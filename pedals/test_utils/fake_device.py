"""FakeDevice: a HidChannel that answers like the pedals' new-style firmware."""

import struct
from dataclasses import dataclass, field

from pedals.hid import NoAnswer

DEBUG_TEXT = bytes([0xA1, 0x05]) + b"debug"


@dataclass
class FakeDevice:
    spaces: dict[int, bytes] = field(default_factory=dict)
    active: int = 1
    new_style: bool = True
    silent: bool = False  # the state after a PC reboot: accepts reports, never answers
    sent: list[bytes] = field(default_factory=list)
    _queue: list[bytes] = field(default_factory=list)
    _space: int | None = None

    def send(self, payload: bytes) -> None:
        if len(payload) > 64:
            raise ValueError("payload over 64 bytes")
        self.sent.append(payload)
        if not self.silent:
            self._queue.append(DEBUG_TEXT)
            self._queue.append(self._answer(payload))

    def recv(self, want: set[int], timeout_s: float = 2.0) -> bytes:
        while self._queue:
            report = self._queue.pop(0).ljust(64, b"\0")
            if report[0] in want:
                return report
        raise NoAnswer("fake device: no answer")

    def _answer(self, payload: bytes) -> bytes:
        cmd = payload[0]
        if cmd == 0x01:
            text = b" Sep 26 2020 14:06:10 Ver 1.0.8\0"
            return bytes([0x91, 0x06, 0x01, 0, 0, 0]) + text if self.new_style else bytes([0x81, 0x20]) + text
        if cmd == 0x0B:
            return bytes([0x8B, 0x01, self.active])
        if cmd == 0x0D:
            self._space = payload[2]
            return bytes([0x8D, 0x00])
        if cmd == 0x02:
            length, addr = struct.unpack_from("<HI", payload, 2)
            data = self.spaces.get(self._space, b"")[addr : addr + length]
            return bytes([0x82, len(data)]) + data
        if cmd == 0x04:
            self.active = payload[2]
            return bytes([0x84, 0x00])
        raise AssertionError(f"fake device: command {cmd:#04x} is not part of the read side")
