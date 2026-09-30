"""Reinstalls the freshly built packages a device already has, over SSH and bypassing the apt repository."""

import subprocess
import sys
from pathlib import Path

from . import build

STATUS_QUERY = "dpkg-query -W -f '${Package} ${db:Status-Abbrev}\\n'"


def installed(status: str) -> set[str]:
    names = set()
    for line in status.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1].startswith("ii"):
            names.add(fields[0])
    return names


def select(debs: list[Path], names: set[str]) -> list[Path]:
    return [deb for deb in debs if deb.name.split("_")[0] in names]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m pihero_testkit.deploy user@host", file=sys.stderr)
        return 2
    target = argv[0]
    debs = build.build_all(build.version_from_git())
    status = subprocess.run(["ssh", target, STATUS_QUERY], capture_output=True, text=True, check=True).stdout
    chosen = select(debs, installed(status))
    if not chosen:
        print(f"none of the built packages is installed on {target}; flash a device file to put Pi Hero on a fresh device", file=sys.stderr)
        return 2
    subprocess.run(["ssh", target, "rm -rf /tmp/pihero-deploy && mkdir -p /tmp/pihero-deploy"], check=True)
    subprocess.run(["scp", "-q", *map(str, chosen), f"{target}:/tmp/pihero-deploy/"], check=True)
    subprocess.run(["ssh", target, "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --reinstall --allow-downgrades /tmp/pihero-deploy/*.deb"], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
