"""Prepares and caches the tier-2 base image: Raspberry Pi OS root filesystem plus Debian's arm64 kernel."""

import hashlib
import sys
import tomllib
import urllib.request
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from . import tools

PACKAGE_DIR = Path(str(files("pihero_testkit")))
LOCK = PACKAGE_DIR / "images.lock"
SCRIPT = PACKAGE_DIR / "prepare-rootfs"
CACHE = Path.home() / ".cache" / "pihero"
TIER2_IMAGE = "raspios_lite_arm64"


@dataclass(frozen=True)
class BaseImage:
    rootfs: Path
    kernel: Path
    initrd: Path
    boot: Path


def lock() -> dict:
    return tomllib.loads(LOCK.read_text())


def images() -> dict[str, dict]:
    """Returns the pinned Raspberry Pi OS images by name: every table of the lock with a url."""
    return {name: table for name, table in lock().items() if "url" in table}


def download(url: str, sha256: str) -> Path:
    dest = CACHE / "downloads" / url.rsplit("/", 1)[1]
    if not dest.exists() or _sha256(dest) != sha256:
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"  ↗ downloading {url}", file=sys.stderr)
        urllib.request.urlretrieve(url, dest)
        if _sha256(dest) != sha256:
            dest.unlink()
            raise RuntimeError(f"checksum mismatch for {url}")
    return dest


def prepare(force: bool = False) -> BaseImage:
    config = lock()
    raspios = config[TIER2_IMAGE]
    key = hashlib.sha256((raspios["sha256"] + config["kernel"]["package"] + SCRIPT.read_text()).encode()).hexdigest()[:12]
    out = CACHE / "base" / key
    if force or not (out / "done").exists():
        image = download(raspios["url"], raspios["sha256"])
        out.mkdir(parents=True, exist_ok=True)
        tools.run(
            ["/testkit/prepare-rootfs", "--image", f"/cache/downloads/{image.name}", "--out", f"/cache/base/{key}", "--kernel-package", config["kernel"]["package"]],
            privileged=True,
            mounts=[f"{CACHE}:/cache", f"{PACKAGE_DIR}:/testkit:ro"],
        )
        (out / "done").touch()
    return BaseImage(out / "rootfs.qcow2", out / "vmlinuz", out / "initrd.img", out / "boot")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    base = prepare(force="--force" in sys.argv)
    print(base.rootfs.parent)
    sys.exit(0)
