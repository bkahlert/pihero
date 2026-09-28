"""Reports whether the Mac-side tooling the harness needs is present and which versions it has."""

import shutil
import subprocess
import sys

TOOLS = {
    "podman": ["podman", "--version"],
    "qemu-system-aarch64": ["qemu-system-aarch64", "--version"],
    "qemu-img": ["qemu-img", "--version"],
    "uv": ["uv", "--version"],
    "ssh": ["ssh", "-V"],
    "git": ["git", "--version"],
}


def main() -> int:
    missing = []
    for name, cmd in TOOLS.items():
        if shutil.which(name) is None:
            print(f"  ✘ {name}: not found")
            missing.append(name)
            continue
        out = subprocess.run(cmd, capture_output=True, text=True, check=False)
        version = (out.stdout or out.stderr).strip().splitlines()[0]
        print(f"  ✔ {name}: {version}")
    machine = subprocess.run(["podman", "machine", "list", "--format", "{{.Name}} {{.Running}}"], capture_output=True, text=True, check=False)
    print(f"  ℹ podman machine: {machine.stdout.strip() or 'none'}")
    if missing:
        print(f"\nInstall with: brew bundle  (missing: {', '.join(missing)})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
