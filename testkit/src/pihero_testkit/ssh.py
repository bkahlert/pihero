"""A real device over SSH as the tier-4 target. Mutating tests are skipped there by the plugin."""

from pathlib import Path

import testinfra


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
