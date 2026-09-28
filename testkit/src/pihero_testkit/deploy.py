"""Installs the freshly built packages on a device over SSH, bypassing the apt repository."""

import subprocess
import sys

from . import build


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m pihero_testkit.deploy user@host", file=sys.stderr)
        return 2
    target = argv[0]
    debs = build.build_all(build.version_from_git())
    subprocess.run(["ssh", target, "rm -rf /tmp/pihero-deploy && mkdir -p /tmp/pihero-deploy"], check=True)
    subprocess.run(["scp", "-q", *map(str, debs), f"{target}:/tmp/pihero-deploy/"], check=True)
    subprocess.run(["ssh", target, "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --reinstall --allow-downgrades /tmp/pihero-deploy/*.deb"], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
