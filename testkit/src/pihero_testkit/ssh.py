"""A real device over SSH as the ssh target. The plugin skips mutating tests there, and the tests of packages the device lacks."""

import subprocess
from pathlib import Path

import testinfra

from . import deploy


# A device that reboots or drops off Wi-Fi mid-run would hang a session for the kernel's TCP timeout, two hours by
# default; three unanswered keepalives 15 s apart end it instead. testinfra adds its own ConnectTimeout.
KEEPALIVE = ["-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3"]


def command(uri: str, remote: str) -> list[str]:
    """Returns the ssh command that runs remote at uri (user@host[:port]) without prompting; exits on an empty uri."""
    if not uri:
        raise SystemExit("--target=ssh needs --target-uri=user@host[:port]")
    user_host, _, port = uri.partition(":")
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", *KEEPALIVE, *(["-p", port] if port else []), user_host, remote]


def installed_version(uri: str) -> str:
    result = subprocess.run(command(uri, "dpkg-query -W -f '${Version}' pihero"), capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit(f"cannot read the installed pihero version from {uri}: {result.stderr.strip() or 'not installed'}")
    return result.stdout.strip()


def installed_packages(uri: str) -> set[str]:
    """Returns the names of the packages dpkg reports installed at uri; exits when the device cannot be asked."""
    result = subprocess.run(command(uri, deploy.STATUS_QUERY), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"cannot list the packages installed on {uri}: {result.stderr.strip()}")
    return deploy.installed(result.stdout)


class SshTarget:
    def __init__(self, uri: str, debs: list[Path]):
        if not uri:
            raise SystemExit("--target=ssh needs --target-uri=user@host[:port]")
        self.uri = uri
        self.debs = debs
        self.host = testinfra.get_host(f"ssh://{uri}", sudo=True, ssh_extra_args=" ".join(KEEPALIVE))

    def install_extra(self, names: list[str]) -> None:
        self.host.check_output("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q " + " ".join(names))

    def purge(self, names: list[str]) -> None:
        raise RuntimeError("purge is not run against a real device")

    def reinstall(self) -> None:
        raise RuntimeError("reinstall is not run against a real device")

    def reboot(self) -> None:
        raise RuntimeError("reboot is not run against a real device")

    def stop(self) -> None:
        return None
