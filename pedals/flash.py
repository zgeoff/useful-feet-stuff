"""Back up, erase, write and verify spaces 2 and 3. The only caller of the Device write side.

The sequence is the vendor app's save, as docs/protocol.md records it, with two checks the vendor
app lacks: the erase must leave both spaces blank, and every chunk is read back before the runtime
starts again.
"""

import struct
from datetime import datetime
from pathlib import Path

from pedals import compiler, profile_image
from pedals.device import PAGE, WRITE_CHUNK, Device

RETRIES = 3
SPACE2_FILE = "space2.bin"
SPACE3_FILE = "space3.bin"


class FlashError(Exception):
    """The write stopped. `backup_dir` holds the pair `pedals restore` needs, when one was taken."""

    def __init__(self, message: str, backup_dir: Path | None, runtime_running: bool):
        super().__init__(message)
        self.backup_dir, self.runtime_running = backup_dir, runtime_running


def read_images(dev: Device) -> tuple[bytes, bytes]:
    """The space 2 and space 3 images on the device, each as long as its header says."""
    return _read_image(dev, 2), _read_image(dev, 3)


def save_backup(space2: bytes, space3: bytes, root: Path, now: datetime) -> Path:
    """Save the pair in a new folder under `root`, named by the time."""
    name = now.strftime("%Y%m%d-%H%M%S")
    folder, n = root / name, 1
    while folder.exists():  # two writes in one second
        n += 1
        folder = root / f"{name}-{n}"
    folder.mkdir(parents=True)
    (folder / SPACE2_FILE).write_bytes(space2)
    (folder / SPACE3_FILE).write_bytes(space3)
    return folder


def load_pair(folder: Path) -> tuple[bytes, bytes]:
    """The space 2 and space 3 images in a backup folder, each cut to the length its header gives."""
    space2 = (folder / SPACE2_FILE).read_bytes()
    space3 = (folder / SPACE3_FILE).read_bytes()
    space2 = space2[: profile_image.image_length(space2)]
    return space2, space3[: runtime_length(space3)]


def runtime_length(space3: bytes) -> int:
    magic, length = struct.unpack_from("<II", space3)
    if magic != compiler.MAGIC:
        raise profile_image.BadImage(f"space 3 magic is {magic:#010x}, not {compiler.MAGIC:#010x}")
    if not compiler.HEADER_LEN <= length <= compiler.MAX_IMAGE_LEN:
        raise profile_image.BadImage(f"space 3 image claims {length} bytes; the limit is {compiler.MAX_IMAGE_LEN}")
    return length


def write(dev: Device, space2: bytes, space3: bytes, old: tuple[bytes, bytes], backup_dir: Path | None,
          profile_after: int) -> None:
    """Write both images. `old` is the pair on the device now, written back if the erase misses space 3."""
    dev.stop_runtime()
    dev.erase_config_sectors()

    # Space 2 and space 3 must read as erased over both the old and the new image.
    if not _blank(dev, 2, max(len(old[0]), len(space2))):
        raise FlashError("space 2 is not blank after the erase; nothing was written", backup_dir, False)
    if not _blank(dev, 3, max(len(old[1]), len(space3))):
        if not old[0]:
            raise FlashError("space 3 is not blank after the erase; nothing was written", backup_dir, False)
        # Space 3 still holds the old runtime, so put the old space 2 back beside it.
        _write_space(dev, 2, old[0], backup_dir)
        dev.start_runtime()
        raise FlashError("space 3 is not blank after the erase; the old config is back", backup_dir, True)

    _write_space(dev, 2, space2, backup_dir)
    _write_space(dev, 3, space3, backup_dir)
    dev.start_runtime()
    dev.switch_profile(profile_after)


def _write_space(dev: Device, space: int, image: bytes, backup_dir: Path | None) -> None:
    dev.select(space)
    for addr, chunk in _chunks(image):
        for _ in range(RETRIES):
            dev.write_chunk(addr, chunk)
            if dev.read_selected(addr, len(chunk)) == chunk:
                break
        else:
            raise FlashError(f"space {space} at {addr:#x} reads back wrong after {RETRIES} writes", backup_dir, False)


def _chunks(image: bytes):
    """56-byte chunks that never cross a 256-byte page, as the vendor app writes them."""
    addr = 0
    while addr < len(image):
        size = min(WRITE_CHUNK, PAGE - addr % PAGE, len(image) - addr)
        yield addr, image[addr : addr + size]
        addr += size


def _blank(dev: Device, space: int, length: int) -> bool:
    dev.select(space)
    return dev.read_selected(0, length) == b"\xff" * length


def _read_image(dev: Device, space: int) -> bytes:
    if space == 2:
        header = dev.read(space=2, addr=0, length=profile_image.HEADER_LEN)
        total = profile_image.image_length(header)
        return header + dev.read(space=2, addr=profile_image.HEADER_LEN, length=total - profile_image.HEADER_LEN)
    head = dev.read(space=3, addr=0, length=8)
    total = runtime_length(head)
    return head + dev.read(space=3, addr=8, length=total - 8)
