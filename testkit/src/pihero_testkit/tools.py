"""Runs commands in pinned container images, the tools image by default, building an image on first use."""

import hashlib
import os
import platform
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

PODMAN = os.environ.get("PODMAN", "podman").split()
CONTAINERFILE = Path(str(files("pihero_testkit") / "tools" / "Containerfile"))

_HOST_ARCH_TO_PLATFORM = {"arm64": "linux/arm64", "aarch64": "linux/arm64", "x86_64": "linux/amd64", "amd64": "linux/amd64"}
# Pinned to the host arch: a cross-arch pull can leave a wrong-arch image under the same
# tag locally, and `podman build` by tag then silently reuses it (tier-2 spike finding).
HOST_PLATFORM = _HOST_ARCH_TO_PLATFORM[platform.machine()]


def image(containerfile: Path = CONTAINERFILE) -> str:
    digest = hashlib.sha256(containerfile.read_bytes()).hexdigest()[:12]
    return f"localhost/pihero-{containerfile.parent.name}:{digest}"


def ensure_image(containerfile: Path = CONTAINERFILE, platform: str = HOST_PLATFORM) -> str:
    tag = image(containerfile)
    exists = subprocess.run([*PODMAN, "image", "exists", tag], check=False)
    if exists.returncode != 0:
        subprocess.run(
            [*PODMAN, "build", "--platform", platform, "-t", tag, "-f", str(containerfile), str(containerfile.parent)],
            check=True,
        )
    return tag


def command(
    args: list[str],
    *,
    workdir: str = "/work",
    env: dict[str, str] | None = None,
    privileged: bool = False,
    mounts: list[str] = (),
    image: str | None = None,
) -> list[str]:
    """Returns the podman command running `args` in `image`, the tools image by default, with the repository mounted at /work."""
    cmd = [*PODMAN, "run", "--rm", "-v", f"{Path.cwd()}:/work", "-w", workdir]
    for mount in mounts:
        cmd += ["-v", mount]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    if privileged:
        # podman populates /dev once at container start, so without a live bind mount
        # `losetup --partscan` never sees the loop and partition nodes it creates (tier-2 spike finding).
        cmd += ["--privileged", "-v", "/dev:/dev"]
    cmd += [image or ensure_image(), *args]
    return cmd


def run(
    args: list[str],
    *,
    workdir: str = "/work",
    env: dict[str, str] | None = None,
    privileged: bool = False,
    check: bool = True,
    capture: bool = False,
    mounts: list[str] = (),
    image: str | None = None,
) -> subprocess.CompletedProcess:
    cmd = command(args, workdir=workdir, env=env, privileged=privileged, mounts=mounts, image=image)
    return subprocess.run(cmd, check=check, text=True, capture_output=capture)


if __name__ == "__main__":
    print(ensure_image())
    sys.exit(0)
