"""The `pedals` commands. `main` maps every error to its exit code."""

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from pedals import compiler, config_files, flash, profile_image
from pedals.compiler import CompileError
from pedals.config_files import ConfigError, PullRefused
from pedals.device import Device, WriteFailed
from pedals.flash import FlashError
from pedals.hid import DeviceNotFound, HidChannel, NoAnswer
from pedals.profile_image import BadImage, Config, TooLarge

EXIT_OK = 0
EXIT_DIFF = 1
EXIT_USAGE = 2
EXIT_NO_DEVICE = 3
EXIT_BAD_INPUT = 4
EXIT_FLASH = 5
EXIT_REFUSED = 6
EXIT_BAD_DEVICE_DATA = 7

REPLUG_HINT = "replug the pedals' USB cable, then run the command again"


@dataclass
class Env:
    open_hid: Callable[[], HidChannel]
    vendor_app_running: Callable[[], bool]
    repo_root: Path
    out: TextIO
    backup_root: Path  # where apply and restore save the pair they replace
    ask: Callable[[str], bool]  # the owner's yes or no
    now: Callable[[], datetime]


class _Exit(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def main(argv: list[str], env: Env) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.run(args, env)
    except _Exit as err:
        _say(env, str(err))
        return err.code
    except (DeviceNotFound,) as err:
        _say(env, f"device     not found: {err}")
        return EXIT_NO_DEVICE
    except NoAnswer as err:
        _say(env, f"channel    no answer: {REPLUG_HINT} ({err})")
        return EXIT_NO_DEVICE
    except ConfigError as err:
        _say(env, f"config     {err}")
        return EXIT_BAD_INPUT
    except (CompileError, TooLarge) as err:
        _say(env, f"compile    {err}")
        return EXIT_BAD_INPUT
    except (FlashError, WriteFailed) as err:
        _say(env, f"flash      {err}")
        backup_dir = getattr(err, "backup_dir", None)
        if not getattr(err, "runtime_running", False):
            _say(env, "flash      the pedals' macros are stopped until a write succeeds")
        if backup_dir is not None:
            _say(env, f"flash      to put the old config back, run: pedals restore \"{backup_dir}\"")
        return EXIT_FLASH
    except (BadImage, PullRefused) as err:
        _say(env, f"device     {err}")
        return EXIT_BAD_DEVICE_DATA


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pedals", description="Manage the GWS Fragpedal Quad.")
    commands = parser.add_subparsers(required=True, metavar="command")
    commands.add_parser("status", help="firmware, channel and active profile").set_defaults(run=_status)
    show = commands.add_parser("show", help="profiles and pedals on the device")
    show.add_argument("profile", nargs="?", help="number or exact name; default: every profile")
    show.set_defaults(run=_show)
    commands.add_parser("pull", help="write the device config to pedals.toml + macros/").set_defaults(run=_pull)
    commands.add_parser("diff", help="compare the repo with the device").set_defaults(run=_diff)
    switch = commands.add_parser("switch", help="change the active profile; no flash write")
    switch.add_argument("profile", help="number or exact name")
    switch.set_defaults(run=_switch)
    apply = commands.add_parser("apply", help="compile the repo and write it to the pedals")
    apply.add_argument("--yes", action="store_true", help="write without asking")
    apply.set_defaults(run=_apply)
    restore = commands.add_parser("restore", help="write a saved space2.bin + space3.bin pair to the pedals")
    restore.add_argument("dir", type=Path, help="the folder that holds the pair")
    restore.add_argument("--yes", action="store_true", help="write without asking")
    restore.set_defaults(run=_restore)
    return parser


def _connect(env: Env, show_version: bool = False) -> Device:
    if env.vendor_app_running():
        raise _Exit(EXIT_REFUSED, "refused    IDIConfig.exe is running; close it first, since both read the same reports")
    dev = Device(env.open_hid())
    version = dev.version()
    if show_version:
        _say(env, f"firmware   {version.text}")
    if not version.new_style:
        raise _Exit(EXIT_REFUSED, "refused    old-style firmware; this tool supports only new-style firmware")
    return dev


def _read_config(dev: Device) -> Config:
    header = dev.read(space=2, addr=0, length=profile_image.HEADER_LEN)
    total = profile_image.image_length(header)
    rest = dev.read(space=2, addr=profile_image.HEADER_LEN, length=total - profile_image.HEADER_LEN)
    return profile_image.decode(header + rest)


def _status(args, env: Env) -> int:
    dev = _connect(env, show_version=True)
    active = dev.active_profile()
    _say(env, "channel    ok")
    config = _read_config(dev)
    name = config.profiles[active - 1].name if 1 <= active <= len(config.profiles) else "?"
    _say(env, f'profile    {active} "{name}"')
    return EXIT_OK


def _show(args, env: Env) -> int:
    config = _read_config(_connect(env))
    numbers = [_resolve(config, args.profile)] if args.profile else range(1, len(config.profiles) + 1)
    for n in numbers:
        profile = config.profiles[n - 1]
        _say(env, f'profile {n} "{profile.name}"')
        for s, pedal in enumerate(profile.pedals, start=1):
            if pedal.macro is None:
                _say(env, f"  pedal {s}  (empty)")
            else:
                _say(env, f"  pedal {s}  {pedal.label or '':<20}{pedal.macro}")
    return EXIT_OK


def _pull(args, env: Env) -> int:
    config = _read_config(_connect(env))
    written = config_files.save(config, env.repo_root)
    _say(env, f"wrote      {config_files.CONFIG_FILE} and {len(written)} macros: {', '.join(written)}")
    return EXIT_OK


def _diff(args, env: Env) -> int:
    repo = config_files.load(env.repo_root)
    device = _read_config(_connect(env))
    lines = _differences(repo, device)
    for line in lines:
        _say(env, line)
    if not lines:
        _say(env, "same       the repo matches the device")
    # a macro no pedal names is a library file, so it is a note and leaves the exit code alone
    for line in _unnamed_macros(env.repo_root, repo):
        _say(env, line)
    return EXIT_DIFF if lines else EXIT_OK


def _switch(args, env: Env) -> int:
    dev = _connect(env)
    config = _read_config(dev)
    n = _resolve(config, args.profile)
    dev.switch_profile(n)
    _say(env, f'profile    {n} "{config.profiles[n - 1].name}"')
    return EXIT_OK


def _apply(args, env: Env) -> int:
    repo = config_files.load(env.repo_root)
    dev = _connect(env)
    old = flash.read_images(dev)
    device = profile_image.decode(old[0])
    repo.serial = device.serial  # pedals.toml holds no serial; keep the device's own
    space2 = profile_image.encode(repo)
    space3 = compiler.compile(repo)
    lines = _differences(repo, device)
    if not lines:
        _say(env, "same       the repo matches the device; nothing to write")
        return EXIT_OK
    for line in lines:
        _say(env, line)
    _say(env, f"write      space 2: {len(space2)} bytes, space 3: {len(space3)} bytes")
    if not args.yes and not env.ask("write this config to the pedals? [y/N] "):
        _say(env, "stopped    nothing written")
        return EXIT_OK
    active = dev.active_profile()
    folder = flash.save_backup(*old, env.backup_root, env.now())
    _say(env, f"backup     {folder}")
    flash.write(dev, space2, space3, old=old, backup_dir=folder,
                profile_after=active if active <= len(repo.profiles) else 1)
    if _differences(repo, _read_config(dev)):
        raise FlashError("the device reads back a config other than the repo's", folder, True)
    _say(env, f"wrote      {len(repo.profiles)} profiles; the device matches the repo")
    return EXIT_OK


def _restore(args, env: Env) -> int:
    if not (args.dir / flash.SPACE2_FILE).is_file() or not (args.dir / flash.SPACE3_FILE).is_file():
        raise _Exit(EXIT_USAGE, f"restore    {args.dir} holds no {flash.SPACE2_FILE} and {flash.SPACE3_FILE}")
    space2, space3 = flash.load_pair(args.dir)
    dev = _connect(env)
    # After a failed write the device images can be unreadable; restore goes on without them.
    try:
        old = flash.read_images(dev)
    except BadImage:
        old = None
    _say(env, f"restore    space 2: {len(space2)} bytes, space 3: {len(space3)} bytes, from {args.dir}")
    if not args.yes and not env.ask("write this pair to the pedals? [y/N] "):
        _say(env, "stopped    nothing written")
        return EXIT_OK
    folder = None
    if old is not None:
        folder = flash.save_backup(*old, env.backup_root, env.now())
        _say(env, f"backup     {folder}")
    flash.write(dev, space2, space3, old=old or (b"", b""), backup_dir=folder or args.dir, profile_after=1)
    _say(env, "wrote      the pair; the pedals run profile 1")
    return EXIT_OK


def _resolve(config: Config, arg: str) -> int:
    count = len(config.profiles)
    if arg.isdigit():
        n = int(arg)
        if not 1 <= n <= count:
            raise _Exit(EXIT_USAGE, f"profile    {n} does not exist; the device has profiles 1 to {count}")
        return n
    matches = [n for n, p in enumerate(config.profiles, start=1) if p.name == arg]
    if len(matches) != 1:
        problem = "matches no profile" if not matches else f"matches profiles {matches}"
        raise _Exit(EXIT_USAGE, f'profile    "{arg}" {problem}')
    return matches[0]


def _differences(repo: Config, device: Config) -> list[str]:
    lines = []
    if repo.owner != device.owner:
        lines.append(f"owner      repo {repo.owner!r}, device {device.owner!r}")
    if repo.files != device.files:
        lines.append(f"files      repo {repo.files}, device {device.files}")
    for n in range(1, max(len(repo.profiles), len(device.profiles)) + 1):
        if n > len(repo.profiles):
            lines.append(f'profile {n}  only on the device: "{device.profiles[n - 1].name}"')
            continue
        if n > len(device.profiles):
            lines.append(f'profile {n}  only in the repo: "{repo.profiles[n - 1].name}"')
            continue
        lines += _profile_differences(n, repo.profiles[n - 1], device.profiles[n - 1])
    repo_extra = [(r.tag, r.a, r.data) for r in repo.extra]
    device_extra = [(r.tag, r.a, r.data) for r in device.extra]
    if repo_extra != device_extra:
        lines.append("records    the [[record]] entries differ from the device")
    return lines


def _profile_differences(n: int, repo, device) -> list[str]:
    lines = []
    for key in ("name", "settings", "image"):
        if getattr(repo, key) != getattr(device, key):
            lines.append(f"profile {n}  {key}: repo {_show_value(getattr(repo, key))}, device {_show_value(getattr(device, key))}")
    for s, (mine, theirs) in enumerate(zip(repo.pedals, device.pedals), start=1):
        for key in ("macro", "label", "description"):
            if getattr(mine, key) != getattr(theirs, key):
                lines.append(f"profile {n} pedal {s}  {key}: repo {getattr(mine, key)!r}, device {getattr(theirs, key)!r}")
        if mine.macro == theirs.macro and mine.source != theirs.source:
            lines.append(f"profile {n} pedal {s}  source of {mine.macro} differs")
    return lines


def _show_value(value) -> str:
    return value.hex() if isinstance(value, bytes) else repr(value)


def _unnamed_macros(root: Path, repo: Config) -> list[str]:
    named = {p.macro for profile in repo.profiles for p in profile.pedals if p.macro}
    folder = root / config_files.MACROS_DIR
    files = sorted(f.name for f in folder.glob("*.idi")) if folder.is_dir() else []
    return [f"unused     {config_files.MACROS_DIR}/{name}: no pedal names it" for name in files if name not in named]


def _say(env: Env, line: str) -> None:
    print(line, file=env.out)
