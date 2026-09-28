"""A real device over SSH as the tier-4 target. Mutating tests are skipped there by the plugin."""

import subprocess
from pathlib import Path

import testinfra


def installed_version(uri: str) -> str:
    if not uri:
        raise SystemExit("--target=ssh needs --target-uri=user@host[:port]")
    user_host, _, port = uri.partition(":")
    cmd = ["ssh", "-o", "BatchMode=yes", *(["-p", port] if port else []), user_host, "dpkg-query -W -f '${Version}' pihero"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit(f"cannot read the installed pihero version from {uri}: {result.stderr.strip() or 'not installed'}")
    return result.stdout.strip()


class SshTarget:
    def __init__(self, uri: str, debs: list[Path]):
        if not uri:
            raise SystemExit("--target=ssh needs --target-uri=user@host[:port]")
        self.uri = uri
        self.debs = debs
        self.host = testinfra.get_host(f"ssh://{uri}", sudo=True)

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
