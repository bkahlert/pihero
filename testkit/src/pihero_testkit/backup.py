"""Images an SD card into backups/<host>-<date>.img.xz with a sidecar naming the image's size and sha256.

macOS only. The card is opened read-only and never written.
"""

import argparse
import hashlib
import lzma
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

from . import disk, prompt
from .flash import CHUNK, hostname, say

BACKUPS = Path("backups")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PRESET = 0
REPORT_EVERY = 256 << 20


def card_hostname(ident: str) -> str | None:
    """Returns the hostname from the cloud-init user-data on the card's first partition, if there is one."""
    mount_point, _ = disk.mount_partition(ident)
    user_data = mount_point / "user-data"
    return hostname(user_data.read_text()) if user_data.is_file() else None


def image_name(host: str, day: date) -> str:
    if not NAME.match(host):
        raise SystemExit(f"{host!r} is not a valid name; use letters, digits, '.', '_', and '-'")
    return f"{host}-{day:%Y-%m-%d}.img.xz"


def sidecar_for(image: Path) -> Path:
    return image.with_name(image.name.removesuffix(".img.xz") + ".toml")


def dump(fd: int, image: Path, total: int, report=lambda message: None) -> tuple[int, str]:
    """Reads fd to its end into the xz image. Returns size and sha256 of the bytes read."""
    digest = hashlib.sha256()
    size = 0
    started = time.monotonic()
    next_report = REPORT_EVERY
    with lzma.open(image, "wb", preset=PRESET) as out:
        while chunk := os.read(fd, CHUNK):
            digest.update(chunk)
            out.write(chunk)
            size += len(chunk)
            if size >= next_report:
                report(f"read {size >> 20} MiB of {total >> 20} ({100 * size // total}%, {size / (time.monotonic() - started) / 1e6:.0f} MB/s)")
                next_report += REPORT_EVERY
    return size, digest.hexdigest()


def write_sidecar(image: Path, size: int, sha256: str) -> Path:
    sidecar = sidecar_for(image)
    sidecar.write_text(f"# Decompressed size and sha256 of {image.name}.\nsize = {size}\nsha256 = \"{sha256}\"\n")
    return sidecar


def backup(info: dict, host: str, day: date, backups: Path = BACKUPS) -> Path:
    ident = info["DeviceIdentifier"]
    image = backups / image_name(host, day)
    if image.exists():
        raise SystemExit(f"{image} exists; move it away or pass NAME=")
    backups.mkdir(exist_ok=True)
    total = info["TotalSize"]
    say(f"{ident}: {info.get('MediaName', '').strip()} {total / 1e9:.1f} GB")
    disk.unmount(ident)
    fd = disk.open_raw(ident, os.O_RDONLY)
    try:
        say(f"reading {ident} into {image} ...")
        size, sha256 = dump(fd, image, total, say)
    except BaseException:
        image.unlink(missing_ok=True)
        raise
    finally:
        os.close(fd)
    write_sidecar(image, size, sha256)
    disk.eject(ident)
    say(f"ejected {ident}; {image} restores onto a card of at least {size / 1e9:.1f} GB")
    return image


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Image an SD card into backups/<host>-<date>.img.xz.")
    parser.add_argument("--disk", default="", help="disk identifier such as disk9; asked when empty")
    parser.add_argument("--name", default="", help="name of the Pi; read from the card's user-data when empty")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("backup is macOS only", file=sys.stderr)
        return 2
    info = disk.card(args.disk)
    host = args.name or card_hostname(info["DeviceIdentifier"]) or prompt.ask("Name for this backup")
    backup(info, host, date.today())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
