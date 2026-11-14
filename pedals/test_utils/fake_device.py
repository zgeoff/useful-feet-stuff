"""FakeDevice: a HidChannel that answers like the pedals' new-style firmware.

Its flash behaves like NOR flash: an erase sets bytes to 0xFF, and a write can only clear bits, so
a write without an erase leaves wrong bytes that a read-back catches.
"""

import struct
from dataclasses import dataclass, field

from pedals.hid import NoAnswer

DEBUG_TEXT = bytes([0xA1, 0x05]) + b"debug"
SPACE_SIZE = {2: 0x20000, 3: 0xC000, 4: 0x624}


@dataclass
class FakeDevice:
    spaces: dict[int, bytes] = field(default_factory=dict)
    active: int = 1
    new_style: bool = True
    silent: bool = False  # the state after a PC reboot: accepts reports, never answers
    erase_clears_space3: bool = True  # what the logged vendor save suggests
    lost_writes: int = 0  # number of writes that never reach the flash, to test the retry
    sent: list[bytes] = field(default_factory=list)
    running: bool = True
    _queue: list[bytes] = field(default_factory=list)
    _space: int | None = None
    _flash: dict[int, bytearray] = field(default_factory=dict)

    def __post_init__(self):
        for space, size in SPACE_SIZE.items():
            stored = self.spaces.get(space, b"")
            self._flash[space] = bytearray(stored + b"\xff" * (size - len(stored)))

    def stored(self, space: int, length: int) -> bytes:
        return bytes(self._flash[space][:length])

    def send(self, payload: bytes) -> None:
        if len(payload) > 64:
            raise ValueError("payload over 64 bytes")
        self.sent.append(payload)
        if not self.silent:
            self._queue.append(DEBUG_TEXT)
            answer = self._answer(payload)
            if answer is not None:
                self._queue.append(answer)

    def recv(self, want: set[int], timeout_s: float = 2.0) -> bytes:
        while self._queue:
            report = self._queue.pop(0).ljust(64, b"\0")
            if report[0] in want:
                return report
        raise NoAnswer("fake device: no answer")

    def _answer(self, payload: bytes) -> bytes | None:
        cmd = payload[0]
        if cmd == 0x01:
            text = b" Sep 26 2020 14:06:10 Ver 1.0.8\0"
            return bytes([0x91, 0x06, 0x01, 0, 0, 0]) + text if self.new_style else bytes([0x81, 0x20]) + text
        if cmd == 0x0B:
            return bytes([0x8B, 0x01, self.active])
        if cmd == 0x0D:
            if payload[2] not in SPACE_SIZE:
                raise AssertionError(f"fake device: space {payload[2]:#04x} must never be selected")
            self._space = payload[2]
            return bytes([0x8D, 0x00])
        if cmd == 0x02:
            length, addr = struct.unpack_from("<HI", payload, 2)
            data = bytes(self._flash[self._space][addr : addr + length])
            return bytes([0x82, len(data)]) + data
        if cmd == 0x04:
            self.active = payload[2]
            return bytes([0x84, 0x00])
        if cmd == 0x08:
            self.running = False
            return bytes([0x88, 0x00])
        if cmd == 0x09:
            self.running = True
            return bytes([0x89, 0x00])
        if cmd == 0x05:
            self._check_write_allowed()
            sector = payload[2]
            if self._space != 2 or sector not in (0, 1):
                raise AssertionError(f"fake device: erase of sector {sector} in space {self._space}")
            if sector == 0:
                self._flash[2][:] = b"\xff" * SPACE_SIZE[2]
            elif self.erase_clears_space3:
                self._flash[3][:] = b"\xff" * SPACE_SIZE[3]
            return bytes([0x85, 0x00])
        if cmd == 0x03:
            self._check_write_allowed()
            length, addr = struct.unpack_from("<HI", payload, 2)
            data = payload[8 : 8 + length]
            if payload[1] != length + 6 or length > 56 or addr // 256 != (addr + length - 1) // 256:
                raise AssertionError(f"fake device: bad write of {length} bytes at {addr:#x}")
            if self._space not in (2, 3):
                raise AssertionError(f"fake device: write to space {self._space}")
            if self.lost_writes:
                self.lost_writes -= 1
                return bytes([0x83, 0x01, 0x00])
            flash = self._flash[self._space]
            for i, b in enumerate(data):
                flash[addr + i] &= b
            return bytes([0x83, 0x01, 0x00])
        raise AssertionError(f"fake device: command {cmd:#04x} is not one the CLI sends")

    def _check_write_allowed(self) -> None:
        if self.running:
            raise AssertionError("fake device: flash command while the runtime runs; send 08 first")
