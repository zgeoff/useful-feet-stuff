"""Config ⇄ pedals.toml + macros/."""

import json
import tomllib
from pathlib import Path

from pedals.profile_image import (
    PEDALS_PER_PROFILE,
    SETTINGS_LEN,
    Config,
    Pedal,
    Profile,
    Record,
)

CONFIG_FILE = "pedals.toml"
MACROS_DIR = "macros"
MAX_PROFILES = 5


class ConfigError(Exception):
    def __init__(self, file: str, key: str, message: str):
        super().__init__(f"{file}: {key}: {message}")
        self.file = file
        self.key = key


class PullRefused(Exception):
    """The device config cannot be written to the repo as it is."""


def load(root: Path) -> Config:
    path = root / CONFIG_FILE
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(CONFIG_FILE, "-", "file not found; run `pedals pull` first") from None
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(CONFIG_FILE, "-", str(err)) from None

    raw_profiles = doc.get("profile", [])
    if not 1 <= len(raw_profiles) <= MAX_PROFILES:
        raise ConfigError(CONFIG_FILE, "profile", f"{len(raw_profiles)} profiles; allowed 1 to {MAX_PROFILES}")

    profiles = [_load_profile(root, i, raw) for i, raw in enumerate(raw_profiles, start=1)]
    extra = [
        Record(tag=_int(r, "tag", f"record[{i}]"), a=_int(r, "profile", f"record[{i}]"), b=0, c=0,
               data=_hex(r.get("data", ""), f"record[{i}].data"))
        for i, r in enumerate(doc.get("record", []))
    ]
    return Config(
        owner=_str(doc, "owner", "owner", default=""),
        serial="",
        files={k: str(v) for k, v in doc.get("files", {}).items()},
        profiles=profiles,
        extra=extra,
    )


def save(config: Config, root: Path) -> list[str]:
    """Write pedals.toml and each named macro. Return the macro file names written."""
    macros = _macros_to_write(config)
    (root / MACROS_DIR).mkdir(parents=True, exist_ok=True)
    for name, source in macros.items():
        (root / MACROS_DIR / name).write_bytes(source)
    (root / CONFIG_FILE).write_text(_to_toml(config), encoding="utf-8", newline="\n")
    return sorted(macros)


def _load_profile(root: Path, number: int, raw: dict) -> Profile:
    key = f"profile[{number}]"
    raw_pedals = raw.get("pedal", [])
    if len(raw_pedals) > PEDALS_PER_PROFILE:
        raise ConfigError(CONFIG_FILE, f"{key}.pedal", f"{len(raw_pedals)} pedals; allowed up to {PEDALS_PER_PROFILE}")
    settings = _hex(raw.get("settings", ""), f"{key}.settings")
    if len(settings) != SETTINGS_LEN:
        raise ConfigError(CONFIG_FILE, f"{key}.settings", f"{len(settings)} bytes; must be {SETTINGS_LEN}")
    pedals = [_load_pedal(root, f"{key}.pedal[{i}]", p) for i, p in enumerate(raw_pedals, start=1)]
    pedals += [Pedal() for _ in range(PEDALS_PER_PROFILE - len(pedals))]
    return Profile(
        name=_str(raw, "name", f"{key}.name"),
        settings=settings,
        image=raw.get("image"),
        pedals=pedals,
    )


def _load_pedal(root: Path, key: str, raw: dict) -> Pedal:
    macro = raw.get("macro")
    if macro is None:
        return Pedal(label=raw.get("label"), description=raw.get("description"))
    _check_macro_name(macro, lambda msg: ConfigError(CONFIG_FILE, f"{key}.macro", msg))
    path = root / MACROS_DIR / macro
    if not path.is_file():
        raise ConfigError(CONFIG_FILE, f"{key}.macro", f"{MACROS_DIR}/{macro} does not exist")
    return Pedal(macro=macro, source=path.read_bytes(), label=raw.get("label"), description=raw.get("description"))


def _macros_to_write(config: Config) -> dict[str, bytes]:
    found: dict[str, tuple[bytes, str]] = {}
    for n, profile in enumerate(config.profiles, start=1):
        for s, pedal in enumerate(profile.pedals, start=1):
            if pedal.macro is None:
                continue
            where = f"profile {n} pedal {s}"
            _check_macro_name(pedal.macro, lambda msg: PullRefused(f"{where}: {msg}"))
            source = pedal.source or b""
            if pedal.macro in found and found[pedal.macro][0] != source:
                raise PullRefused(
                    f"{found[pedal.macro][1]} and {where} both name {pedal.macro} with different source"
                )
            found.setdefault(pedal.macro, (source, where))
    return {name: source for name, (source, _) in found.items()}


def _check_macro_name(name: str, error) -> None:
    if not name or "/" in name or "\\" in name or name in (".", "..") or ":" in name:
        raise error(f"{name!r} is not a plain file name")


def _to_toml(config: Config) -> str:
    lines = [f"owner = {_q(config.owner)}", ""]
    if config.files:
        lines.append("[files]")
        lines += [f"{k} = {_q(v)}" for k, v in config.files.items()]
        lines.append("")
    for profile in config.profiles:
        lines.append("[[profile]]")
        lines.append(f"name = {_q(profile.name)}")
        if profile.image is not None:
            lines.append(f"image = {_q(profile.image)}")
        lines.append(f"settings = {_q(profile.settings.hex())}")
        lines.append("")
        for pedal in _trim_empty_tail(profile.pedals):
            lines.append("  [[profile.pedal]]")
            for key in ("macro", "label", "description"):
                value = getattr(pedal, key)
                if value is not None:
                    lines.append(f"  {key} = {_q(value)}")
            lines.append("")
    for rec in config.extra:
        lines += ["[[record]]", f"tag = {rec.tag:#04x}", f"profile = {rec.a}", f"data = {_q(rec.data.hex())}", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def _trim_empty_tail(pedals: list[Pedal]) -> list[Pedal]:
    end = len(pedals)
    while end and pedals[end - 1] == Pedal():
        end -= 1
    return pedals[:end]


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def _str(raw: dict, key: str, where: str, default: str | None = None) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(CONFIG_FILE, where, "must be a string")
    return value


def _int(raw: dict, key: str, where: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or not 0 <= value <= 0xFF:
        raise ConfigError(CONFIG_FILE, f"{where}.{key}", "must be an integer from 0 to 255")
    return value


def _hex(value: str, where: str) -> bytes:
    try:
        return bytes.fromhex(value)
    except (ValueError, TypeError):
        raise ConfigError(CONFIG_FILE, where, "must be a hex string") from None
