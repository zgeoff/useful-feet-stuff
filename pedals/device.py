"""One method per device command. The only module that builds packets.

The command table lives in docs/protocol.md.
"""

import struct
from dataclasses import dataclass
from typing import Literal

from pedals.hid import HidChannel, NoAnswer

READ_CHUNK = 62
READABLE_SPACES = (2, 3, 4)


@dataclass(frozen=True)
class Version:
    text: str
    new_style: bool


class Device:
    def __init__(self, hid: HidChannel):
        self._hid = hid

    def version(self) -> Version:
        answer = self._ask(b"\x01", {0x81, 0x91})
        new_style = answer[0] == 0x91
        text = answer[6:] if new_style else answer[2:]
        return Version(text=text.split(b"\0")[0].decode("cp1252").strip(), new_style=new_style)

    def active_profile(self) -> int:
        return self._ask(b"\x0b", {0x8B})[2]

    def read(self, space: Literal[2, 3, 4], addr: int, length: int) -> bytes:
        if space not in READABLE_SPACES:
            raise ValueError(f"space {space} is not readable; only {READABLE_SPACES}")
        self._ask(bytes([0x0D, 0x01, space]), {0x8D})
        out = bytearray()
        while len(out) < length:
            want = min(READ_CHUNK, length - len(out))
            answer = self._ask(b"\x02\x06" + struct.pack("<HI", want, addr + len(out)), {0x82})
            got = answer[1]
            if got == 0:
                raise NoAnswer(f"the device returned no data at space {space} address {addr + len(out):#x}")
            out += answer[2 : 2 + got]
        return bytes(out)

    def switch_profile(self, n: int) -> None:
        self._ask(bytes([0x04, 0x01, n]), {0x84})

    def _ask(self, payload: bytes, answer: set[int]) -> bytes:
        self._hid.send(payload)
        return self._hid.recv(answer)
