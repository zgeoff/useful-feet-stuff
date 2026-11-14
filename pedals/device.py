"""One method per device command. The only module that builds packets.

The command table lives in docs/protocol.md.
"""

import struct
from dataclasses import dataclass
from typing import Literal

from pedals.hid import HidChannel, NoAnswer

READ_CHUNK = 62
READABLE_SPACES = (2, 3, 4)
WRITE_CHUNK = 56
PAGE = 256
WRITABLE_SPACES = (2, 3)
ERASE_TIMEOUT_S = 5.0  # each erase took about 0.7 s in the logged vendor save


@dataclass(frozen=True)
class Version:
    text: str
    new_style: bool


class WriteFailed(Exception):
    """The device answered a write with a non-zero status."""


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
        self._select(space)
        return self.read_selected(addr, length)

    def switch_profile(self, n: int) -> None:
        self._ask(bytes([0x04, 0x01, n]), {0x84})

    # --- write side: only the flash module calls these -----------------------------------------

    def stop_runtime(self) -> None:
        self._ask(b"\x08", {0x88})

    def start_runtime(self) -> None:
        self._ask(b"\x09", {0x89})

    def erase_config_sectors(self) -> None:
        """Erase what the vendor app erases before a save: sectors 0 and 1, with space 2 selected."""
        self._select(2)
        for sector in (0, 1):
            self._ask(bytes([0x05, 0x01, sector]), {0x85}, timeout_s=ERASE_TIMEOUT_S)

    def select(self, space: Literal[2, 3]) -> None:
        if space not in WRITABLE_SPACES:
            raise ValueError(f"space {space} is not writable; only {WRITABLE_SPACES}")
        self._select(space)

    def write_chunk(self, addr: int, data: bytes) -> None:
        """Write one chunk to the selected space: at most 56 bytes, inside one 256-byte page."""
        if not 0 < len(data) <= WRITE_CHUNK or addr // PAGE != (addr + len(data) - 1) // PAGE:
            raise ValueError(f"a write of {len(data)} bytes at {addr:#x} breaks the chunk rules")
        answer = self._ask(bytes([0x03, len(data) + 6]) + struct.pack("<HI", len(data), addr) + data, {0x83})
        if answer[1] >= 1 and answer[2] != 0:
            raise WriteFailed(f"the device answered status {answer[2]} to a write at {addr:#x}")

    def read_selected(self, addr: int, length: int) -> bytes:
        """Read from the space the last select chose."""
        out = bytearray()
        while len(out) < length:
            want = min(READ_CHUNK, length - len(out))
            answer = self._ask(b"\x02\x06" + struct.pack("<HI", want, addr + len(out)), {0x82})
            got = answer[1]
            if got == 0:
                raise NoAnswer(f"the device returned no data at address {addr + len(out):#x}")
            out += answer[2 : 2 + got]
        return bytes(out)

    def _select(self, space: int) -> None:
        self._ask(bytes([0x0D, 0x01, space]), {0x8D})

    def _ask(self, payload: bytes, answer: set[int], timeout_s: float = 2.0) -> bytes:
        self._hid.send(payload)
        return self._hid.recv(answer, timeout_s)
