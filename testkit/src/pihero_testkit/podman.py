"""Systemd-enabled podman containers as an install target for the packages."""

import subprocess
import time
import uuid
from importlib.resources import files
from pathlib import Path

import testinfra

from .tools import PODMAN

TIER1_DIR = Path(str(files("pihero_testkit") / "tier1"))


def image_for(platform: str) -> str:
    tag = f"localhost/pihero-tier1:trixie-{platform.removeprefix('linux/').replace('/', '-')}"
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
        self._apt("install", *[f"/dist/{deb.name}" for deb in debs])

    def install_extra(self, names: list[str]) -> None:
        self._apt("install", *names)

    def remove(self, names: list[str]) -> None:
        self._apt("remove", *names)

    def purge(self, names: list[str]) -> None:
        self._apt("purge", *names)

    def reinstall(self) -> None:
        self._apt("install", "--reinstall", *[f"/dist/{deb.name}" for deb in self.debs])

    def reboot(self) -> None:
        return None

    def stop(self) -> None:
        subprocess.run([*PODMAN, "rm", "-f", self.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
