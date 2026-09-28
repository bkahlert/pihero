"""Writes Raspberry Pi OS Lite onto an SD card and puts a device's cloud-init files on its boot partition.

macOS only. Writes are sector aligned and read back for verification.
"""

import hashlib
import lzma
import os
import re
import shutil
import sys
import time
from pathlib import Path

from . import prepare
from .disk import check_removable, disk_info, eject, mount_partition, open_raw, unmount

CHUNK = 4 << 20
SECTOR = 512
BOOT_LABEL = "bootfs"
DEVICE_FILES = ("user-data", "network-config", "meta-data")
REGULATORY_DOMAIN = re.compile(r"""^\s*regulatory-domain:\s*["']?(?P<code>[A-Z]{2})["']?\s*$""", re.MULTILINE)
CMDLINE_REGDOM = re.compile(r"\s*cfg80211\.ieee80211_regdom=\S*")


def device_dir(name: str) -> Path:
    path = Path(name) if Path(name).is_dir() else Path.cwd() / "devices" / name
    if not (path / "user-data").is_file():
        raise SystemExit(f"{path} has no user-data")
    return path


def write_image(fd: int, image: Path, report=lambda message: None) -> tuple[int, str]:
    """Streams the xz image onto fd in sector-aligned chunks. Returns size and sha256 of the uncompressed image."""
    digest = hashlib.sha256()
    total = 0
    started = time.monotonic()
    next_report = 256 << 20
    with lzma.open(image, "rb") as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
            total += len(chunk)
            chunk += b"\0" * (-len(chunk) % SECTOR)
            view = memoryview(chunk)
            while view:
                view = view[os.write(fd, view) :]
            if total >= next_report:
                report(f"written {total >> 20} MiB ({total / (time.monotonic() - started) / 1e6:.0f} MB/s)")
                next_report += 256 << 20
    return total, digest.hexdigest()


def read_back(fd: int, size: int) -> str:
    """Returns the sha256 of the first size bytes on fd, reading whole sectors as raw disks require."""
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    remaining = size + (-size % SECTOR)
    hashed = 0
    while remaining:
        data = os.read(fd, min(CHUNK, remaining))
        if not data:
            raise SystemExit(f"short read while verifying: {remaining} bytes left")
        remaining -= len(data)
        take = min(len(data), size - hashed)
        digest.update(data[:take])
        hashed += take
    return digest.hexdigest()


def mount_bootfs(disk: str) -> Path:
    mount_point, label = mount_partition(disk)
    if label != BOOT_LABEL:
        raise SystemExit(f"{disk}s1 is {label!r}, expected {BOOT_LABEL!r}")
    return mount_point


def copy_device_files(device: Path, bootfs: Path) -> list[str]:
    copied = []
    for name in DEVICE_FILES:
        if (device / name).is_file():
            shutil.copyfile(device / name, bootfs / name)
            copied.append(name)
    return copied


def regulatory_domain(network_config: str) -> str | None:
    match = REGULATORY_DOMAIN.search(network_config)
    return match["code"] if match else None


def with_regulatory_domain(cmdline: str, code: str) -> str:
    """Returns the one-line cmdline with cfg80211.ieee80211_regdom=<code> as its last word, replacing an earlier one."""
    return CMDLINE_REGDOM.sub("", cmdline.strip()) + f" cfg80211.ieee80211_regdom={code}\n"


def flash(device: Path, disk: str) -> None:
    info = disk_info(disk)
    check_removable(info)
    say(f"{disk}: {info.get('MediaName', '').strip()} {info.get('TotalSize', 0) / 1e9:.1f} GB")
    config = prepare.lock()["raspios"]
    image = prepare.download(config["url"], config["sha256"])
    unmount(disk)
    fd = open_raw(disk, os.O_RDWR)
    try:
        say(f"writing {image.name} ...")
        size, expected = write_image(fd, image, say)
        say(f"verifying {size >> 20} MiB ...")
        actual = read_back(fd, size)
    finally:
        os.close(fd)
    if actual != expected:
        raise SystemExit(f"verification failed: wrote {expected}, read {actual}")
    bootfs = mount_bootfs(disk)
    copied = copy_device_files(device, bootfs)
    say(f"copied {', '.join(copied)} from {device} to {bootfs}")
    # Raspberry Pi OS brings Wi-Fi up on the first boot only when the regulatory domain is already on the kernel command line;
    # netplan writes it there during that boot, too late. Imager does the same at flash time.
    code = regulatory_domain((device / "network-config").read_text()) if "network-config" in copied else None
    if code:
        cmdline = bootfs / "cmdline.txt"
        cmdline.write_text(with_regulatory_domain(cmdline.read_text(), code))
        say(f"set the Wi-Fi regulatory domain {code} in cmdline.txt")
    eject(disk)
    say(f"ejected {disk}; insert the card into the Raspberry Pi and power it on")


def say(message: str) -> None:
    print(f"  {message}", file=sys.stderr, flush=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m pihero_testkit.flash DEVICE DISK   (e.g. checkpoint disk9; see: diskutil list external)", file=sys.stderr)
        return 2
    if sys.platform != "darwin":
        print("flash is macOS only", file=sys.stderr)
        return 2
    flash(device_dir(argv[0]), argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
