"""The HID channel the device module talks through, and its errors."""

from typing import Protocol


class NoAnswer(Exception):
    """The device sent no wanted report before the timeout."""


class DeviceNotFound(Exception):
    """No pedal config interface (vid_1095&pid_0400&mi_01) is present."""


class HidChannel(Protocol):
    def send(self, payload: bytes) -> None:
        """Send one output report. `payload` is at most 64 bytes; report ID 0 is added."""
        ...

    def recv(self, want: set[int], timeout_s: float = 2.0) -> bytes:
        """Return the first 64-byte input report whose byte 0 is in `want`, skipping the rest.

        Raises NoAnswer when none arrives within `timeout_s`.
        """
        ...
