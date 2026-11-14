"""Space 2 bytes → Config. The layout lives in docs/image-format.md."""

import struct
from dataclasses import dataclass, field

MAGIC = 0x86754232
VERSION = 1
HEADER_LEN = 0x54
MAX_IMAGE_LEN = 128 * 1024
PEDALS_PER_PROFILE = 4
DEVICE_SLOTS = 8
SETTINGS_LEN = 29
MAX_PROFILES = 5

TAG_OWNER = 0x01
TAG_SERIAL = 0x02
TAG_SETTINGS = 0x03
TAG_PROFILE_NAME = 0x04
TAG_SLOT_KIND = 0x05
TAG_FILE = 0x06
TAG_SOURCE = 0x07
TAG_LABEL = 0x0B
TAG_DESCRIPTION = 0x0C
TAG_IMAGE = 0x10
TAG_ALIASES_FILE = 0x11
TAG_MACROS_FILE = 0x12

FILE_TAGS = {TAG_ALIASES_FILE: "aliases", TAG_MACROS_FILE: "macros"}
PEDAL_TAGS = {TAG_SLOT_KIND, TAG_FILE, TAG_SOURCE, TAG_LABEL, TAG_DESCRIPTION}


class BadImage(Exception):
    """The device's space 2 data breaks a rule this tool depends on."""


class TooLarge(Exception):
    """An image from the repo's config passes its size limit."""


@dataclass
class Record:
    tag: int
    a: int  # profile number on profile and pedal records
    b: int  # slot number on pedal records
    c: int  # 0x08 on the tag 0x05 record of a used slot
    data: bytes


@dataclass
class Pedal:
    macro: str | None = None  # None = empty slot
    source: bytes | None = None  # the .idi file's bytes; no trailing NUL
    label: str | None = None
    description: str | None = None  # None = no tag 0x0c record


@dataclass
class Profile:
    name: str
    settings: bytes
    image: str | None
    pedals: list[Pedal]


@dataclass
class Config:
    owner: str
    serial: str
    files: dict[str, str]
    profiles: list[Profile]
    extra: list[Record] = field(default_factory=list)


def image_length(header: bytes) -> int:
    """Return the whole image length from its first HEADER_LEN bytes."""
    magic, version, _, records_len = struct.unpack_from("<IIII", header)
    if magic != MAGIC:
        raise BadImage(f"space 2 magic is {magic:#010x}, not {MAGIC:#010x}")
    if version != VERSION:
        raise BadImage(f"space 2 image version is {version}, not {VERSION}")
    total = HEADER_LEN + records_len
    if total > MAX_IMAGE_LEN:
        raise BadImage(f"space 2 image claims {total} bytes; the limit is {MAX_IMAGE_LEN}")
    return total


def decode(image: bytes) -> Config:
    total = image_length(image)
    if len(image) < total:
        raise BadImage(f"space 2 image is {len(image)} bytes; its header says {total}")
    records = list(_records(image[HEADER_LEN:total]))

    owner = serial = ""
    files: dict[str, str] = {}
    profiles: dict[int, dict] = {}
    slots: dict[tuple[int, int], Pedal] = {}
    extra: list[Record] = []

    for rec in records:
        if rec.tag == TAG_OWNER:
            owner = _text(rec.data)
        elif rec.tag == TAG_SERIAL:
            serial = _text(rec.data)
        elif rec.tag in FILE_TAGS:
            files[FILE_TAGS[rec.tag]] = _text(rec.data)
        elif rec.tag == TAG_SETTINGS:
            profiles.setdefault(rec.a, {})["settings"] = rec.data
        elif rec.tag == TAG_PROFILE_NAME:
            profiles.setdefault(rec.a, {})["name"] = _text(rec.data)
        elif rec.tag == TAG_IMAGE:
            profiles.setdefault(rec.a, {})["image"] = _text(rec.data)
        elif rec.tag in PEDAL_TAGS:
            _apply_pedal_record(slots.setdefault((rec.a, rec.b), Pedal()), rec)
        else:
            extra.append(rec)

    numbers = sorted(profiles)
    if numbers != list(range(1, len(numbers) + 1)):
        raise BadImage(f"profile numbers are {numbers}; expected 1 to {len(numbers)}")
    for (profile, slot), pedal in slots.items():
        if profile not in profiles:
            raise BadImage(f"pedal record for profile {profile}, which has no name record")
        if not 1 <= slot <= DEVICE_SLOTS:
            raise BadImage(f"profile {profile} has a record for slot {slot}")
        if slot > PEDALS_PER_PROFILE and (pedal.macro or pedal.label or pedal.description):
            raise BadImage(f"profile {profile} slot {slot} holds a macro, label or description")

    return Config(
        owner=owner,
        serial=serial,
        files=files,
        profiles=[
            Profile(
                name=profiles[n].get("name", ""),
                settings=profiles[n].get("settings", b""),
                image=profiles[n].get("image"),
                pedals=[slots.get((n, s), Pedal()) for s in range(1, PEDALS_PER_PROFILE + 1)],
            )
            for n in numbers
        ],
        extra=extra,
    )


def _apply_pedal_record(pedal: Pedal, rec: Record) -> None:
    if rec.tag == TAG_FILE:
        pedal.macro = _text(rec.data) or None
    elif rec.tag == TAG_SOURCE:
        pedal.source = _strip_nul(rec.data)
    elif rec.tag == TAG_LABEL:
        pedal.label = _text(rec.data)
    elif rec.tag == TAG_DESCRIPTION:
        pedal.description = _text(rec.data)
    # TAG_SLOT_KIND carries nothing a Pedal keeps: a used slot is one with a macro.


def _records(area: bytes):
    off = 0
    while off < len(area):
        if off + 6 > len(area):
            raise BadImage(f"record header at {HEADER_LEN + off:#x} runs past the image end")
        tag, a, b, c, length = struct.unpack_from("<BBBBH", area, off)
        end = off + 6 + length
        if end > len(area):
            raise BadImage(f"record {tag:#04x} at {HEADER_LEN + off:#x} runs past the image end")
        yield Record(tag=tag, a=a, b=b, c=c, data=area[off + 6 : end])
        off = end


def _strip_nul(data: bytes) -> bytes:
    return data[:-1] if data.endswith(b"\0") else data


def _text(data: bytes) -> str:
    return _strip_nul(data).decode("cp1252")


def encode(config: Config) -> bytes:
    """Config → space 2 bytes, in the vendor app's record order (docs/image-format.md).

    The vendor app leaves some record header bytes uninitialised; encode writes 0 there.
    """
    if not 1 <= len(config.profiles) <= MAX_PROFILES:
        raise ValueError(f"a config holds 1 to {MAX_PROFILES} profiles, not {len(config.profiles)}")
    records = [_rec(TAG_OWNER, 0, 0, 0, _string(config.owner)), _rec(TAG_SERIAL, 0, 0, 0, _string(config.serial))]
    starts = []
    for n, profile in enumerate(config.profiles, 1):
        starts.append(sum(len(r) for r in records))
        if len(profile.settings) != SETTINGS_LEN:
            raise ValueError(f"profile {n} settings are {len(profile.settings)} bytes, not {SETTINGS_LEN}")
        records.append(_rec(TAG_SETTINGS, n, 0, 0, profile.settings))
        records.append(_rec(TAG_PROFILE_NAME, n, 0, 0, _string(profile.name)))
        if profile.image is not None:
            records.append(_rec(TAG_IMAGE, n, 0, 0, _string(profile.image)))
        for slot in range(1, DEVICE_SLOTS + 1):
            pedal = profile.pedals[slot - 1] if slot <= len(profile.pedals) else Pedal()
            used = pedal.macro is not None
            records.append(_rec(TAG_SLOT_KIND, n, slot, 0x08 if used else 0, bytes([0x08 if used else 0])))
            records.append(_rec(TAG_FILE, n, slot, 0, _string(pedal.macro or "")))
            if used:
                records.append(_rec(TAG_LABEL, n, slot, 0, _string(pedal.label or "")))
                if pedal.description is not None:
                    records.append(_rec(TAG_DESCRIPTION, n, slot, 0, _string(pedal.description)))
                records.append(_rec(TAG_SOURCE, n, slot, 0, (pedal.source or b"") + b"\0"))
    last = len(config.profiles)
    for tag, key in FILE_TAGS.items():
        if key in config.files:
            records.append(_rec(tag, last, 0, 0, _string(config.files[key])))
    records += [_rec(r.tag, r.a, r.b, r.c, r.data) for r in config.extra]

    body = b"".join(records)
    offsets = [HEADER_LEN + s for s in starts] + [0] * (MAX_PROFILES - len(starts))
    header = struct.pack("<IIIII5H", MAGIC, VERSION, (1 << last) - 1, len(body), len(records), *offsets)
    image = header.ljust(HEADER_LEN, b"\0") + body
    if len(image) > MAX_IMAGE_LEN:
        raise TooLarge(f"space 2 image is {len(image)} bytes; the limit is {MAX_IMAGE_LEN}")
    return image


def _rec(tag: int, a: int, b: int, c: int, data: bytes) -> bytes:
    if len(data) > 0xFFFF:
        raise TooLarge(f"record {tag:#04x} holds {len(data)} bytes; the limit is 65535")
    return struct.pack("<BBBBH", tag, a, b, c, len(data)) + data


def _string(value: str) -> bytes:
    return value.encode("cp1252") + b"\0"
