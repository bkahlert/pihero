"""Raw access to SD cards on macOS.

The raw disk is opened through authopen, which asks for authorization and hands the descriptor back over a socket, the way
Raspberry Pi Imager does; a plain open is refused even for root.
"""

import plistlib
import socket
import subprocess
import time
from pathlib import Path

from . import prompt

AUTHOPEN = "/usr/libexec/authopen"


def disk_info(disk: str) -> dict:
    out = subprocess.run(["diskutil", "info", "-plist", disk], capture_output=True, check=True).stdout
    return plistlib.loads(out)


def is_card(info: dict) -> bool:
    return bool(info.get("WholeDisk")) and bool(info.get("RemovableMedia")) and not info.get("Internal")


def check_removable(info: dict) -> None:
    ident = info.get("DeviceIdentifier", "?")
    if not info.get("WholeDisk"):
        raise SystemExit(f"{ident} is a partition; name the whole disk")
    if info.get("Internal") or not info.get("RemovableMedia"):
        raise SystemExit(f"{ident} ({info.get('MediaName', 'unknown media')}) is not a removable disk")


def cards() -> list[dict]:
    """Returns the info of every external, physical, removable whole disk, in diskutil's order."""
    out = subprocess.run(["diskutil", "list", "-plist", "external", "physical"], capture_output=True, check=True).stdout
    infos = (disk_info(ident) for ident in plistlib.loads(out).get("WholeDisks", []))
    return [info for info in infos if is_card(info)]


def describe(info: dict) -> str:
    return f"{info.get('DeviceIdentifier', '?')}  {info.get('MediaName', 'unknown media').strip()}  {info.get('TotalSize', 0) / 1e9:.1f} GB"


def card(ident: str) -> dict:
    """Returns the info of the named card, or of the one chosen from the cards present when ident is empty."""
    if ident:
        info = disk_info(ident)
        check_removable(info)
        return info
    found = cards()
    if not found:
        raise SystemExit("no SD card found; insert one and check with: diskutil list external")
    return found[prompt.choose("Card:", [describe(info) for info in found])]


def open_raw(disk: str, flags: int) -> int:
    dev = f"/dev/r{disk}"
    parent, child = socket.socketpair()
    with subprocess.Popen([AUTHOPEN, "-stdoutpipe", "-o", str(flags), dev], stdout=child.fileno()) as proc:
        child.close()
        _, fds, _, _ = socket.recv_fds(parent, 1024, 1)
        parent.close()
    if not fds:
        raise SystemExit(f"authopen did not open {dev} (exit {proc.returncode}); authorization denied?")
    return fds[0]


def unmount(disk: str) -> None:
    subprocess.run(["diskutil", "unmountDisk", "force", disk], check=True, capture_output=True)


def eject(disk: str) -> None:
    subprocess.run(["diskutil", "eject", disk], check=True, capture_output=True)


def mount_partition(disk: str, number: int = 1, timeout: float = 60) -> tuple[Path, str]:
    """Mounts the disk and returns the partition's mount point and volume name."""
    subprocess.run(["diskutil", "mountDisk", disk], capture_output=True, check=False)
    deadline = time.monotonic() + timeout
    while True:
        info = disk_info(f"{disk}s{number}")
        if info.get("MountPoint"):
            return Path(info["MountPoint"]), info.get("VolumeName", "")
        if time.monotonic() > deadline:
            raise SystemExit(f"{disk}s{number} did not mount")
        time.sleep(1)
