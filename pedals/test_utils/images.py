"""Build invented space 2 images for tests, record by record."""

import struct

from pedals.profile_image import HEADER_LEN, MAGIC, VERSION, Record


def build_image(records: list[Record], magic: int = MAGIC, version: int = VERSION) -> bytes:
    area = b"".join(struct.pack("<BBBBH", r.tag, r.a, r.b, r.c, len(r.data)) + r.data for r in records)
    header = struct.pack("<IIII", magic, version, 0, len(area)).ljust(HEADER_LEN, b"\0")
    return header + area


def text(value: str) -> bytes:
    return value.encode("cp1252") + b"\0"


def profile_records(number: int, name: str, pedals: list[tuple[str, bytes, str, str | None]]) -> list[Record]:
    """Records for one profile: (macro file, source, label, description) per used pedal, slots 1–8."""
    out = [
        Record(tag=0x03, a=number, b=0, c=0, data=bytes(29)),
        Record(tag=0x04, a=number, b=0, c=0, data=text(name)),
    ]
    for slot in range(1, 9):
        if slot <= len(pedals):
            macro, source, label, description = pedals[slot - 1]
            out += [
                Record(tag=0x05, a=number, b=slot, c=0x08, data=b"\x08"),
                Record(tag=0x06, a=number, b=slot, c=0, data=text(macro)),
                Record(tag=0x0B, a=number, b=slot, c=0, data=text(label)),
            ]
            if description is not None:
                out.append(Record(tag=0x0C, a=number, b=slot, c=0, data=text(description)))
            out.append(Record(tag=0x07, a=number, b=slot, c=0, data=source + b"\0"))
        else:
            out += [
                Record(tag=0x05, a=number, b=slot, c=0, data=b"\x00"),
                Record(tag=0x06, a=number, b=slot, c=0, data=b"\0"),
            ]
    return out
