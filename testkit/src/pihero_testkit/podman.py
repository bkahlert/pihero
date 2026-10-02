"""Systemd-enabled podman containers as an install target for the packages."""

import hashlib
import subprocess
import time
import uuid
from importlib.resources import files
from pathlib import Path

import testinfra

from .tools import PODMAN

TIER1_DIR = Path(str(files("pihero_testkit") / "tier1"))
# dpkg's architecture is baked into the image; `uname -m` is no discriminator, since an arm64 kernel runs armhf natively and reports aarch64.
ARCHITECTURES = {"linux/arm64": "arm64", "linux/arm/v7": "armhf"}


def installable(debs: list[Path], platform: str) -> list[Path]:
    """The debs apt can install on the platform: architecture-independent ones and those built for its architecture."""
    architectures = {"all", ARCHITECTURES[platform]}
    return [deb for deb in debs if deb.stem.rsplit("_", 1)[1] in architectures]


def image_tag(platform: str, context: Path = TIER1_DIR) -> str:
    """The tag carries a digest of the build context, so a changed Containerfile or fixture is rebuilt on first use."""
    digest = hashlib.sha256()
    for path in sorted(p for p in context.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(context)).encode())
        digest.update(path.read_bytes())
    return f"localhost/pihero-tier1:{digest.hexdigest()[:12]}-{platform.removeprefix('linux/').replace('/', '-')}"


def image_for(platform: str) -> str:
    tag = image_tag(platform)
    if subprocess.run([*PODMAN, "image", "exists", tag], check=False).returncode != 0:
        # The default OCI format drops HEALTHCHECK.
        subprocess.run([*PODMAN, "build", "--format", "docker", "--platform", platform, "-t", tag, "-f", str(TIER1_DIR / "Containerfile"), str(TIER1_DIR)], check=True)
    return tag


class SystemdContainer:
    def __init__(self, platform: str, dist: Path, debs: list[Path]):
        self.platform = platform
        self.dist = dist
        self.debs = debs
        self.name = f"pihero-t1-{uuid.uuid4().hex[:8]}"
        self.host = None

    def start(self) -> "SystemdContainer":
        subprocess.run(
            [*PODMAN, "run", "-d", "--rm", "--systemd=always", "--platform", self.platform, "--name", self.name,
             "-v", f"{self.dist}:/dist:ro", image_for(self.platform)],
            check=True, stdout=subprocess.DEVNULL,
        )
        self._wait_ready()
        # A wrong-arch base image under the right tag would pass every test vacuously.
        architecture = self.exec("dpkg", "--print-architecture").stdout.strip()
        if architecture != ARCHITECTURES.get(self.platform):
            raise RuntimeError(f"{self.name}: image architecture is {architecture}, expected {ARCHITECTURES.get(self.platform)} for {self.platform}")
        self.host = testinfra.get_host(f"podman://{self.name}", sudo=True)
        return self

    def _wait_ready(self, timeout: int = 120) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = subprocess.run([*PODMAN, "exec", self.name, "systemctl", "is-system-running"], capture_output=True, text=True, check=False).stdout.strip()
            if state in ("running", "degraded"):
                return
            time.sleep(1)
        raise TimeoutError(f"{self.name}: systemd did not reach running/degraded within {timeout}s")

    def exec(self, *cmd: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run([*PODMAN, "exec", self.name, *cmd], check=check, capture_output=True, text=True)

    def _apt(self, *args: str) -> None:
        self.exec("env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-y", "-q", *args)

    def install(self, debs: list[Path]) -> None:
        self._apt("update")
        self._apt("install", *[f"/dist/{deb.name}" for deb in installable(debs, self.platform)])

    def install_extra(self, names: list[str]) -> None:
        self._apt("install", *names)

    def remove(self, names: list[str]) -> None:
        self._apt("remove", *names)

    def purge(self, names: list[str]) -> None:
        self._apt("purge", *names)

    def reinstall(self) -> None:
        # The published repository may carry a deb of the same version as a local build; apt calls installing the
        # local one over it a downgrade and refuses it under -y without the flag.
        self._apt("install", "--reinstall", "--allow-downgrades", *[f"/dist/{deb.name}" for deb in installable(self.debs, self.platform)])

    def reboot(self) -> None:
        return None

    def stop(self) -> None:
        subprocess.run([*PODMAN, "rm", "-f", self.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
