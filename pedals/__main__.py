"""Entry point: `python -m pedals [--repo DIR] <command>`. Runs under Windows Python."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from pedals.cli import Env, main
from pedals.config_files import CONFIG_FILE

BACKUP_ROOT = Path(r"C:\Users\Public\Public Hardware\GWS\pedal-restore")


def _open_hid():
    from pedals.windows_hid import WindowsHid  # Windows only

    return WindowsHid.open()


def _vendor_app_running() -> bool:
    listing = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq IDIConfig.exe", "/NH", "/FO", "CSV"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "idiconfig.exe" in listing.stdout.lower()


def _ask(question: str) -> bool:
    try:
        return input(question).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _repo_root(argv: list[str]) -> tuple[Path, list[str]]:
    if len(argv) >= 2 and argv[0] == "--repo":
        return Path(argv[1]), argv[2:]
    here = Path.cwd()
    for folder in (here, *here.parents):
        if (folder / CONFIG_FILE).is_file():
            return folder, argv
    return here, argv


if __name__ == "__main__":
    root, rest = _repo_root(sys.argv[1:])
    env = Env(
        open_hid=_open_hid,
        vendor_app_running=_vendor_app_running,
        repo_root=root,
        out=sys.stdout,
        backup_root=BACKUP_ROOT,
        ask=_ask,
        now=datetime.now,
    )
    sys.exit(main(rest, env))
