"""Writes a backup image onto an SD card and verifies it.

macOS only. Restore is flash without the device files: the same authopen route, the same sector-aligned write, the same
read-back.
"""

import argparse
import lzma
import os
import re
import sys
import tomllib
from pathlib import Path

from . import disk, ghostty, prompt
from .backup import BACKUPS, sidecar_for
from .flash import read_back, say, write_image

IMAGE_HOST = re.compile(r"^(?P<host>.+)-\d{4}-\d{2}-\d{2}\.img\.xz$")


def image_host(image: Path) -> str | None:
    """Returns the host a backup image is named after, or None for a file not named `<host>-<date>.img.xz`."""
    match = IMAGE_HOST.match(image.name)
    return match["host"] if match else None


def sidecar(image: Path) -> dict | None:
    path = sidecar_for(image)
    if not path.is_file():
        return None
    try:
        meta = tomllib.loads(path.read_text())
        return {"size": int(meta["size"]), "sha256": str(meta["sha256"])}
    except (tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"{path} is not a valid sidecar: {error}") from None


def images(backups: Path = BACKUPS) -> list[Path]:
    """Returns the backup images, newest first."""
    return sorted(backups.glob("*.img.xz"), key=lambda path: path.stat().st_mtime, reverse=True)


def describe(image: Path) -> str:
    meta = sidecar(image)
    return f"{image.name}  needs a {meta['size'] / 1e9:.1f} GB card" if meta else f"{image.name}  (no sidecar)"


def image_for(path: str, backups: Path = BACKUPS) -> Path:
    """Returns the given image, or the one chosen from the images in backups when path is empty."""
    if path:
        image = Path(path)
        if not image.name.endswith(".img.xz"):
            raise SystemExit(f"{image} is not an .img.xz image")
        if not image.is_file():
            raise SystemExit(f"{image} not found")
        return image
    found = images(backups)
    if not found:
        raise SystemExit(f"no images in {backups}/; run make backup first")
    return found[prompt.choose("Image:", [describe(image) for image in found])]


def check_fits(info: dict, size: int) -> None:
    total = info.get("TotalSize", 0)
    if total < size:
        short = -(-(size - total) // (1 << 20))
        raise SystemExit(
            f"{info.get('DeviceIdentifier', '?')} holds {total / 1e9:.1f} GB, the image needs {size / 1e9:.1f} GB ({short} MiB short); use a larger card"
        )


def check(image: Path, info: dict) -> dict | None:
    """Returns the image's sidecar after checking that the card can hold it; None, with a warning, when there is no sidecar."""
    meta = sidecar(image)
    if meta:
        check_fits(info, meta["size"])
    else:
        say(f"no {sidecar_for(image).name} next to the image; skipping the size and integrity checks")
    return meta


def restore(image: Path, info: dict, meta: dict | None) -> None:
    ident = info["DeviceIdentifier"]
    total = info.get("TotalSize", 0)
    say(f"{ident}: {info.get('MediaName', '').strip()} {total / 1e9:.1f} GB")
    disk.unmount(ident)
    fd = disk.open_raw(ident, os.O_RDWR)
    try:
        say(f"writing {image.name} ...")
        try:
            size, written = write_image(fd, image, say)
        except (lzma.LZMAError, EOFError) as error:
            raise SystemExit(f"{image.name} is damaged: {error}") from None
        if meta and written != meta["sha256"]:
            raise SystemExit(f"{image.name} is damaged: its content hashes to {written}, the sidecar says {meta['sha256']}")
        say(f"verifying {size >> 20} MiB ...")
        read = read_back(fd, size)
    finally:
        os.close(fd)
    if read != written:
        raise SystemExit(f"verification failed: wrote {written}, read {read}")
    disk.eject(ident)
    say(f"ejected {ident}; insert the card into the Raspberry Pi and power it on")
    if total > size:
        say("the card is larger than the image, so the root filesystem keeps its old size; on the Pi run: sudo raspi-config --expand-rootfs && sudo reboot")
    if host := image_host(image):
        ghostty.forget(host, say)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Write a backup image onto an SD card and verify it.")
    parser.add_argument("--image", default="", help="path of the .img.xz; asked when empty")
    parser.add_argument("--disk", default="", help="disk identifier such as disk9; asked when empty")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("restore is macOS only", file=sys.stderr)
        return 2
    image = image_for(args.image)
    info = disk.card(args.disk)
    meta = check(image, info)
    if not (args.image and args.disk) and not prompt.confirm(f"Restore {image.name} onto {disk.describe(info)}?"):
        print("cancelled", file=sys.stderr)
        return 1
    restore(image, info, meta)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
