# Pi Hero 2 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the package build, the three-tier test harness, the release pipeline, the `pihero` core package, and `pihero-avahi`, so that every later feature is one more directory under `packages/`.

**Architecture:** Each feature is an architecture-independent Debian package built with nfpm from a file tree that mirrors the target filesystem. Devices are described by a cloud-init `user-data` file on the boot partition. Tests are pytest plus pytest-testinfra, run against a systemd podman container (tier 1) or a QEMU VM booted from the real Raspberry Pi OS root filesystem (tier 2); tier 0 is unit tests and static checks. This plan covers steps 1 to 3 of the spec's migration order: spikes, skeleton plus `pihero`, and `pihero-avahi`.

**Tech Stack:** Python 3.13 standard library on the device; uv, pytest, pytest-testinfra on the Mac; nfpm; podman; QEMU 11 with HVF; cloud-init; apt-ftparchive; GitHub Actions; GitHub Pages.

**Spec:** [docs/superpowers/specs/2026-09-27-pihero-packages-design.md](../specs/2026-09-27-pihero-packages-design.md)

## Global Constraints

- Every package is `Architecture: all` and depends only on packages present on both the 64-bit and 32-bit Raspberry Pi OS Trixie archives.
- On-device helpers are Python 3 standard library only, `#!/usr/bin/python3`, no pip. Shell appears only in `ExecStart=` lines and maintainer scripts.
- Package names: `pihero` core, `pihero-<feature>`. Units: `pihero-<feature>*.service`. Rendered files carry the `pihero-` prefix.
- Paths: executables `/usr/lib/pihero/`, data `/usr/share/pihero/<feature>/`, units `/usr/lib/systemd/system/`, device overrides `/etc/pihero/<feature>.conf` (never shipped by a package), state `/var/lib/pihero/`.
- Boot files live under `/boot/firmware/`. Postinst never reboots; it touches `/run/reboot-required` and appends to `/run/reboot-required.pkgs`.
- Removal is symmetric: purge deletes rendered `pihero-*` files and reverts boot config lines.
- All packages share one SemVer version from the git tag `vX.Y.Z`; version 2 starts at `2.0.0`.
- Tier budgets: tier 0 under 30 s, tier 1 under 2 min, tier 2 under 10 min.
- Linux-side tooling runs in one tools container pinned by digest. Mac-side tooling is `qemu`, `podman`, `uv` from a Brewfile. Upstream inputs are pinned in `images.lock`.
- Never commit on `master`. All work happens on branch `pihero-2`, created from `spec/packages-design`.
- Commit messages follow the existing repo style (`feat:`, `fix:`, `docs:`, `test:`, `chore:`) and end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Shell scripts follow the user's bash rules: extensionless, executable, `#!/usr/bin/env bash`, header with `Purpose:`/`Usage:`, `while`/`case` option parsing, `-h/--help`. Containerfiles declare `HEALTHCHECK`. Tests put test cases first and helpers last, names are claims.

## Review Focus

1. A `cmdline.txt` that contains a line break (a hand edit gone wrong) must make `pihero-bootconfig` refuse with exit 1 and leave the file untouched, not silently produce an unbootable file. Test in Task 5.
2. A `config.txt` where the same key appears under `[pi4]` and `[all]` must have only its `[all]` occurrence changed by `set --section all`. Test in Task 5.
3. A pretty hostname containing `&`, `<`, or non-ASCII characters (the owner uses `(ノಠ益ಠ)ノ彡 ⬬`) must produce valid, escaped XML that avahi accepts. Test in Task 13.
4. A machine without `/proc/device-tree/model` (every container, some VMs) must get a device-info record without `machine=` rather than a failed render unit. Test in Task 13.
5. A `MODEL` value containing `@`, `,` and `=` (`MacPro7,1@ECOLOR=226,226,224`) must survive the environment file unquoted and reach the TXT record unchanged. Test in Task 13 and Task 14.

---

## Task 1: Spike — tools container and systemd containers under podman

Answers, before anything is built on them: can podman on this Mac build the tools image, run a systemd-as-PID-1 Debian Trixie container for `linux/arm64` and `linux/arm/v7`, install a `.deb` into it, and can testinfra talk to it. Throwaway; the deliverable is a findings file.

**Files:**
- Create: `docs/spikes/2026-09-27-tier1-podman.md`

- [ ] **Step 1: Create the branch**

```bash
git switch spec/packages-design && git switch -c pihero-2
```

- [ ] **Step 2: Check podman machine and binfmt for arm/v7**

```bash
podman machine list
podman run --rm --platform linux/arm64 docker.io/library/debian:trixie-slim uname -m
podman run --rm --platform linux/arm/v7 docker.io/library/debian:trixie-slim uname -m
```

Expected: `aarch64` then `armv7l`. If the second fails with `exec format error`, record that and try `podman machine ssh sudo rpm-ostree install qemu-user-static` followed by `podman machine stop && podman machine start`, then retry.

- [ ] **Step 3: Run a systemd container**

```bash
cat > /tmp/pihero-spike.Containerfile <<'CF'
FROM docker.io/library/debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv dbus ca-certificates apt-utils python3 iproute2 \
 && rm -rf /var/lib/apt/lists/* \
 && systemctl mask systemd-udevd.service systemd-udevd-kernel.socket systemd-udevd-control.socket systemd-udev-trigger.service getty.target console-getty.service systemd-firstboot.service
HEALTHCHECK --interval=5s --timeout=3s CMD systemctl is-active --quiet multi-user.target
CMD ["/sbin/init"]
CF
podman build --platform linux/arm64 -t pihero-spike:arm64 -f /tmp/pihero-spike.Containerfile /tmp
podman run -d --rm --systemd=always --platform linux/arm64 --name spike1 pihero-spike:arm64
sleep 5; podman exec spike1 systemctl is-system-running
podman exec spike1 systemctl show --property=RuntimeWatchdogUSec
```

Expected: `running` or `degraded`, and a `RuntimeWatchdogUSec=` line. Record the exact value of `is-system-running` and which units are failed (`podman exec spike1 systemctl --failed`).

- [ ] **Step 4: Install a .deb and query it with testinfra**

```bash
podman exec spike1 sh -c 'apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q avahi-daemon avahi-utils'
podman exec spike1 systemctl is-active avahi-daemon
podman exec spike1 avahi-browse -rpt _workstation._tcp
uvx --from pytest-testinfra --with pytest python -c "import testinfra; h=testinfra.get_host('podman://spike1'); print(h.package('avahi-daemon').is_installed, h.service('avahi-daemon').is_running)"
podman rm -f spike1
```

Expected: `active`, `True True`. Record whether `avahi-browse` shows anything (it needs a non-loopback interface with multicast; note the interface list from `podman exec spike1 ip -o link`). Repeat steps 3 and 4 with `--platform linux/arm/v7` and tag `arm32v7`.

- [ ] **Step 5: Write the findings**

`docs/spikes/2026-09-27-tier1-podman.md` with these headings and one to three lines each: `arm/v7 works` (yes/no, what was needed), `systemd container state` (running/degraded, failed units), `RuntimeWatchdogUSec in a container`, `avahi-browse inside a container` (what it printed), `testinfra podman backend` (worked or not), `Decisions for Task 8` (masked units to add, `PODMAN` prefix needed or not).

- [ ] **Step 6: Commit**

```bash
git add docs/spikes/2026-09-27-tier1-podman.md
git commit -m "docs: spike findings for tier-1 podman systemd containers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 2: Spike — Raspberry Pi OS root filesystem with Debian's kernel under QEMU

The biggest technical risk in the spec. Answers: does the Raspberry Pi OS Lite arm64 rootfs boot in `qemu-system-aarch64 -M virt -accel hvf` with Debian's kernel, does a FAT image labelled `bootfs` get mounted at `/boot/firmware`, does cloud-init consume `user-data` from it, can apt install from an HTTP server on the Mac, and what do `rpi: enable_usb_gadget: true` and `btvirt` do. Throwaway scripts live in the scratchpad; the deliverable is a findings file and the stock boot files.

**Files:**
- Create: `docs/spikes/2026-09-27-tier2-vm.md`
- Create: `testkit/src/pihero_testkit/tier1/boot/config.txt` (stock file, copied out)
- Create: `testkit/src/pihero_testkit/tier1/boot/cmdline.txt` (stock file, copied out)

- [ ] **Step 1: Find and download the current Raspberry Pi OS Lite arm64 image**

```bash
curl -s https://downloads.raspberrypi.com/raspios_lite_arm64/images/ | grep -o 'raspios_lite_arm64-[0-9-]*/' | sort | tail -1
```

Take the newest directory `D`, then:

```bash
D=raspios_lite_arm64-YYYY-MM-DD   # from the previous command
curl -s "https://downloads.raspberrypi.com/raspios_lite_arm64/images/$D/" | grep -o '[0-9-]*-raspios-trixie-arm64-lite.img.xz' | head -1
```

Record `URL` and download `URL` and `URL.sha256` into `~/.cache/pihero/downloads/`, verify with `shasum -a 256 -c`.

- [ ] **Step 2: Prepare the rootfs inside a privileged tools container**

Build a throwaway tools image:

```bash
cat > /tmp/pihero-tools-spike.Containerfile <<'CF'
FROM docker.io/library/debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates xz-utils util-linux mount fdisk e2fsprogs dosfstools mtools qemu-utils && rm -rf /var/lib/apt/lists/*
HEALTHCHECK NONE
CMD ["bash"]
CF
podman build -t pihero-tools-spike -f /tmp/pihero-tools-spike.Containerfile /tmp
podman run --rm -it --privileged -v ~/.cache/pihero:/cache pihero-tools-spike bash
```

Inside the container, run these one block at a time and record which fail:

```bash
IMG=/cache/downloads/$(ls /cache/downloads | grep img.xz$ | head -1)
mkdir -p /cache/spike && xz -dc "$IMG" > /cache/spike/raspios.img
loop=$(losetup --find --show --partscan /cache/spike/raspios.img); echo "$loop"; ls "${loop}"p*
mkdir -p /mnt/root && mount "${loop}p2" /mnt/root && mount "${loop}p1" /mnt/root/boot/firmware
mkdir -p /cache/spike/boot && cp /mnt/root/boot/firmware/{config.txt,cmdline.txt} /cache/spike/boot/
cat /mnt/root/etc/fstab; cat /mnt/root/etc/cloud/cloud.cfg.d/99*; ls /mnt/root/etc/cloud/cloud.cfg.d/
for m in proc sys dev dev/pts; do mount --bind "/$m" "/mnt/root/$m"; done
cp --remove-destination /etc/resolv.conf /mnt/root/etc/resolv.conf
chroot /mnt/root env DEBIAN_FRONTEND=noninteractive apt-get update -q
chroot /mnt/root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends linux-image-arm64
ls /mnt/root/boot/
sed -i -E 's|^PARTUUID=[^ ]+-01 |LABEL=bootfs |; s|^PARTUUID=[^ ]+-02 |LABEL=rootfs |' /mnt/root/etc/fstab
install -d /mnt/root/etc/systemd/system/cloud-init-local.service.d
printf '[Unit]\nRequiresMountsFor=/boot/firmware\n' > /mnt/root/etc/systemd/system/cloud-init-local.service.d/pihero-bootfs.conf
cp "$(ls /mnt/root/boot/vmlinuz-*-arm64 | sort -V | tail -1)" /cache/spike/vmlinuz
cp "$(ls /mnt/root/boot/initrd.img-*-arm64 | sort -V | tail -1)" /cache/spike/initrd.img
for m in dev/pts dev sys proc boot/firmware; do umount "/mnt/root/$m"; done
truncate -s 6G /cache/spike/rootfs.img && mkfs.ext4 -q -L rootfs -d /mnt/root /cache/spike/rootfs.img
umount /mnt/root && losetup -d "$loop"
qemu-img convert -f raw -O qcow2 /cache/spike/rootfs.img /cache/spike/rootfs.qcow2 && rm /cache/spike/rootfs.img
```

Record: whether `losetup` works in the privileged container (if not, note the error; the fallback is `debugfs -R "rdump / /mnt/root" <partition image extracted with dd>` and copying the boot files with `mcopy -i`), whether the kernel install fails in the `raspi-firmware` hook and what fixed it, the exact contents of `99*.cfg`, and the sizes of `vmlinuz` and `initrd.img`.

- [ ] **Step 3: Build a bootfs image with a test device file**

On the Mac:

```bash
mkdir -p ~/.cache/pihero/spike/dev && cd ~/.cache/pihero/spike/dev
ssh-keygen -t ed25519 -N '' -f spike-key -C spike >/dev/null
cat > user-data <<EOF
#cloud-config
hostname: spike
manage_etc_hosts: true
enable_ssh: true
ssh_pwauth: false
users:
  - name: pihero
    groups: users,adm,sudo
    shell: /bin/bash
    lock_passwd: true
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - $(cat spike-key.pub)
package_update: true
apt:
  sources:
    pihero-local:
      source: deb [trusted=yes] http://10.0.2.2:8000/ ./
packages: [avahi-utils]
rpi:
  enable_usb_gadget: true
runcmd:
  - hostnamectl set-hostname --pretty "Spike"
power_state:
  mode: reboot
  condition: test -f /run/reboot-required
EOF
printf 'instance-id: spike-1\nlocal-hostname: spike\n' > meta-data
podman run --rm -v ~/.cache/pihero/spike:/s pihero-tools-spike sh -c 'rm -f /s/bootfs.img && mkfs.vfat -n bootfs -C /s/bootfs.img 65536 >/dev/null && mcopy -i /s/bootfs.img /s/boot/config.txt /s/boot/cmdline.txt /s/dev/user-data /s/dev/meta-data ::/ && mtype -i /s/bootfs.img ::/cmdline.txt'
```

Record the stock `cmdline.txt` line printed at the end.

- [ ] **Step 4: Serve an empty flat repo and boot**

```bash
mkdir -p ~/.cache/pihero/spike/repo && cd ~/.cache/pihero/spike/repo
podman run --rm -v "$PWD":/r pihero-tools-spike sh -c 'apt-get update -q >/dev/null && apt-get install -y -q apt-utils >/dev/null && cd /r && apt-ftparchive packages . > Packages && gzip -kf Packages && apt-ftparchive release . > Release'
(python3 -m http.server 8000 --bind 127.0.0.1 >/dev/null 2>&1 &)
cd ~/.cache/pihero/spike
qemu-img create -q -f qcow2 -b rootfs.qcow2 -F qcow2 overlay.qcow2
CMDLINE=$(podman run --rm -v "$PWD":/s pihero-tools-spike mtype -i /s/bootfs.img ::/cmdline.txt)
APPEND="root=LABEL=rootfs console=ttyAMA0,115200 $(echo "$CMDLINE" | tr ' ' '\n' | grep -vE '^(root=|console=|init=)' | tr '\n' ' ')"
qemu-system-aarch64 -M virt -accel hvf -cpu host -m 1024 -smp 2 -no-reboot -display none -monitor none \
  -kernel vmlinuz -initrd initrd.img -append "$APPEND" \
  -drive if=none,file=overlay.qcow2,format=qcow2,id=root -device virtio-blk-pci,drive=root \
  -drive if=none,file=bootfs.img,format=raw,id=boot -device virtio-blk-pci,drive=boot \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22 -device virtio-net-pci,netdev=net0 \
  -device virtio-rng-pci -serial file:serial.log &
sleep 60; tail -n 30 serial.log
ssh -i dev/spike-key -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null pihero@127.0.0.1 'cloud-init status --wait --long; findmnt /boot/firmware; hostnamectl; apt-cache policy | grep -A1 10.0.2.2; systemctl --failed; journalctl -u rpi-usb-gadget* --no-pager | tail -n 20; sudo apt-get install -y bluez-test-tools && ls /usr/bin/btvirt'
```

If QEMU exits (the `power_state` reboot), re-run the `qemu-system-aarch64` command and repeat the `ssh`. Record: time to SSH, `cloud-init status` result and `errors:`, whether `/boot/firmware` is the bootfs image, whether the apt source is known, failed units, what `rpi: enable_usb_gadget` did without dwc2 (unit state, whether the `USB Gadget (shared)` NetworkManager profile exists via `nmcli -g NAME connection show`), and whether `btvirt` exists. Kill QEMU and the HTTP server afterwards.

- [ ] **Step 5: Copy the stock boot files into the repo and write the findings**

```bash
mkdir -p testkit/src/pihero_testkit/tier1/boot
cp ~/.cache/pihero/spike/boot/config.txt ~/.cache/pihero/spike/boot/cmdline.txt testkit/src/pihero_testkit/tier1/boot/
```

`docs/spikes/2026-09-27-tier2-vm.md` with headings: `Image` (URL, sha256), `Loop devices in privileged podman`, `Kernel install in chroot` (hook behaviour, fix), `Boot` (time to SSH, kernel line used), `bootfs mount and cloud-init` (status, errors, seed path), `Local apt repo`, `rpi: enable_usb_gadget without hardware`, `btvirt`, `Decision` (go with Raspberry Pi OS rootfs, or fall back to the Debian cloud image, and why), `Adjustments for Task 10` (exact substitutions the harness must make to `cmdline.txt`, masked units, timeouts).

- [ ] **Step 6: Commit**

```bash
git add docs/spikes/2026-09-27-tier2-vm.md testkit/src/pihero_testkit/tier1/boot
git commit -m "docs: spike findings for the tier-2 QEMU VM; stock boot files

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 3: Repository skeleton

The uv workspace, the testkit package stub with the script loader, the Makefile, the Brewfile, the tools Containerfile, and the doctor command. Ends with `make doctor` and `make tools` working and one unit test passing.

**Files:**
- Create: `pyproject.toml`, `Brewfile`, `Makefile`, `.gitignore` (append if present)
- Create: `testkit/pyproject.toml`
- Create: `testkit/src/pihero_testkit/__init__.py`, `scripts.py`, `tools.py`, `doctor.py`
- Create: `testkit/src/pihero_testkit/tools/Containerfile`
- Create: `testkit/tests/test_scripts.py`
- Create: `docs/app-conventions.md`

**Interfaces:**
- Produces: `pihero_testkit.scripts.load_script(path: Path) -> ModuleType`; `pihero_testkit.tools.run(args: list[str], *, workdir: str = "/work", env: dict | None = None, privileged: bool = False, check: bool = True, capture: bool = False, mounts: list[str] = ()) -> subprocess.CompletedProcess`; `pihero_testkit.tools.ensure_image() -> str`; `pihero_testkit.tools.PODMAN: list[str]`.

- [ ] **Step 1: Root project files**

`pyproject.toml`:

```toml
[project]
name = "pihero-dev"
version = "0.0.0"
description = "Development environment for Pi Hero packages and their tests"
requires-python = ">=3.13"

[tool.uv]
package = false

[tool.uv.workspace]
members = ["testkit"]

[tool.uv.sources]
pihero-testkit = { workspace = true }

[dependency-groups]
dev = ["pihero-testkit"]

[tool.pytest.ini_options]
testpaths = ["packages", "testkit/tests"]
addopts = "-p pihero_testkit.plugin --import-mode=importlib -ra"
```

`Brewfile`:

```ruby
brew "qemu"
brew "podman"
brew "uv"
```

Append to `.gitignore` (create it if missing):

```gitignore
dist/
packages/*/.build/
.venv/
__pycache__/
.pytest_cache/
devices/*
!devices/sample/
!devices/README.md
```

`Makefile` (recipe lines start with a tab):

```make
SHELL := /bin/bash
.DEFAULT_GOAL := help

PLATFORM ?= linux/arm64
QEMU_ACCEL ?= hvf
TARGET ?=
UV := uv run --frozen

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

doctor: ## check host tooling
	@$(UV) python -m pihero_testkit.doctor

tools: ## build the tools container image
	@$(UV) python -m pihero_testkit.tools

build: ## build all .deb packages into dist/
	@$(UV) python -m pihero_testkit.build

test-tier0: ## unit tests and static checks
	@$(UV) pytest -m tier0

test-tier1: ## install packages into a systemd container and test
	@$(UV) pytest -m installed --target=podman --platform=$(PLATFORM)

test-tier2: ## boot a VM from a device file and test
	@$(UV) pytest -m 'installed or boot' --target=vm --qemu-accel=$(QEMU_ACCEL)

test: test-tier0 test-tier1 ## tiers 0 and 1

test-all: test-tier0 test-tier1 test-tier2 ## tiers 0 to 2

vm-prepare: ## build and cache the tier-2 base image
	@$(UV) python -m pihero_testkit.prepare

vm: ## boot the tier-2 VM and keep it running for inspection
	@$(UV) python -m pihero_testkit.vm --keep --qemu-accel=$(QEMU_ACCEL)

deploy: build ## install built packages on TARGET over SSH
	@test -n "$(TARGET)" || { echo "usage: make deploy TARGET=host"; exit 2; }
	@$(UV) python -m pihero_testkit.deploy "$(TARGET)"

clean: ## remove build outputs
	rm -rf dist packages/*/.build
```

- [ ] **Step 2: Testkit package**

`testkit/pyproject.toml`:

```toml
[project]
name = "pihero-testkit"
version = "2.0.0"
description = "Test harness for Pi Hero packages: build, podman, QEMU VM, testinfra fixtures"
requires-python = ">=3.13"
dependencies = ["pytest>=8.3", "pytest-testinfra>=10.1"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pihero_testkit"]
```

`testkit/src/pihero_testkit/__init__.py`: empty.

`testkit/src/pihero_testkit/scripts.py`:

```python
"""Imports extensionless Python scripts, such as /usr/lib/pihero/bootconfig, as modules for unit tests."""

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType


def load_script(path: Path) -> ModuleType:
    name = f"pihero_script_{path.name}_{abs(hash(str(path.resolve())))}"
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module
```

`testkit/src/pihero_testkit/tools.py`:

```python
"""Runs commands in the pinned tools container, building its image on first use."""

import hashlib
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

PODMAN = os.environ.get("PODMAN", "podman").split()
CONTAINERFILE = Path(str(files("pihero_testkit") / "tools" / "Containerfile"))


def image() -> str:
    digest = hashlib.sha256(CONTAINERFILE.read_bytes()).hexdigest()[:12]
    return f"localhost/pihero-tools:{digest}"


def ensure_image() -> str:
    tag = image()
    exists = subprocess.run([*PODMAN, "image", "exists", tag], check=False)
    if exists.returncode != 0:
        subprocess.run(
            [*PODMAN, "build", "-t", tag, "-f", str(CONTAINERFILE), str(CONTAINERFILE.parent)],
            check=True,
        )
    return tag


def run(
    args: list[str],
    *,
    workdir: str = "/work",
    env: dict[str, str] | None = None,
    privileged: bool = False,
    check: bool = True,
    capture: bool = False,
    mounts: list[str] = (),
) -> subprocess.CompletedProcess:
    cmd = [*PODMAN, "run", "--rm", "-v", f"{Path.cwd()}:/work", "-w", workdir]
    for mount in mounts:
        cmd += ["-v", mount]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    if privileged:
        cmd.append("--privileged")
    cmd += [ensure_image(), *args]
    return subprocess.run(cmd, check=check, text=True, capture_output=capture)


if __name__ == "__main__":
    print(ensure_image())
    sys.exit(0)
```

`testkit/src/pihero_testkit/doctor.py`:

```python
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
```

- [ ] **Step 3: Tools Containerfile**

Look up the two pinned values first:

```bash
podman pull docker.io/library/debian:trixie-slim && podman image inspect --format '{{ index .RepoDigests 0 }}' docker.io/library/debian:trixie-slim
podman run --rm docker.io/library/debian:trixie-slim bash -c "apt-get update -qq && apt-get install -y -qq ca-certificates >/dev/null && echo 'deb [trusted=yes] https://repo.goreleaser.com/apt/ /' > /etc/apt/sources.list.d/g.list && apt-get update -qq && apt-cache madison nfpm | head -1"
```

`testkit/src/pihero_testkit/tools/Containerfile`, with the digest and the nfpm version from above:

```dockerfile
# Pi Hero tools: every Linux-side tool the build and the tests need, pinned.
FROM docker.io/library/debian:trixie-slim@sha256:DIGEST_FROM_STEP_3
ARG NFPM_VERSION=VERSION_FROM_STEP_3
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg \
      apt-utils dpkg-dev shellcheck systemd cloud-init python3 python3-yaml \
      mtools dosfstools e2fsprogs xz-utils util-linux mount fdisk qemu-utils \
    && rm -rf /var/lib/apt/lists/*
RUN echo 'deb [trusted=yes] https://repo.goreleaser.com/apt/ /' > /etc/apt/sources.list.d/goreleaser.list \
    && apt-get update && apt-get install -y --no-install-recommends "nfpm=${NFPM_VERSION}" \
    && rm -rf /var/lib/apt/lists/*
# One-shot tool image run with `podman run --rm`; there is no long-running service to probe.
HEALTHCHECK NONE
CMD ["bash"]
```

- [ ] **Step 4: App conventions doc**

`docs/app-conventions.md`:

```markdown
# Application unit conventions

Apps run as systemd services installed by their own Debian package. Pi Hero packages never depend on app units.

    [Unit]
    Description=My App
    After=network-online.target
    Wants=network-online.target

    [Service]
    User=myapp
    Group=myapp
    ExecStart=/usr/lib/myapp/run
    Restart=always
    RestartSec=5
    MemoryMax=200M
    NoNewPrivileges=yes
    ProtectSystem=strict
    StateDirectory=myapp

    [Install]
    WantedBy=multi-user.target

- One dedicated system user per app, created in `postinst` with `adduser --system --group --no-create-home`.
- `Restart=always` so a crash never leaves the device without its app; `MemoryMax=` so a leak never starves sshd.
- Hardware access through group membership (`spi`, `gpio`, `i2c`, `video`), never by running as root.
- Configuration overrides in `/etc/<app>/<app>.conf` as `KEY=VALUE`, read with `EnvironmentFile=-`.
- Tests depend on `pihero-testkit` pinned to a tag and reuse its tiers; the app's tier-2 device file adds the app's apt source to a copy of the `all-features` device.
```

- [ ] **Step 5: Write the failing unit test for the script loader**

`testkit/tests/test_scripts.py`:

```python
from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0


class TestLoadScript:
    def test_exposes_functions_of_an_extensionless_script(self, tmp_path):
        script = tmp_path / "tool"
        script.write_text("def answer():\n    return 42\n\nif __name__ == '__main__':\n    raise SystemExit(answer())\n")

        module = load_script(script)

        assert module.answer() == 42

    def test_does_not_run_the_main_guard(self, tmp_path):
        script = tmp_path / "tool"
        script.write_text("if __name__ == '__main__':\n    raise SystemExit(3)\n")

        module = load_script(script)

        assert module.__name__.startswith("pihero_script_tool_")
```

- [ ] **Step 6: Install the environment and run the test**

```bash
brew bundle --no-lock
uv sync
uv run pytest testkit/tests/test_scripts.py -v
```

Expected: `pytest` fails to start because `pihero_testkit.plugin` does not exist yet (`-p pihero_testkit.plugin`). Create a minimal plugin so the run proceeds:

`testkit/src/pihero_testkit/plugin.py`:

```python
"""pytest plugin: markers shared by all Pi Hero tests. Target fixtures are added in later tasks."""


def pytest_configure(config):
    config.addinivalue_line("markers", "tier0: runs on the Mac against fixtures and the tools container, no target")
    config.addinivalue_line("markers", "installed: runs against any target with the packages installed (podman, vm, ssh)")
    config.addinivalue_line("markers", "boot: cross-cutting checks that need a booted VM or device (vm, ssh)")
    config.addinivalue_line("markers", "mutating: changes the target's state; skipped on --target=ssh")
```

Run again: `uv run pytest testkit/tests/test_scripts.py -v`. Expected: 2 passed.

- [ ] **Step 7: Verify doctor and tools**

```bash
make doctor
make tools
```

Expected: every tool marked `✔`, and `localhost/pihero-tools:<hash>` printed after a successful build.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock Brewfile Makefile .gitignore testkit docs/app-conventions.md
git commit -m "chore: uv workspace, testkit stub, Makefile, tools container

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 4: Package build pipeline

`pihero_testkit.build` discovers `packages/*/nfpm.yaml`, generates the Debian maintainer scripts from `units.txt` and hook fragments, derives the version from git, and runs nfpm in the tools container. A throwaway package proves the pipeline end to end; it is deleted again at the end of the task.

**Files:**
- Create: `testkit/src/pihero_testkit/maintscripts.py`, `testkit/src/pihero_testkit/build.py`
- Create: `testkit/tests/test_maintscripts.py`, `testkit/tests/test_build.py`

**Interfaces:**
- Produces: `build.version_from_git() -> str`; `build.discover() -> list[Path]`; `build.build(pkg_dir: Path, version: str) -> Path` (the `.deb`); `build.build_all(version: str) -> list[Path]`; `build.DIST: Path` (`<cwd>/dist`); `maintscripts.write(pkg_dir: Path) -> None` writing `pkg_dir/.build/{postinst,prerm,postrm}`.
- Package directory contract consumed by later tasks: `nfpm.yaml` with `scripts:` pointing at `.build/…`; optional `units.txt` (one unit name per line, `#` comments); optional fragments `scripts/postinst.sh` (runs on configure before units are enabled), `scripts/prerm.sh` (runs on remove after units are stopped), `scripts/postrm.sh` (runs on purge only). Fragments are POSIX sh without a shebang, starting with `# shellcheck shell=sh`.

- [ ] **Step 1: Write the failing tests for maintainer script generation**

`testkit/tests/test_maintscripts.py`:

```python
import pytest

from pihero_testkit import maintscripts, tools

pytestmark = pytest.mark.tier0


class TestPostinst:
    def test_enables_and_restarts_each_unit(self):
        script = maintscripts.postinst(["a.service", "b.service"], fragment="")

        assert "deb-systemd-helper enable 'a.service'" in script
        assert "deb-systemd-invoke restart 'b.service'" in script

    def test_runs_fragment_before_enabling_units(self):
        script = maintscripts.postinst(["a.service"], fragment="touch /tmp/fragment\n")

        assert script.index("touch /tmp/fragment") < script.index("deb-systemd-helper enable")

    def test_without_units_only_contains_fragment(self):
        script = maintscripts.postinst([], fragment="echo hi\n")

        assert "deb-systemd" not in script
        assert "echo hi" in script


class TestPrerm:
    def test_stops_units_on_remove(self):
        script = maintscripts.prerm(["a.service"], fragment="")

        assert "deb-systemd-invoke stop 'a.service'" in script
        assert '"$1" = "remove"' in script


class TestPostrm:
    def test_purges_unit_state_and_runs_fragment_on_purge_only(self):
        script = maintscripts.postrm(["a.service"], fragment="rm -f /etc/x\n")

        purge_block = script[script.index('"$1" = "purge"'):]
        assert "deb-systemd-helper purge 'a.service'" in purge_block
        assert "rm -f /etc/x" in purge_block


class TestWrite:
    def test_writes_three_scripts_that_pass_shellcheck(self, tmp_path):
        pkg = tmp_path / "pihero-x"
        (pkg / "scripts").mkdir(parents=True)
        (pkg / "units.txt").write_text("# units\npihero-x.service\n")
        (pkg / "scripts" / "postinst.sh").write_text("# shellcheck shell=sh\n/usr/lib/pihero/bootconfig add cmdline x=1 --package pihero-x\n")

        maintscripts.write(pkg)

        names = sorted(p.name for p in (pkg / ".build").iterdir())
        assert names == ["postinst", "postrm", "prerm"]
        for name in names:
            result = tools.run(["shellcheck", "-s", "sh", f"/pkg/.build/{name}"], mounts=[f"{pkg}:/pkg:ro"], check=False, capture=True)
            assert result.returncode == 0, result.stdout
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest testkit/tests/test_maintscripts.py -v`
Expected: FAIL with `ModuleNotFoundError: pihero_testkit.maintscripts`.

- [ ] **Step 3: Implement maintscripts**

`testkit/src/pihero_testkit/maintscripts.py`:

```python
"""Generates Debian maintainer scripts for a package directory from its units.txt and hook fragments.

The systemd handling is the snippet debhelper emits, so packages behave like any Debian package.
"""

from pathlib import Path

HEADER = "#!/bin/sh\nset -e\n"


def units_of(pkg_dir: Path) -> list[str]:
    path = pkg_dir / "units.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def fragment_of(pkg_dir: Path, name: str) -> str:
    path = pkg_dir / "scripts" / f"{name}.sh"
    return path.read_text() if path.exists() else ""


def postinst(units: list[str], fragment: str) -> str:
    lines = [HEADER, 'if [ "$1" = "configure" ] || [ "$1" = "abort-upgrade" ] || [ "$1" = "abort-deconfigure" ] || [ "$1" = "abort-remove" ]; then']
    lines.append(_indent(fragment))
    for unit in units:
        lines.append(
            f"  deb-systemd-helper unmask '{unit}' >/dev/null || true\n"
            f"  if deb-systemd-helper --quiet was-enabled '{unit}'; then\n"
            f"    deb-systemd-helper enable '{unit}' >/dev/null || true\n"
            f"  else\n"
            f"    deb-systemd-helper update-state '{unit}' >/dev/null || true\n"
            f"  fi"
        )
    if units:
        lines.append("  if [ -d /run/systemd/system ]; then\n    systemctl --system daemon-reload >/dev/null || true")
        lines.extend(f"    deb-systemd-invoke restart '{unit}' >/dev/null || true" for unit in units)
        lines.append("  fi")
    lines.append("fi\n")
    return "\n".join(lines)


def prerm(units: list[str], fragment: str) -> str:
    lines = [HEADER, 'if [ "$1" = "remove" ]; then']
    if units:
        lines.append("  if [ -d /run/systemd/system ]; then")
        lines.extend(f"    deb-systemd-invoke stop '{unit}' >/dev/null || true" for unit in units)
        lines.append("  fi")
    lines.append(_indent(fragment))
    lines.append("fi\n")
    return "\n".join(lines)


def postrm(units: list[str], fragment: str) -> str:
    lines = [HEADER]
    if units:
        lines.append("if [ -d /run/systemd/system ]; then\n  systemctl --system daemon-reload >/dev/null || true\nfi")
        lines.append('if [ "$1" = "remove" ] && [ -x /usr/bin/deb-systemd-helper ]; then')
        lines.extend(f"  deb-systemd-helper mask '{unit}' >/dev/null || true" for unit in units)
        lines.append("fi")
    lines.append('if [ "$1" = "purge" ]; then')
    if units:
        lines.append("  if [ -x /usr/bin/deb-systemd-helper ]; then")
        for unit in units:
            lines.append(f"    deb-systemd-helper purge '{unit}' >/dev/null || true\n    deb-systemd-helper unmask '{unit}' >/dev/null || true")
        lines.append("  fi")
    lines.append(_indent(fragment))
    lines.append("fi\n")
    return "\n".join(lines)


def write(pkg_dir: Path) -> None:
    units = units_of(pkg_dir)
    out = pkg_dir / ".build"
    out.mkdir(exist_ok=True)
    for name, render in (("postinst", postinst), ("prerm", prerm), ("postrm", postrm)):
        (out / name).write_text(render(units, fragment_of(pkg_dir, name)))
        (out / name).chmod(0o755)


def _indent(fragment: str) -> str:
    return "\n".join(f"  {line}" if line.strip() else "" for line in fragment.rstrip("\n").splitlines()) if fragment.strip() else "  :"
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest testkit/tests/test_maintscripts.py -v`
Expected: 6 passed.

- [ ] **Step 5: Write the failing tests for build**

`testkit/tests/test_build.py`:

```python
import subprocess
from pathlib import Path

import pytest

from pihero_testkit import build, tools

pytestmark = pytest.mark.tier0


class TestVersionFromGit:
    @pytest.mark.parametrize(
        ("describe", "version"),
        [
            ("v2.0.0-0-gabc1234", "2.0.0"),
            ("v2.0.0-3-gabc1234", "2.0.0+3.abc1234"),
            ("v2.0.0-3-gabc1234-dirty", "2.0.0+3.abc1234.dirty"),
            ("v2.0.0-0-gabc1234-dirty", "2.0.0+0.abc1234.dirty"),
            ("abc1234", "0.0.0+abc1234"),
            ("abc1234-dirty", "0.0.0+abc1234.dirty"),
        ],
    )
    def test_maps_git_describe_to_a_debian_version(self, describe, version):
        assert build.version_from_describe(describe) == version


class TestBuild:
    def test_builds_a_package_from_a_directory(self, tmp_path, monkeypatch):
        pkg = Path("packages") / "pihero-zz-probe"
        (pkg / "root" / "usr" / "lib" / "pihero").mkdir(parents=True)
        (pkg / "root" / "usr" / "lib" / "pihero" / "probe").write_text("#!/bin/sh\necho probe\n")
        (pkg / "root" / "usr" / "lib" / "pihero" / "probe").chmod(0o755)
        (pkg / "nfpm.yaml").write_text(
            "name: pihero-zz-probe\narch: all\nplatform: linux\nversion: ${VERSION}\nsection: admin\npriority: optional\n"
            "maintainer: Björn Kahlert <bkahlert@users.noreply.github.com>\ndescription: probe\nlicense: MIT\n"
            "contents:\n  - src: root/\n    dst: /\n    type: tree\n"
            "scripts:\n  postinstall: .build/postinst\n  preremove: .build/prerm\n  postremove: .build/postrm\n"
        )
        try:
            deb = build.build(pkg, "9.9.9", dist=Path("dist") / "probe")

            info = tools.run(["dpkg-deb", "--info", f"/work/{deb.relative_to(Path.cwd())}"], capture=True).stdout
            contents = tools.run(["dpkg-deb", "--contents", f"/work/{deb.relative_to(Path.cwd())}"], capture=True).stdout
            assert deb.name == "pihero-zz-probe_9.9.9_all.deb"
            assert " Architecture: all" in info
            assert " Version: 9.9.9" in info
            assert "-rwxr-xr-x" in contents and "./usr/lib/pihero/probe" in contents
        finally:
            subprocess.run(["rm", "-rf", str(pkg), "dist/probe"], check=True)
```

- [ ] **Step 6: Run to verify failure**

Run: `uv run pytest testkit/tests/test_build.py -v`
Expected: FAIL with `ModuleNotFoundError: pihero_testkit.build`.

- [ ] **Step 7: Implement build**

`testkit/src/pihero_testkit/build.py`:

```python
"""Builds every package under packages/ into dist/ with nfpm running in the tools container."""

import os
import re
import subprocess
import sys
from pathlib import Path

from . import maintscripts, tools

PACKAGES = Path.cwd() / "packages"
DIST = Path.cwd() / "dist"


def version_from_describe(describe: str) -> str:
    match = re.fullmatch(r"v(\d+\.\d+\.\d+)-(\d+)-g([0-9a-f]+)(-dirty)?", describe)
    if not match:
        return "0.0.0+" + describe.replace("-dirty", ".dirty")
    base, ahead, sha, dirty = match.groups()
    if ahead == "0" and not dirty:
        return base
    return f"{base}+{ahead}.{sha}{'.dirty' if dirty else ''}"


def version_from_git() -> str:
    if env := os.environ.get("VERSION"):
        return env
    out = subprocess.run(
        ["git", "describe", "--tags", "--match", "v*", "--long", "--dirty", "--always"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return version_from_describe(out)


def discover() -> list[Path]:
    return sorted(p for p in PACKAGES.iterdir() if (p / "nfpm.yaml").exists())


def build(pkg_dir: Path, version: str, dist: Path = DIST) -> Path:
    maintscripts.write(pkg_dir)
    dist.mkdir(parents=True, exist_ok=True)
    deb = dist / f"{pkg_dir.name}_{version}_all.deb"
    tools.run(
        ["nfpm", "package", "-f", "nfpm.yaml", "-p", "deb", "-t", f"/work/{deb.relative_to(Path.cwd())}"],
        workdir=f"/work/{pkg_dir.relative_to(Path.cwd())}",
        env={"VERSION": version},
    )
    return deb


def build_all(version: str, dist: Path = DIST) -> list[Path]:
    return [build(pkg_dir, version, dist) for pkg_dir in discover()]


if __name__ == "__main__":
    for path in build_all(version_from_git()):
        print(path)
    sys.exit(0)
```

- [ ] **Step 8: Run to verify pass**

Run: `uv run pytest testkit/tests/test_build.py -v`
Expected: 7 passed. If nfpm rejects `type: tree` with `dst: /`, change the probe and the later packages to `dst: /` → `dst: /.`; record which form worked in the commit message.

- [ ] **Step 9: Commit**

```bash
git add testkit
git commit -m "feat(testkit): package build with nfpm and generated maintainer scripts

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 5: `pihero-bootconfig`

The idempotent editor for `config.txt` and `cmdline.txt`. Pure functions first, then the CLI around them.

**Files:**
- Create: `packages/pihero/root/usr/lib/pihero/bootconfig` (executable, `#!/usr/bin/python3`)
- Create: `packages/pihero/tests/test_bootconfig.py`

**Interfaces:**
- Produces (module): `parse_config(text) -> list[Section]`, `render_config(sections) -> str`, `set_key(sections, section, key, value) -> bool`, `unset_key(sections, section, key, value=None) -> bool`, `parse_cmdline(text) -> list[str]` (raises `ValueError` on more than one line), `render_cmdline(params) -> str`, `add_param(params, param) -> bool`, `remove_param(params, name) -> bool`, `mark_reboot_required(run_dir, package)`.
- Produces (CLI): `bootconfig set config KEY VALUE [--section all] [--package PKG]`, `bootconfig unset config KEY [--value V] [--section all] [--package PKG]`, `bootconfig add cmdline PARAM[=VALUE] [--package PKG]`, `bootconfig remove cmdline PARAM [--package PKG]`. Prints `changed` or `unchanged`. Exit 0 on success, 1 on a malformed or missing file, 2 on usage errors. Environment: `PIHERO_BOOTFS` (default `/boot/firmware`), `PIHERO_RUN` (default `/run`).

- [ ] **Step 1: Write the failing tests**

`packages/pihero/tests/test_bootconfig.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0

SCRIPT = Path(__file__).resolve().parents[1] / "root" / "usr" / "lib" / "pihero" / "bootconfig"
bootconfig = load_script(SCRIPT)

STOCK_CONFIG = """# For more options and information see
# http://rptl.io/configtxt
dtparam=audio=on
camera_auto_detect=1
display_auto_detect=1
auto_initramfs=1
dtoverlay=vc4-kms-v3d
max_framebuffers=2
disable_fw_kms_setup=1
arm_64bit=1
disable_overscan=1
arm_boost=1

[cm4]
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
"""

STOCK_CMDLINE = "console=serial0,115200 console=tty1 root=PARTUUID=0a1b2c3d-02 rootfstype=ext4 fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles cfg80211.ieee80211_regdom=DE\n"


class TestConfig:
    class TestSet:
        def test_appends_missing_key_to_the_last_all_section(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.set_key(sections, "all", "disable_splash", "1")

            assert changed
            assert bootconfig.render_config(sections).endswith("[all]\ndisable_splash=1\n")

        def test_replaces_an_existing_value_in_place(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.set_key(sections, "all", "disable_overscan", "0")

            text = bootconfig.render_config(sections)
            assert changed
            assert "disable_overscan=0\n" in text
            assert "disable_overscan=1" not in text
            assert text.index("disable_overscan=0") < text.index("[cm4]")

        def test_is_unchanged_on_the_same_value(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.set_key(sections, "all", "arm_64bit", "1")

            assert not changed
            assert bootconfig.render_config(sections) == STOCK_CONFIG

        def test_leaves_the_same_key_in_other_sections_alone(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            bootconfig.set_key(sections, "all", "dtoverlay", "dwc2")

            text = bootconfig.render_config(sections)
            assert text.count("dtoverlay=dwc2,dr_mode=host") == 1
            assert text.splitlines()[-1] == "dtoverlay=dwc2"

        def test_adds_a_repeatable_key_as_a_new_line(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            bootconfig.set_key(sections, "all", "dtoverlay", "dwc2")

            text = bootconfig.render_config(sections)
            assert "dtoverlay=vc4-kms-v3d\n" in text
            assert "dtoverlay=dwc2\n" in text

        def test_creates_a_missing_section_at_the_end(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.set_key(sections, "pi0", "gpu_mem", "16")

            assert changed
            assert bootconfig.render_config(sections).endswith("[all]\n[pi0]\ngpu_mem=16\n")

        def test_collapses_duplicate_keys_into_one(self):
            sections = bootconfig.parse_config("arm_boost=1\narm_boost=0\n")

            bootconfig.set_key(sections, "all", "arm_boost", "1")

            assert bootconfig.render_config(sections) == "arm_boost=1\n"

        def test_matches_section_names_case_insensitively(self):
            sections = bootconfig.parse_config("[CM4]\notg_mode=1\n")

            changed = bootconfig.set_key(sections, "cm4", "otg_mode", "1")

            assert not changed

    class TestUnset:
        def test_removes_the_key(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.unset_key(sections, "all", "arm_boost")

            assert changed
            assert "arm_boost" not in bootconfig.render_config(sections)

        def test_removes_only_the_matching_value_of_a_repeatable_key(self):
            sections = bootconfig.parse_config("dtoverlay=vc4-kms-v3d\ndtoverlay=dwc2\n")

            bootconfig.unset_key(sections, "all", "dtoverlay", "dwc2")

            assert bootconfig.render_config(sections) == "dtoverlay=vc4-kms-v3d\n"

        def test_is_unchanged_on_a_missing_key(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.unset_key(sections, "all", "gpu_mem")

            assert not changed


class TestCmdline:
    class TestAdd:
        def test_appends_a_missing_parameter(self):
            params = bootconfig.parse_cmdline(STOCK_CMDLINE)

            changed = bootconfig.add_param(params, "logo.nologo")

            assert changed
            assert bootconfig.render_cmdline(params) == STOCK_CMDLINE.rstrip("\n") + " logo.nologo\n"

        def test_replaces_a_parameter_with_the_same_name(self):
            params = bootconfig.parse_cmdline("quiet loglevel=7 splash\n")

            changed = bootconfig.add_param(params, "loglevel=3")

            assert changed
            assert bootconfig.render_cmdline(params) == "quiet loglevel=3 splash\n"

        def test_is_unchanged_on_a_present_parameter(self):
            params = bootconfig.parse_cmdline(STOCK_CMDLINE)

            changed = bootconfig.add_param(params, "quiet")

            assert not changed

    class TestRemove:
        def test_removes_all_occurrences_by_name(self):
            params = bootconfig.parse_cmdline(STOCK_CMDLINE)

            changed = bootconfig.remove_param(params, "console")

            assert changed
            assert "console=" not in bootconfig.render_cmdline(params)

        def test_is_unchanged_on_a_missing_parameter(self):
            params = bootconfig.parse_cmdline(STOCK_CMDLINE)

            changed = bootconfig.remove_param(params, "logo.nologo")

            assert not changed

    def test_keeps_a_single_line_with_a_trailing_newline(self):
        params = bootconfig.parse_cmdline("quiet  splash")

        assert bootconfig.render_cmdline(params) == "quiet splash\n"

    def test_refuses_a_file_with_more_than_one_line(self):
        with pytest.raises(ValueError):
            bootconfig.parse_cmdline("quiet\nsplash\n")


class TestCli:
    def test_set_writes_the_file_and_marks_a_reboot_required(self, bootfs, run_dir):
        result = cli("set", "config", "disable_splash", "1", "--package", "pihero-splash", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 0
        assert result.stdout.strip() == "changed"
        assert (bootfs / "config.txt").read_text().endswith("[all]\ndisable_splash=1\n")
        assert (run_dir / "reboot-required").exists()
        assert (run_dir / "reboot-required.pkgs").read_text() == "pihero-splash\n"

    def test_unchanged_run_does_not_mark_a_reboot(self, bootfs, run_dir):
        result = cli("add", "cmdline", "quiet", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 0
        assert result.stdout.strip() == "unchanged"
        assert not (run_dir / "reboot-required").exists()

    def test_records_each_package_once(self, bootfs, run_dir):
        cli("add", "cmdline", "a=1", "--package", "pihero-splash", bootfs=bootfs, run_dir=run_dir)
        cli("add", "cmdline", "b=1", "--package", "pihero-splash", bootfs=bootfs, run_dir=run_dir)
        cli("add", "cmdline", "c=1", "--package", "pihero-display-hdmi", bootfs=bootfs, run_dir=run_dir)

        assert (run_dir / "reboot-required.pkgs").read_text() == "pihero-splash\npihero-display-hdmi\n"

    def test_multiline_cmdline_exits_1_without_writing(self, bootfs, run_dir):
        (bootfs / "cmdline.txt").write_text("quiet\nsplash\n")

        result = cli("add", "cmdline", "logo.nologo", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 1
        assert "single line" in result.stderr
        assert (bootfs / "cmdline.txt").read_text() == "quiet\nsplash\n"

    def test_missing_file_exits_1(self, bootfs, run_dir):
        (bootfs / "config.txt").unlink()

        result = cli("set", "config", "a", "1", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 1

    def test_unknown_action_exits_2(self, bootfs, run_dir):
        result = cli("frob", "config", "a", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 2

    def test_unset_of_a_repeatable_key_needs_a_value(self, bootfs, run_dir):
        result = cli("unset", "config", "dtoverlay", "--value", "vc4-kms-v3d", bootfs=bootfs, run_dir=run_dir)

        assert result.stdout.strip() == "changed"
        assert "dtoverlay=vc4-kms-v3d" not in (bootfs / "config.txt").read_text()


@pytest.fixture
def bootfs(tmp_path):
    path = tmp_path / "bootfs"
    path.mkdir()
    (path / "config.txt").write_text(STOCK_CONFIG)
    (path / "cmdline.txt").write_text(STOCK_CMDLINE)
    return path


@pytest.fixture
def run_dir(tmp_path):
    path = tmp_path / "run"
    path.mkdir()
    return path


def cli(*args, bootfs, run_dir):
    env = {**os.environ, "PIHERO_BOOTFS": str(bootfs), "PIHERO_RUN": str(run_dir)}
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/pihero/tests/test_bootconfig.py -v`
Expected: FAIL at import with `FileNotFoundError` for the script.

- [ ] **Step 3: Implement the script**

`packages/pihero/root/usr/lib/pihero/bootconfig`:

```python
#!/usr/bin/python3
"""Idempotent editor for the Raspberry Pi boot files config.txt and cmdline.txt.

Usage:
  bootconfig set    config  KEY VALUE [--section NAME] [--package PKG]
  bootconfig unset  config  KEY [--value VALUE] [--section NAME] [--package PKG]
  bootconfig add    cmdline PARAM[=VALUE] [--package PKG]
  bootconfig remove cmdline PARAM [--package PKG]

Prints "changed" or "unchanged". On change it touches $PIHERO_RUN/reboot-required and records PKG in
$PIHERO_RUN/reboot-required.pkgs. Files are read from $PIHERO_BOOTFS (default /boot/firmware).
"""

import argparse
import os
import re
import sys
from pathlib import Path

REPEATABLE = {"dtoverlay", "dtparam"}
KEY_VALUE = re.compile(r"^\s*([^#=\s\[]+)\s*=\s*(.*?)\s*$")
REBOOT_REQUIRED_TEXT = "*** System restart required ***\n"


class Section:
    def __init__(self, name: str, header: str | None):
        self.name = name
        self.header = header
        self.lines: list[str] = []


def parse_config(text: str) -> list[Section]:
    sections = [Section("all", None)]
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            sections.append(Section(stripped[1:-1].strip().lower(), line))
        else:
            sections[-1].lines.append(line)
    return sections


def render_config(sections: list[Section]) -> str:
    out: list[str] = []
    for section in sections:
        if section.header is not None:
            out.append(section.header)
        out.extend(section.lines)
    return "\n".join(out) + "\n"


def _key_value(line: str) -> tuple[str, str] | None:
    match = KEY_VALUE.match(line)
    return (match.group(1), match.group(2)) if match else None


def set_key(sections: list[Section], section_name: str, key: str, value: str) -> bool:
    section_name = section_name.lower()
    line = f"{key}={value}"
    targets = [s for s in sections if s.name == section_name]
    if key in REPEATABLE:
        if any(_key_value(l) == (key, value) for s in targets for l in s.lines):
            return False
    else:
        occurrences = [(s, i) for s in targets for i, l in enumerate(s.lines) if (kv := _key_value(l)) and kv[0] == key]
        if occurrences:
            first_section, first_index = occurrences[0]
            unchanged = len(occurrences) == 1 and _key_value(first_section.lines[first_index]) == (key, value)
            if unchanged:
                return False
            first_section.lines[first_index] = line
            for section, index in reversed(occurrences[1:]):
                del section.lines[index]
            return True
    if not targets:
        sections.append(Section(section_name, f"[{section_name}]"))
        targets = [sections[-1]]
    targets[-1].lines.append(line)
    return True


def unset_key(sections: list[Section], section_name: str, key: str, value: str | None = None) -> bool:
    section_name = section_name.lower()
    changed = False
    for section in (s for s in sections if s.name == section_name):
        kept = [l for l in section.lines if not ((kv := _key_value(l)) and kv[0] == key and (value is None or kv[1] == value))]
        changed |= len(kept) != len(section.lines)
        section.lines = kept
    return changed


def parse_cmdline(text: str) -> list[str]:
    if "\n" in text.strip():
        raise ValueError("cmdline.txt must be a single line")
    return text.split()


def render_cmdline(params: list[str]) -> str:
    return " ".join(params) + "\n"


def _name(param: str) -> str:
    return param.split("=", 1)[0]


def add_param(params: list[str], param: str) -> bool:
    indices = [i for i, p in enumerate(params) if _name(p) == _name(param)]
    if indices:
        if len(indices) == 1 and params[indices[0]] == param:
            return False
        params[indices[0]] = param
        for index in reversed(indices[1:]):
            del params[index]
        return True
    params.append(param)
    return True


def remove_param(params: list[str], name: str) -> bool:
    kept = [p for p in params if _name(p) != name]
    changed = len(kept) != len(params)
    params[:] = kept
    return changed


def mark_reboot_required(run_dir: Path, package: str | None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "reboot-required").write_text(REBOOT_REQUIRED_TEXT)
    if package:
        pkgs = run_dir / "reboot-required.pkgs"
        listed = pkgs.read_text().split() if pkgs.exists() else []
        if package not in listed:
            pkgs.write_text("".join(f"{p}\n" for p in [*listed, package]))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="bootconfig", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["set", "unset", "add", "remove"])
    parser.add_argument("file", choices=["config", "cmdline"])
    parser.add_argument("key")
    parser.add_argument("value", nargs="?")
    parser.add_argument("--section", default="all")
    parser.add_argument("--value", dest="unset_value")
    parser.add_argument("--package")
    args = parser.parse_args(argv)
    if args.file == "config" and args.action not in ("set", "unset") or args.file == "cmdline" and args.action not in ("add", "remove"):
        parser.error(f"'{args.action}' does not apply to {args.file}")
    if args.action == "set" and args.value is None:
        parser.error("set needs KEY VALUE")

    bootfs = Path(os.environ.get("PIHERO_BOOTFS", "/boot/firmware"))
    run_dir = Path(os.environ.get("PIHERO_RUN", "/run"))
    path = bootfs / ("config.txt" if args.file == "config" else "cmdline.txt")
    try:
        text = path.read_text()
        if args.file == "config":
            sections = parse_config(text)
            changed = set_key(sections, args.section, args.key, args.value) if args.action == "set" else unset_key(sections, args.section, args.key, args.unset_value)
            new_text = render_config(sections)
        else:
            params = parse_cmdline(text)
            changed = add_param(params, args.key) if args.action == "add" else remove_param(params, args.key)
            new_text = render_cmdline(params)
    except (OSError, ValueError) as error:
        print(f"bootconfig: {path}: {error}", file=sys.stderr)
        return 1
    if changed:
        path.write_text(new_text)
        mark_reboot_required(run_dir, args.package)
    print("changed" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Make it executable: `chmod 755 packages/pihero/root/usr/lib/pihero/bootconfig`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest packages/pihero/tests/test_bootconfig.py -v`
Expected: all passed. If `test_appends_a_missing_parameter` fails on the trailing-space join, the fixture line ends with `\n` on purpose; compare against `STOCK_CMDLINE.rstrip("\n") + " logo.nologo\n"` as written.

- [ ] **Step 5: Commit**

```bash
git add packages/pihero
git commit -m "feat(pihero): bootconfig, an idempotent editor for config.txt and cmdline.txt

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 6: MOTD generator

Pure parsing and rendering functions with unit tests; the CLI glues them to `dpkg-query`, `systemctl`, and `ip`. Its end-to-end behaviour is checked in tier 1 (Task 7).

**Files:**
- Create: `packages/pihero/root/usr/lib/pihero/motd` (executable, `#!/usr/bin/python3`)
- Create: `packages/pihero/root/etc/update-motd.d/50-pihero` (executable, `#!/bin/sh`)
- Create: `packages/pihero/root/usr/share/pihero/hero.txt`
- Create: `packages/pihero/tests/test_motd.py`

**Interfaces:**
- Produces (module): `parse_dpkg(output) -> list[tuple[str, str]]`, `parse_failed(output) -> list[str]`, `parse_usb0(output) -> str | None`, `reboot_state(run_dir) -> tuple[bool, list[str]]`, `render(banner, packages, failed, reboot, usb0) -> str`.
- Output format consumed by tests in Tasks 7 and 10: lines `  packages:        pihero 2.0.0, pihero-avahi 2.0.0`, `  failed units:    none`, `  reboot required: no` or `yes (pihero-splash)`, `  usb0:            10.10.10.60/29` or `not present`.

- [ ] **Step 1: Generate the static banner**

```bash
mkdir -p packages/pihero/root/usr/share/pihero
./assets/hero --mood neutral --no-color > packages/pihero/root/usr/share/pihero/hero.txt
cat packages/pihero/root/usr/share/pihero/hero.txt
```

Expected: the neutral kaomoji on one line. If the script emits more than one line or any escape sequence, trim it to the single plain line.

- [ ] **Step 2: Write the failing tests**

`packages/pihero/tests/test_motd.py`:

```python
from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0

SCRIPT = Path(__file__).resolve().parents[1] / "root" / "usr" / "lib" / "pihero" / "motd"
motd = load_script(SCRIPT)


class TestParseDpkg:
    def test_keeps_installed_packages_with_version(self):
        rows = motd.parse_dpkg("pihero 2.0.0 ii \npihero-avahi 2.0.0 ii \npihero-smb 1.0 rc \n")

        assert rows == [("pihero", "2.0.0"), ("pihero-avahi", "2.0.0")]

    def test_is_empty_on_no_output(self):
        assert motd.parse_dpkg("") == []


class TestParseFailed:
    def test_lists_unit_names(self):
        assert motd.parse_failed("pihero-avahi-render.service loaded failed failed Pi Hero\nfoo.service loaded failed failed Foo\n") == ["pihero-avahi-render.service", "foo.service"]

    def test_is_empty_on_no_output(self):
        assert motd.parse_failed("\n") == []


class TestParseUsb0:
    def test_returns_the_cidr(self):
        assert motd.parse_usb0("3: usb0    inet 10.10.10.60/29 brd 10.10.10.63 scope global usb0\\       valid_lft forever\n") == "10.10.10.60/29"

    def test_is_none_without_an_address(self):
        assert motd.parse_usb0("") is None


class TestRebootState:
    def test_reports_flag_and_packages(self, tmp_path):
        (tmp_path / "reboot-required").write_text("*** System restart required ***\n")
        (tmp_path / "reboot-required.pkgs").write_text("pihero-splash\n")

        assert motd.reboot_state(tmp_path) == (True, ["pihero-splash"])

    def test_reports_no_reboot_without_the_flag(self, tmp_path):
        assert motd.reboot_state(tmp_path) == (False, [])


class TestRender:
    def test_shows_every_line_with_defaults(self):
        text = motd.render("HERO\n", [("pihero", "2.0.0")], [], (False, []), None)

        assert text == "HERO\n\n  packages:        pihero 2.0.0\n  failed units:    none\n  reboot required: no\n  usb0:            not present\n"

    def test_lists_failed_units_and_reboot_packages(self):
        text = motd.render("", [], ["x.service"], (True, ["pihero-splash", "pihero-display-hdmi"]), "10.10.10.60/29")

        assert "  failed units:    x.service\n" in text
        assert "  reboot required: yes (pihero-splash, pihero-display-hdmi)\n" in text
        assert "  usb0:            10.10.10.60/29\n" in text

    def test_shows_yes_without_package_list(self):
        text = motd.render("", [], [], (True, []), None)

        assert "  reboot required: yes\n" in text
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest packages/pihero/tests/test_motd.py -v`
Expected: FAIL at import.

- [ ] **Step 4: Implement**

`packages/pihero/root/usr/lib/pihero/motd`:

```python
#!/usr/bin/python3
"""Prints the Pi Hero MOTD: banner, installed pihero packages, failed units, pending reboot, usb0 address."""

import subprocess
import sys
from pathlib import Path

BANNER = Path("/usr/share/pihero/hero.txt")
RUN = Path("/run")


def parse_dpkg(output: str) -> list[tuple[str, str]]:
    rows = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2].startswith("ii"):
            rows.append((parts[0], parts[1]))
    return rows


def parse_failed(output: str) -> list[str]:
    return [line.split()[0] for line in output.splitlines() if line.strip()]


def parse_usb0(output: str) -> str | None:
    for line in output.splitlines():
        parts = line.split()
        if "inet" in parts:
            return parts[parts.index("inet") + 1]
    return None


def reboot_state(run_dir: Path) -> tuple[bool, list[str]]:
    pkgs = run_dir / "reboot-required.pkgs"
    return (run_dir / "reboot-required").exists(), (pkgs.read_text().split() if pkgs.exists() else [])


def render(banner: str, packages: list[tuple[str, str]], failed: list[str], reboot: tuple[bool, list[str]], usb0: str | None) -> str:
    required, reboot_pkgs = reboot
    reboot_text = "no" if not required else f"yes ({', '.join(reboot_pkgs)})" if reboot_pkgs else "yes"
    return (
        f"{banner.rstrip()}\n\n"
        f"  packages:        {', '.join(f'{name} {version}' for name, version in packages) or 'none'}\n"
        f"  failed units:    {', '.join(failed) or 'none'}\n"
        f"  reboot required: {reboot_text}\n"
        f"  usb0:            {usb0 or 'not present'}\n"
    )


def _output(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout
    except FileNotFoundError:
        return ""


def main() -> int:
    packages = parse_dpkg(_output(["dpkg-query", "-W", "-f=${Package} ${Version} ${db:Status-Abbrev}\n", "pihero*"]))
    failed = parse_failed(_output(["systemctl", "--failed", "--no-legend", "--plain"]))
    usb0 = parse_usb0(_output(["ip", "-o", "-4", "addr", "show", "dev", "usb0"]))
    banner = BANNER.read_text() if BANNER.exists() else ""
    sys.stdout.write(render(banner, packages, failed, reboot_state(RUN), usb0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`packages/pihero/root/etc/update-motd.d/50-pihero`:

```sh
#!/bin/sh
exec /usr/lib/pihero/motd
```

```bash
chmod 755 packages/pihero/root/usr/lib/pihero/motd packages/pihero/root/etc/update-motd.d/50-pihero
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest packages/pihero/tests/test_motd.py -v`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add packages/pihero
git commit -m "feat(pihero): MOTD generator with static hero banner

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 7: The `pihero` package

Assembles the core package: manifest, watchdog drop-in, maintainer-script fragments, and the installed-state tests that tiers 1, 2, and 4 share. The tests are written now and first run in Task 8 once the podman target exists.

**Files:**
- Create: `packages/pihero/nfpm.yaml`
- Create: `packages/pihero/root/etc/systemd/system.conf.d/10-pihero-watchdog.conf`
- Create: `packages/pihero/scripts/postinst.sh`, `packages/pihero/scripts/postrm.sh`
- Create: `packages/pihero/tests/test_installed.py`

**Interfaces:**
- Consumes: fixtures `host`, `target`, `version` from `pihero_testkit.plugin` (Task 8): `host` is a testinfra host with sudo; `target.reboot()`; `target.install_extra(names: list[str])`; `version` is the built version string.

- [ ] **Step 1: Manifest and files**

`packages/pihero/nfpm.yaml`:

```yaml
name: pihero
arch: all
platform: linux
version: ${VERSION}
section: admin
priority: optional
maintainer: Björn Kahlert <bkahlert@users.noreply.github.com>
description: |
  Pi Hero core: boot-config editor, MOTD, hardware watchdog.
  Every pihero-* feature package depends on this one.
homepage: https://github.com/bkahlert/pihero
license: MIT
depends:
  - python3
  - systemd
contents:
  - src: root/
    dst: /
    type: tree
scripts:
  postinstall: .build/postinst
  preremove: .build/prerm
  postremove: .build/postrm
```

`packages/pihero/root/etc/systemd/system.conf.d/10-pihero-watchdog.conf`:

```ini
# Armed by systemd; the BCM2835 watchdog resets the board if pings stop. 15 s is its maximum.
[Manager]
RuntimeWatchdogSec=15
```

`packages/pihero/scripts/postinst.sh`:

```sh
# shellcheck shell=sh
if [ -d /run/systemd/system ]; then
  systemctl daemon-reexec >/dev/null 2>&1 || true
fi
```

`packages/pihero/scripts/postrm.sh`:

```sh
# shellcheck shell=sh
if [ -d /run/systemd/system ]; then
  systemctl daemon-reexec >/dev/null 2>&1 || true
fi
```

- [ ] **Step 2: Build it**

Run: `make build && ls dist/`
Expected: `pihero_<version>_all.deb`. Then `podman run --rm -v "$PWD/dist":/d docker.io/library/debian:trixie-slim dpkg-deb --contents /d/pihero_*_all.deb` lists `./usr/lib/pihero/bootconfig` and `./usr/lib/pihero/motd` with mode `-rwxr-xr-x`, and `./etc/update-motd.d/50-pihero` likewise.

- [ ] **Step 3: Write the installed-state tests**

`packages/pihero/tests/test_installed.py`:

```python
import pytest

pytestmark = pytest.mark.installed


class TestPackage:
    def test_is_installed_at_the_built_version(self, host, version):
        package = host.package("pihero")

        assert package.is_installed
        assert package.version == version

    @pytest.mark.parametrize("path", ["/usr/lib/pihero/bootconfig", "/usr/lib/pihero/motd", "/etc/update-motd.d/50-pihero"])
    def test_ships_executables_owned_by_root(self, host, path):
        file = host.file(path)

        assert file.exists
        assert file.mode == 0o755
        assert file.user == "root"


class TestWatchdog:
    def test_drop_in_sets_fifteen_seconds(self, host):
        assert host.file("/etc/systemd/system.conf.d/10-pihero-watchdog.conf").contains("RuntimeWatchdogSec=15")

    def test_manager_reports_the_configured_timeout(self, host):
        assert host.check_output("systemctl show --property=RuntimeWatchdogUSec").strip() == "RuntimeWatchdogUSec=15s"


class TestMotd:
    def test_reports_the_installed_packages(self, host, version):
        output = host.check_output("/usr/lib/pihero/motd")

        assert f"pihero {version}" in output
        assert "failed units:" in output


class TestBootconfig:
    @pytest.mark.mutating
    def test_edits_cmdline_and_flags_a_reboot(self, host):
        host.check_output("sudo /usr/lib/pihero/bootconfig add cmdline pihero.probe=1 --package pihero-probe")

        assert "pihero.probe=1" in host.file("/boot/firmware/cmdline.txt").content_string
        assert host.file("/run/reboot-required").exists
        assert host.file("/run/reboot-required.pkgs").contains("pihero-probe")
        assert "reboot required: yes (pihero-probe)" in host.check_output("/usr/lib/pihero/motd")

        host.check_output("sudo /usr/lib/pihero/bootconfig remove cmdline pihero.probe --package pihero-probe")

        assert "pihero.probe" not in host.file("/boot/firmware/cmdline.txt").content_string


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_leaves_nothing_behind(self, host, target):
        target.purge(["pihero"])

        assert not host.file("/usr/lib/pihero/bootconfig").exists
        assert not host.file("/etc/systemd/system.conf.d/10-pihero-watchdog.conf").exists
        assert not host.file("/etc/update-motd.d/50-pihero").exists

        target.reinstall()
```

- [ ] **Step 4: Tier 0 still green**

Run: `make test-tier0`
Expected: all tier-0 tests pass; the `installed` tests are collected but deselected.

- [ ] **Step 5: Commit**

```bash
git add packages/pihero
git commit -m "feat(pihero): package manifest, watchdog drop-in, installed-state tests

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 8: Tier 1 harness — systemd podman target

The plugin gains `--target`, the session-scoped `target` and `host` fixtures, and the podman implementation. Ends with `make test-tier1` green for `linux/arm64` and `linux/arm/v7`. Apply the adjustments recorded in `docs/spikes/2026-09-27-tier1-podman.md` (masked units, `PODMAN` prefix) where the spike found them necessary.

**Files:**
- Create: `testkit/src/pihero_testkit/tier1/Containerfile`
- Create: `testkit/src/pihero_testkit/podman.py`
- Modify: `testkit/src/pihero_testkit/plugin.py`

**Interfaces:**
- Produces: pytest options `--target {podman,vm,ssh}` (default `podman`), `--target-uri`, `--platform` (default `linux/arm64`), `--qemu-accel` (default `hvf`), `--device`, `--keep`. Session fixtures `version: str`, `packages: list[Path]`, `target`, and function fixture `host`.
- Target protocol every implementation offers: `.host` (testinfra host, sudo enabled), `.install(debs: list[Path])`, `.install_extra(names: list[str])`, `.remove(names)`, `.purge(names)`, `.reinstall()` (reinstalls all built packages), `.reboot()` (podman: no-op), `.stop()`.

- [ ] **Step 1: Tier 1 Containerfile**

`testkit/src/pihero_testkit/tier1/Containerfile` (the `boot/` directory next to it holds the stock files from Task 2):

```dockerfile
# Debian Trixie with systemd as PID 1: the tier-1 install target for Pi Hero packages.
FROM docker.io/library/debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus ca-certificates apt-utils python3 iproute2 \
    && rm -rf /var/lib/apt/lists/* \
    && systemctl mask systemd-udevd.service systemd-udevd-kernel.socket systemd-udevd-control.socket \
         systemd-udev-trigger.service getty.target console-getty.service systemd-firstboot.service
COPY boot/ /boot/firmware/
# Ready when the default target is reached; a wedged init keeps PID 1 alive but never gets here.
HEALTHCHECK --interval=5s --timeout=3s CMD systemctl is-active --quiet multi-user.target
CMD ["/sbin/init"]
```

- [ ] **Step 2: Podman target**

`testkit/src/pihero_testkit/podman.py`:

```python
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
        subprocess.run([*PODMAN, "build", "--platform", platform, "-t", tag, "-f", str(TIER1_DIR / "Containerfile"), str(TIER1_DIR)], check=True)
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
```

- [ ] **Step 3: Plugin with target fixtures**

Replace `testkit/src/pihero_testkit/plugin.py`:

```python
"""pytest plugin: target selection, tier markers, and the testinfra host fixture shared by all package tests."""

import pytest

from . import build


def pytest_addoption(parser):
    group = parser.getgroup("pihero")
    group.addoption("--target", choices=["podman", "vm", "ssh"], default="podman", help="where 'installed' and 'boot' tests run")
    group.addoption("--target-uri", default=None, help="for --target=ssh: user@host[:port]")
    group.addoption("--platform", default="linux/arm64", help="for --target=podman: container platform")
    group.addoption("--qemu-accel", default="hvf", help="for --target=vm: hvf or tcg")
    group.addoption("--device", default=None, help="for --target=vm: device directory (default: the testkit's all-features device)")
    group.addoption("--keep", action="store_true", help="keep the VM or container running after the session")


def pytest_configure(config):
    config.addinivalue_line("markers", "tier0: runs on the Mac against fixtures and the tools container, no target")
    config.addinivalue_line("markers", "installed: runs against any target with the packages installed (podman, vm, ssh)")
    config.addinivalue_line("markers", "boot: cross-cutting checks that need a booted VM or device (vm, ssh)")
    config.addinivalue_line("markers", "mutating: changes the target's state; skipped on --target=ssh")


def pytest_collection_modifyitems(config, items):
    target = config.getoption("--target")
    for item in items:
        if "mutating" in item.keywords and target == "ssh":
            item.add_marker(pytest.mark.skip(reason="mutating test on a real device"))
        if "boot" in item.keywords and target == "podman":
            item.add_marker(pytest.mark.skip(reason="needs a booted system"))


@pytest.fixture(scope="session")
def version() -> str:
    return build.version_from_git()


@pytest.fixture(scope="session")
def packages(version):
    return build.build_all(version)


@pytest.fixture(scope="session")
def target(request, version, packages):
    kind = request.config.getoption("--target")
    keep = request.config.getoption("--keep")
    if kind == "podman":
        from .podman import SystemdContainer

        container = SystemdContainer(request.config.getoption("--platform"), build.DIST, packages).start()
        container.install(packages)
        yield container
        if not keep:
            container.stop()
    elif kind == "vm":
        from .vm import provisioned_vm

        with provisioned_vm(packages, request.config.getoption("--device"), request.config.getoption("--qemu-accel"), keep) as vm:
            yield vm
    else:
        from .ssh import SshTarget

        yield SshTarget(request.config.getoption("--target-uri"), packages)


@pytest.fixture
def host(target):
    return target.host
```

- [ ] **Step 4: Run tier 1 on arm64**

Run: `make test-tier1`
Expected: all `installed` tests of `pihero` pass. Watch for these outcomes recorded by the spike and act accordingly: `RuntimeWatchdogUSec` reported as `0` in a container means the manager ignores the drop-in without a device, so change `test_manager_reports_the_configured_timeout` to read the value with `systemd-analyze cat-config systemd/system.conf | grep RuntimeWatchdogSec` and keep the `systemctl show` assertion for the `boot` tier only.

- [ ] **Step 5: Run tier 1 on arm/v7**

Run: `make test-tier1 PLATFORM=linux/arm/v7`
Expected: same result under emulation, slower.

- [ ] **Step 6: Commit**

```bash
git add testkit
git commit -m "feat(testkit): tier-1 target, a systemd podman container per platform

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 9: Tier 0 static checks

shellcheck for every shell file, `systemd-analyze verify` for every unit, and cloud-init schema validation for every device file, all inside the tools container. Device files use two Raspberry Pi-only keys (`rpi:` and `enable_ssh:`) that upstream cloud-init does not know; the test strips them before validating, and the real Raspberry Pi cloud-init validates them in tier 2.

**Files:**
- Create: `testkit/tests/test_static.py`
- Create: `testkit/src/pihero_testkit/devices/all-features/user-data`, `meta-data` (first version; Task 10 finalises)

**Interfaces:**
- Produces: nothing new; establishes that `devices/*/user-data` in the repo and `pihero_testkit/devices/*/user-data` in the package are both validated.

- [ ] **Step 1: First device file for validation**

`testkit/src/pihero_testkit/devices/all-features/user-data` (the SSH key line is replaced in Task 10 after the key exists):

```yaml
#cloud-config
# board: QEMU virt (tier 2)  image: Raspberry Pi OS Lite 64-bit (Trixie)
hostname: all-features
manage_etc_hosts: true
enable_ssh: true
ssh_pwauth: false
users:
  - name: pihero
    groups: users,adm,sudo,gpio,spi,i2c,netdev,plugdev
    shell: /bin/bash
    lock_passwd: true
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPLACEHOLDERREPLACEDINTASK10 pihero-testkit
package_update: true
apt:
  sources:
    pihero-local:
      source: deb [trusted=yes] http://10.0.2.2:8000/ ./
packages:
  - avahi-utils
  - pihero
write_files:
  - path: /etc/pihero/device-info.conf
    content: MODEL=MacPro7,1@ECOLOR=226,226,224
runcmd:
  - hostnamectl set-hostname --pretty "All Features"
power_state:
  mode: reboot
  condition: test -f /run/reboot-required
```

`testkit/src/pihero_testkit/devices/all-features/meta-data`:

```yaml
instance-id: pihero-all-features-1
local-hostname: all-features
```

- [ ] **Step 2: Write the failing tests**

`testkit/tests/test_static.py`:

```python
import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from pihero_testkit import tools

pytestmark = pytest.mark.tier0

ROOT = Path.cwd()
TESTKIT_DEVICES = Path(str(files("pihero_testkit") / "devices"))
STRIP_RPI_KEYS = (
    "import sys, yaml; d = yaml.safe_load(open(sys.argv[1])); "
    "[d.pop(k, None) for k in ('rpi', 'enable_ssh')]; "
    "open(sys.argv[2], 'w').write('#cloud-config\\n' + yaml.safe_dump(d))"
)


@pytest.mark.parametrize("script", sorted(shell_files()), ids=lambda p: str(p.relative_to(ROOT)))
def test_shell_file_passes_shellcheck(script):
    result = tools.run(["shellcheck", f"/work/{script.relative_to(ROOT)}"], check=False, capture=True)

    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("unit", sorted(unit_files()), ids=lambda p: p.name)
def test_unit_passes_systemd_analyze_verify(unit):
    package_root = unit.parents[4]
    result = tools.run(
        ["systemd-analyze", "verify", "--man=no", f"/work/{unit.relative_to(ROOT)}"],
        mounts=[f"{package_root / 'usr' / 'lib' / 'pihero'}:/usr/lib/pihero:ro"],
        check=False, capture=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("user_data", sorted(device_files()), ids=lambda p: p.parent.name)
def test_device_file_validates_against_cloud_init_schema(user_data):
    staged = ROOT / "dist" / "schema" / user_data.parent.name
    staged.mkdir(parents=True, exist_ok=True)
    shutil.copy(user_data, staged / "user-data")
    relative = staged.relative_to(ROOT)

    result = tools.run(
        ["sh", "-c", f"python3 -c \"{STRIP_RPI_KEYS}\" /work/{relative}/user-data /work/{relative}/stripped && cloud-init schema --config-file /work/{relative}/stripped"],
        check=False, capture=True,
    )

    assert user_data.read_text().startswith("#cloud-config\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Valid schema" in result.stdout


def shell_files():
    for path in (ROOT / "packages").rglob("*"):
        if not path.is_file() or path.is_symlink() or ".build" in path.parts:
            continue
        first_line = path.open("rb").readline()
        if path.suffix == ".sh" or (first_line.startswith(b"#!") and b"sh" in first_line):
            yield path


def unit_files():
    yield from (ROOT / "packages").glob("*/root/usr/lib/systemd/system/*.service")


def device_files():
    yield from (ROOT / "devices").glob("*/user-data")
    yield from TESTKIT_DEVICES.glob("*/user-data")
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest testkit/tests/test_static.py -v`
Expected: the shellcheck tests for `50-pihero`, `postinst.sh`, `postrm.sh` run; the schema test for `all-features` runs. Any failures point at real problems in the files (fix them); a failure of the form `cloud-init: command not found` means the tools image predates the Containerfile from Task 3 and `make tools` needs to run.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest testkit/tests/test_static.py -v`
Expected: all passed; the unit test is collected with zero parameters until Task 14 adds a unit.

- [ ] **Step 5: Commit**

```bash
git add testkit
git commit -m "test(testkit): static checks for shell files, units and device files

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 10: Tier 2 harness — QEMU VM from a device file

Promotes the spike into `prepare`, `bootfs`, `repo`, `vm`, and the `boot` tests. Apply the adjustments recorded in `docs/spikes/2026-09-27-tier2-vm.md`, in particular the exact `cmdline.txt` substitutions and any masked units. Ends with `make test-tier2` green.

**Files:**
- Create: `testkit/src/pihero_testkit/images.lock`
- Create: `testkit/src/pihero_testkit/prepare-rootfs` (bash, executable), `prepare.py`, `bootfs.py`, `repo.py`, `vm.py`, `ssh.py`, `deploy.py`
- Create: `testkit/src/pihero_testkit/keys/pihero-testkit`, `pihero-testkit.pub`
- Modify: `testkit/src/pihero_testkit/devices/all-features/user-data` (real key)
- Create: `testkit/tests/test_bootfs.py`, `testkit/tests/test_boot.py`

**Interfaces:**
- Produces: `prepare.prepare(force=False) -> BaseImage(rootfs: Path, kernel: Path, initrd: Path, boot: Path)`; `bootfs.build_bootfs(device_dir, stock_boot, out) -> Path`; `bootfs.read_cmdline(image) -> str`; `bootfs.kernel_args(cmdline) -> str`; `repo.build_repo(debs, out) -> Path`; `repo.Server(directory, port=8000)` with `.close()`; `vm.Vm` with `.start()`, `.wait_provisioned()`, `.reboot()`, `.stop()`, `.host`, `.ssh(cmd)`, `.install_extra(names)`, `.purge(names)`, `.reinstall()`, `.serial_log`; `vm.provisioned_vm(debs, device_dir, accel, keep)` context manager; `ssh.SshTarget(uri, debs)` implementing the target protocol over plain SSH.

- [ ] **Step 1: Insecure test key and image lock**

```bash
mkdir -p testkit/src/pihero_testkit/keys
ssh-keygen -t ed25519 -N '' -C pihero-testkit -f testkit/src/pihero_testkit/keys/pihero-testkit
```

Replace the placeholder `ssh_authorized_keys` line in `testkit/src/pihero_testkit/devices/all-features/user-data` with the content of `pihero-testkit.pub`. The private key is committed on purpose: it only ever opens throwaway VMs, the same way Vagrant's insecure key does.

`testkit/src/pihero_testkit/images.lock` (values from `docs/spikes/2026-09-27-tier2-vm.md`):

```toml
# Pinned upstream inputs of the tier-2 base image. Update url and sha256 together.
[raspios]
url = "URL_FROM_SPIKE"
sha256 = "SHA256_FROM_SPIKE"

[kernel]
package = "linux-image-arm64"
```

- [ ] **Step 2: Root filesystem preparation script**

`testkit/src/pihero_testkit/prepare-rootfs`:

```bash
#!/usr/bin/env bash
# Purpose: Turn a Raspberry Pi OS image into a QEMU virt bootable root filesystem with Debian's kernel.
# Usage:   prepare-rootfs --image <img|img.xz> --out <dir> [--kernel-package <name>]
#
# Options:
#   --image <path>            Raspberry Pi OS image, optionally xz-compressed.
#   --out <dir>               Output directory; receives rootfs.qcow2, vmlinuz, initrd.img and boot/.
#   --kernel-package <name>   Debian kernel metapackage (default: linux-image-arm64).
#   -h, --help                Show this help.
#
# Runs as root in a privileged container: it needs loop devices, mount and chroot.
#
# Examples:
#   prepare-rootfs --image /cache/downloads/raspios-lite.img.xz --out /cache/base/3f9a2c1b0d4e

set -euo pipefail

usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"; }
die()   { printf '%s: %s\nSee '\''%s --help'\''\n' "${0##*/}" "$1" "${0##*/}" >&2; exit 2; }
log()   { printf '%s %s\n' "$(tput setaf 3 2>/dev/null || true)⚙$(tput sgr0 2>/dev/null || true)" "$*" >&2; }

image=; out=; kernel_package=linux-image-arm64
while (( $# )); do
  case $1 in
    -h|--help)          usage; exit 0 ;;
    --image)            image=${2?--image: missing value}; shift 2 ;;
    --image=*)          image=${1#*=}; shift ;;
    --out)              out=${2?--out: missing value}; shift 2 ;;
    --out=*)            out=${1#*=}; shift ;;
    --kernel-package)   kernel_package=${2?--kernel-package: missing value}; shift 2 ;;
    --kernel-package=*) kernel_package=${1#*=}; shift ;;
    -?*)                die "unknown option: $1" ;;
    *)                  die "unexpected argument: $1" ;;
  esac
done
[[ -n $image && -n $out ]] || { usage >&2; exit 2; }

work=$(mktemp -d)
root=$work/root
loop=
cleanup() {
  set +e
  for m in dev/pts dev sys proc boot/firmware ''; do
    mountpoint -q "$root/$m" && umount "$root/$m"
  done
  [[ -n $loop ]] && losetup -d "$loop"
  rm -rf "$work"
}
trap cleanup EXIT

log "decompressing image"
raw=$work/raspios.img
case $image in
  *.xz) xz -dc "$image" >"$raw" ;;
  *)    cp "$image" "$raw" ;;
esac

log "mounting partitions"
loop=$(losetup --find --show --partscan "$raw")
mkdir -p "$root"
mount "${loop}p2" "$root"
mount "${loop}p1" "$root/boot/firmware"

log "saving stock boot files"
mkdir -p "$out/boot"
cp "$root/boot/firmware/config.txt" "$root/boot/firmware/cmdline.txt" "$out/boot/"

log "installing $kernel_package in chroot"
for m in proc sys dev dev/pts; do mount --bind "/$m" "$root/$m"; done
cp --remove-destination /etc/resolv.conf "$root/etc/resolv.conf"
chroot "$root" env DEBIAN_FRONTEND=noninteractive apt-get update -q
chroot "$root" env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends "$kernel_package"

log "adapting fstab and cloud-init ordering"
sed -i -E 's|^PARTUUID=[^ ]+-01 |LABEL=bootfs |; s|^PARTUUID=[^ ]+-02 |LABEL=rootfs |' "$root/etc/fstab"
install -d "$root/etc/systemd/system/cloud-init-local.service.d"
printf '[Unit]\nRequiresMountsFor=/boot/firmware\n' >"$root/etc/systemd/system/cloud-init-local.service.d/pihero-bootfs.conf"

log "extracting kernel and initrd"
cp "$(ls "$root"/boot/vmlinuz-*-arm64 | sort -V | tail -1)" "$out/vmlinuz"
cp "$(ls "$root"/boot/initrd.img-*-arm64 | sort -V | tail -1)" "$out/initrd.img"
for m in dev/pts dev sys proc boot/firmware; do umount "$root/$m"; done

log "packing root filesystem"
truncate -s 6G "$work/rootfs.img"
mkfs.ext4 -q -L rootfs -d "$root" "$work/rootfs.img"
umount "$root"
qemu-img convert -f raw -O qcow2 "$work/rootfs.img" "$out/rootfs.qcow2"
log "done: $out"
```

`chmod 755 testkit/src/pihero_testkit/prepare-rootfs`. If the spike found that the `raspi-firmware` kernel hook or loop devices need a different approach, put that approach here and note it in a one-line comment above the affected block.

- [ ] **Step 3: prepare.py**

```python
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


@dataclass(frozen=True)
class BaseImage:
    rootfs: Path
    kernel: Path
    initrd: Path
    boot: Path


def lock() -> dict:
    return tomllib.loads(LOCK.read_text())


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
    key = hashlib.sha256((config["raspios"]["sha256"] + config["kernel"]["package"] + SCRIPT.read_text()).encode()).hexdigest()[:12]
    out = CACHE / "base" / key
    if force or not (out / "done").exists():
        image = download(config["raspios"]["url"], config["raspios"]["sha256"])
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
```

- [ ] **Step 4: bootfs.py with its failing test first**

`testkit/tests/test_bootfs.py`:

```python
import pytest

from pihero_testkit import bootfs

pytestmark = pytest.mark.tier0

STOCK = "console=serial0,115200 console=tty1 root=PARTUUID=0a1b2c3d-02 rootfstype=ext4 fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles cfg80211.ieee80211_regdom=DE"


class TestKernelArgs:
    def test_replaces_root_and_console_and_keeps_the_rest(self):
        args = bootfs.kernel_args(STOCK)

        assert args.startswith("root=LABEL=rootfs console=ttyAMA0,115200 ")
        assert "PARTUUID" not in args
        assert "console=tty1" not in args
        assert args.endswith("rootfstype=ext4 fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles cfg80211.ieee80211_regdom=DE")

    def test_drops_a_firstboot_init(self):
        args = bootfs.kernel_args(STOCK + " init=/usr/lib/raspberrypi-sys-mods/firstboot")

        assert "init=" not in args

    def test_keeps_parameters_added_by_bootconfig(self):
        args = bootfs.kernel_args(STOCK + " logo.nologo pihero.probe=1")

        assert args.endswith("logo.nologo pihero.probe=1")
```

Run: `uv run pytest testkit/tests/test_bootfs.py -v` → FAIL at import. Then `testkit/src/pihero_testkit/bootfs.py`:

```python
"""Builds the FAT boot partition image for a device directory and derives the kernel command line from it."""

import shutil
from pathlib import Path

from . import tools

SIZE_KIB = 65536
HARNESS_OWNED = ("root=", "console=", "init=")


def build_bootfs(device_dir: Path, stock_boot: Path, out: Path) -> Path:
    staging = out.parent / f"{out.stem}.d"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    for name in ("config.txt", "cmdline.txt"):
        shutil.copy(stock_boot / name, staging / name)
    for file in device_dir.iterdir():
        if file.is_file():
            shutil.copy(file, staging / file.name)
    if not (staging / "meta-data").exists():
        (staging / "meta-data").write_text(f"instance-id: pihero-{device_dir.name}-1\nlocal-hostname: {device_dir.name}\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    tools.run(
        ["sh", "-c", f"rm -f /out/{out.name} && mkfs.vfat -n bootfs -C /out/{out.name} {SIZE_KIB} >/dev/null && mcopy -i /out/{out.name} -s /staging/* ::/"],
        mounts=[f"{out.parent}:/out", f"{staging}:/staging:ro"],
    )
    return out


def read_cmdline(image: Path) -> str:
    result = tools.run(["mtype", "-i", f"/out/{image.name}", "::/cmdline.txt"], mounts=[f"{image.parent}:/out:ro"], capture=True)
    return result.stdout.strip()


def kernel_args(cmdline: str) -> str:
    """Returns cmdline.txt adapted for QEMU virt: root by label, serial console on ttyAMA0, no firstboot init."""
    kept = [p for p in cmdline.split() if not p.startswith(HARNESS_OWNED)]
    return " ".join(["root=LABEL=rootfs", "console=ttyAMA0,115200", *kept])
```

Run: `uv run pytest testkit/tests/test_bootfs.py -v` → 3 passed.

- [ ] **Step 5: repo.py**

```python
"""Flat apt repository: index generation with apt-ftparchive, signing, and a local HTTP server for the VM."""

import functools
import http.server
import shutil
import threading
from pathlib import Path

from . import tools

RELEASE_OPTIONS = [
    "-o", "APT::FTPArchive::Release::Origin=pihero",
    "-o", "APT::FTPArchive::Release::Label=pihero",
    "-o", "APT::FTPArchive::Release::Suite=stable",
    "-o", "APT::FTPArchive::Release::Architectures=all",
    "-o", "APT::FTPArchive::Release::Description=Pi Hero packages",
]


def build_repo(debs: list[Path], out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    for deb in debs:
        shutil.copy(deb, out / deb.name)
    relative = out.relative_to(Path.cwd())
    options = " ".join(RELEASE_OPTIONS)
    tools.run(["sh", "-c", f"cd /work/{relative} && apt-ftparchive packages . > Packages && gzip -kf Packages && apt-ftparchive {options} release . > Release"])
    return out


def sign_repo(repo: Path, private_key: Path) -> None:
    relative = repo.relative_to(Path.cwd())
    tools.run(
        ["sh", "-c", f"gpg --batch --import /key/{private_key.name} && cd /work/{relative} && gpg --batch --yes -abs -o Release.gpg Release && gpg --batch --yes --clearsign -o InRelease Release"],
        mounts=[f"{private_key.parent}:/key:ro"],
    )


class Server:
    def __init__(self, directory: Path, port: int = 8000):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.port = port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
```

- [ ] **Step 6: vm.py**

```python
"""Boots the tier-2 VM: QEMU virt with the prepared base image, a bootfs image built from a device directory, and a local apt repo.

The harness plays the firmware: it reads cmdline.txt from the bootfs image on every boot and QEMU runs with
-no-reboot, so a guest reboot returns here and the next boot picks up edited boot files.
"""

import argparse
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

import testinfra

from . import bootfs as bootfs_mod
from . import build, prepare, repo

PACKAGE_DIR = Path(str(files("pihero_testkit")))
KEY = PACKAGE_DIR / "keys" / "pihero-testkit"
DEFAULT_DEVICE = PACKAGE_DIR / "devices" / "all-features"
REPO_PORT = 8000
SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "LogLevel=ERROR"]
SSH_CONNECTION_FAILED = 255


class Vm:
    def __init__(self, base: prepare.BaseImage, bootfs: Path, workdir: Path, accel: str = "hvf", user: str = "pihero", memory_mb: int = 1024, debs: list[Path] = ()):
        self.base, self.bootfs, self.workdir, self.accel, self.user, self.memory_mb, self.debs = base, bootfs, workdir, accel, user, memory_mb, list(debs)
        self.overlay = workdir / "overlay.qcow2"
        self.serial_log = workdir / "serial.log"
        self.port = _free_port()
        self.process: subprocess.Popen | None = None
        self.boots = 0
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-b", str(base.rootfs), "-F", "qcow2", str(self.overlay)], check=True)

    def start(self) -> "Vm":
        append = bootfs_mod.kernel_args(bootfs_mod.read_cmdline(self.bootfs))
        cpu = ["-cpu", "host"] if self.accel == "hvf" else ["-cpu", "cortex-a72"]
        command = [
            "qemu-system-aarch64", "-M", "virt", "-accel", self.accel, *cpu, "-m", str(self.memory_mb), "-smp", "2",
            "-no-reboot", "-display", "none", "-monitor", "none",
            "-kernel", str(self.base.kernel), "-initrd", str(self.base.initrd), "-append", append,
            "-drive", f"if=none,file={self.overlay},format=qcow2,id=root", "-device", "virtio-blk-pci,drive=root",
            "-drive", f"if=none,file={self.bootfs},format=raw,id=boot", "-device", "virtio-blk-pci,drive=boot",
            "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{self.port}-:22", "-device", "virtio-net-pci,netdev=net0",
            "-device", "virtio-rng-pci", "-serial", f"file:{self.serial_log}",
        ]
        self.boots += 1
        with self.serial_log.open("a") as log:
            log.write(f"\n===== boot {self.boots}: {append}\n")
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        return self

    def ssh(self, command: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(["ssh", "-i", str(KEY), "-p", str(self.port), *SSH_OPTS, f"{self.user}@127.0.0.1", command], capture_output=True, text=True, timeout=timeout, check=False)

    def wait_ssh(self, timeout: int = 300) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"QEMU exited during boot {self.boots}; see {self.serial_log}\n{self.process.stderr.read()}")
            if self.ssh("true", timeout=15).returncode == 0:
                return
            time.sleep(2)
        raise TimeoutError(f"no SSH after {timeout}s; see {self.serial_log}")

    def wait_exit(self, timeout: int = 180) -> None:
        self.process.wait(timeout)

    def wait_provisioned(self, timeout: int = 900) -> None:
        """Follows cloud-init to the end, including the reboot its power_state requests, until no reboot is pending."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.wait_ssh(timeout=max(30, int(deadline - time.time())))
            status = self.ssh("cloud-init status --wait --long", timeout=600)
            if status.returncode == SSH_CONNECTION_FAILED or self._exited_within(15):
                self.start()
                continue
            if status.returncode != 0:
                raise RuntimeError(f"cloud-init failed (exit {status.returncode}):\n{status.stdout}{status.stderr}\n{self.ssh('sudo tail -n 60 /var/log/cloud-init.log').stdout}")
            pending = self.ssh("test -f /run/reboot-required")
            if pending.returncode == SSH_CONNECTION_FAILED or self._exited_within(15):
                self.start()
                continue
            if pending.returncode == 0:
                self.reboot()
                continue
            return
        raise TimeoutError(f"provisioning did not settle within {timeout}s; see {self.serial_log}")

    def _exited_within(self, seconds: int) -> bool:
        try:
            self.process.wait(seconds)
            return True
        except subprocess.TimeoutExpired:
            return False

    def reboot(self) -> None:
        self.ssh("sudo systemctl reboot")
        self.wait_exit()
        self.start()
        self.wait_ssh()

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(15)

    @property
    def host(self):
        return testinfra.get_host(f"ssh://{self.user}@127.0.0.1:{self.port}", ssh_identity_file=str(KEY), ssh_extra_args=" ".join(SSH_OPTS), sudo=True)

    def install_extra(self, names: list[str]) -> None:
        self.ssh("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q " + " ".join(names), timeout=900)

    def purge(self, names: list[str]) -> None:
        self.ssh("sudo DEBIAN_FRONTEND=noninteractive apt-get purge -y -q " + " ".join(names), timeout=600)

    def reinstall(self) -> None:
        self.ssh("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --reinstall " + " ".join(d.name.split("_")[0] for d in self.debs), timeout=900)

    def ssh_command(self) -> str:
        return f"ssh -i {KEY} -p {self.port} {' '.join(SSH_OPTS)} {self.user}@127.0.0.1"


@contextmanager
def provisioned_vm(debs: list[Path], device_dir: str | Path | None, accel: str, keep: bool):
    device = Path(device_dir) if device_dir else DEFAULT_DEVICE
    base = prepare.prepare()
    workdir = build.DIST / "vm" / device.name
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)
    server = repo.Server(repo.build_repo(debs, build.DIST / "repo"), port=REPO_PORT)
    try:
        vm = Vm(base, bootfs_mod.build_bootfs(device, base.boot, workdir / "bootfs.img"), workdir, accel=accel, debs=debs).start()
        try:
            vm.wait_provisioned()
            yield vm
        finally:
            if keep:
                print(f"\nVM kept running. Connect with:\n  {vm.ssh_command()}\nSerial log: {vm.serial_log}", file=sys.stderr)
            else:
                vm.stop()
    finally:
        server.close()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Boot the tier-2 VM from a device directory and keep it running.")
    parser.add_argument("--device", default=None)
    parser.add_argument("--qemu-accel", default="hvf")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    debs = build.build_all(build.version_from_git())
    with provisioned_vm(debs, args.device, args.qemu_accel, keep=True) as vm:
        print(vm.ssh_command())
        if args.keep:
            print("Press Ctrl-C to stop the VM.", file=sys.stderr)
            try:
                vm.process.wait()
            except KeyboardInterrupt:
                vm.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note on `provisioned_vm` with `keep=True` from `main()`: the server keeps serving until the process ends, which is what an interactive session wants.

- [ ] **Step 7: ssh.py and deploy.py**

`testkit/src/pihero_testkit/ssh.py`:

```python
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
```

`testkit/src/pihero_testkit/deploy.py`:

```python
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
```

- [ ] **Step 8: Boot tests**

`testkit/tests/test_boot.py`:

```python
import pytest

pytestmark = pytest.mark.boot


class TestProvisioning:
    def test_cloud_init_finished_without_errors(self, host):
        status = host.check_output("cloud-init status --long")

        assert "status: done" in status
        assert "errors: []" in status

    def test_boot_partition_is_the_bootfs_image(self, host):
        assert host.mount_point("/boot/firmware").exists
        assert host.file("/boot/firmware/user-data").exists

    def test_no_unit_failed(self, host):
        assert host.check_output("systemctl --failed --no-legend --plain").strip() == ""

    def test_no_reboot_is_pending(self, host):
        assert not host.file("/run/reboot-required").exists

    def test_pretty_hostname_was_applied(self, host):
        assert host.check_output("hostnamectl --pretty").strip() == "All Features"


class TestWatchdog:
    def test_is_armed(self, host):
        assert host.check_output("systemctl show --property=RuntimeWatchdogUSec").strip() == "RuntimeWatchdogUSec=15s"


class TestBootConfigRoundTrip:
    @pytest.mark.mutating
    def test_cmdline_edit_survives_a_reboot(self, target):
        target.host.check_output("sudo /usr/lib/pihero/bootconfig add cmdline pihero.marker=1 --package pihero-probe")
        assert target.host.file("/run/reboot-required").exists

        target.reboot()

        assert "pihero.marker=1" in target.host.file("/proc/cmdline").content_string
        assert not target.host.file("/run/reboot-required").exists
        target.host.check_output("sudo /usr/lib/pihero/bootconfig remove cmdline pihero.marker")
```

- [ ] **Step 9: Prepare, then run tier 2**

```bash
make vm-prepare
make test-tier2
```

Expected: the base image builds once (minutes), then the VM boots, cloud-init installs `pihero` from the local repo, the `power_state` reboot happens, and all `installed` and `boot` tests pass in under 10 minutes. On failure run `make vm` to keep a VM up and inspect it with the printed SSH command and `dist/vm/all-features/serial.log`.

- [ ] **Step 10: Commit**

```bash
git add testkit
git commit -m "feat(testkit): tier-2 target, a QEMU VM booted from a device file

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 11: Continuous integration

Tiers 0 and 1 on every push, tier 2 weekly under software emulation. The workflows can only be verified by pushing the branch and watching the runs.

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/weekly.yml`

- [ ] **Step 1: ci.yml**

```yaml
name: ci
on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  tier0:
    runs-on: ubuntu-24.04-arm
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: astral-sh/setup-uv@v6
        with: { enable-cache: true }
      - run: uv sync --frozen
      - run: make build
      - run: make test-tier0

  tier1:
    runs-on: ubuntu-24.04-arm
    strategy:
      fail-fast: false
      matrix:
        platform: [linux/arm64, linux/arm/v7]
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: astral-sh/setup-uv@v6
        with: { enable-cache: true }
      - uses: docker/setup-qemu-action@v3
        if: matrix.platform != 'linux/arm64'
      - run: uv sync --frozen
      - run: make test-tier1 PLATFORM=${{ matrix.platform }}
```

- [ ] **Step 2: weekly.yml**

```yaml
name: weekly
on:
  schedule:
    - cron: "0 4 * * 1"
  workflow_dispatch:

jobs:
  tier2:
    runs-on: ubuntu-latest
    timeout-minutes: 180
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: astral-sh/setup-uv@v6
        with: { enable-cache: true }
      - uses: docker/setup-qemu-action@v3
      - run: sudo apt-get update && sudo apt-get install -y qemu-system-arm qemu-utils
      - run: uv sync --frozen
      - uses: actions/cache@v4
        with:
          path: ~/.cache/pihero
          key: pihero-base-${{ hashFiles('testkit/src/pihero_testkit/images.lock', 'testkit/src/pihero_testkit/prepare-rootfs') }}
      - run: make test-tier2 QEMU_ACCEL=tcg
```

- [ ] **Step 3: Push and watch**

```bash
git add .github
git commit -m "ci: tiers 0 and 1 on push, tier 2 weekly under emulation

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin pihero-2
gh run watch
```

Expected: `tier0` and both `tier1` jobs green. If rootless podman cannot run systemd containers on the runner, add `PODMAN: sudo podman` to the job `env:` and re-push; if `docker/setup-qemu-action` does not register handlers for podman, add `sudo apt-get install -y qemu-user-static binfmt-support` before the tier-1 step. Trigger `weekly` once by hand with `gh workflow run weekly` and record its duration in the commit message of the fix-up, if one is needed.

---

## Task 12: Release pipeline and the device file samples

Tagging `vX.Y.Z` publishes a signed flat apt repository to GitHub Pages. This task also creates the signing key, writes the committed device file samples with the real public key, and gates `make release` on a local tier-2 run. A release candidate tag proves the pipeline before `v2.0.0` is cut in Task 16.

**Files:**
- Create: `.github/workflows/release.yml`
- Create: `devices/README.md`, `devices/sample/user-data`, `devices/sample/network-config`
- Create: `docs/pihero-apt.asc` (public key)
- Modify: `Makefile` (add `repo` and `release` targets)

- [ ] **Step 1: Signing key**

```bash
export GNUPGHOME=$(mktemp -d)
gpg --batch --quick-generate-key "Pi Hero apt repository <bkahlert@users.noreply.github.com>" ed25519 sign never
KEYID=$(gpg --list-keys --with-colons | awk -F: '/^pub/{print $5}')
gpg --armor --export "$KEYID" > docs/pihero-apt.asc
gpg --armor --export-secret-keys "$KEYID" | gh secret set APT_SIGNING_KEY
gpg --armor --export-secret-keys "$KEYID" > ~/.config/pihero-apt-signing-key.asc && chmod 600 ~/.config/pihero-apt-signing-key.asc
rm -rf "$GNUPGHOME"; unset GNUPGHOME
```

The private key now lives only in the GitHub secret and in `~/.config/pihero-apt-signing-key.asc` on the Mac for `make repo`.

- [ ] **Step 2: GitHub Pages**

```bash
git switch --orphan gh-pages && git rm -rf --quiet . ; mkdir -p apt && cp docs/pihero-apt.asc apt/ 2>/dev/null || git show pihero-2:docs/pihero-apt.asc > apt/pihero-apt.asc
git add apt && git commit -m "apt: initial gh-pages" && git push -u origin gh-pages
git switch pihero-2
gh api -X POST repos/bkahlert/pihero/pages -f 'source[branch]=gh-pages' -f 'source[path]=/' || gh api -X PUT repos/bkahlert/pihero/pages -f 'source[branch]=gh-pages' -f 'source[path]=/'
```

Expected: `https://bkahlert.github.io/pihero/apt/pihero-apt.asc` serves the public key after a minute.

- [ ] **Step 3: release.yml**

```yaml
name: release
on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  publish:
    runs-on: ubuntu-24.04-arm
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: astral-sh/setup-uv@v6
        with: { enable-cache: true }
      - run: uv sync --frozen
      - run: make build
      - run: make test-tier0
      - run: make test-tier1
      - name: Check out the published repository
        uses: actions/checkout@v4
        with:
          ref: gh-pages
          path: gh-pages
      - name: Add packages and regenerate the signed index
        env:
          APT_SIGNING_KEY: ${{ secrets.APT_SIGNING_KEY }}
        run: |
          printf '%s' "$APT_SIGNING_KEY" > "$RUNNER_TEMP/key.asc"
          uv run --frozen python -m pihero_testkit.repo publish --debs 'dist/*.deb' --repo gh-pages/apt --key "$RUNNER_TEMP/key.asc"
          rm -f "$RUNNER_TEMP/key.asc"
      - name: Push
        run: |
          cd gh-pages
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add -A
          git commit -m "apt: ${GITHUB_REF_NAME}"
          git push
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: dist/*.deb
```

Add the `publish` entry point to `testkit/src/pihero_testkit/repo.py`:

```python
def main(argv: list[str]) -> int:
    import argparse
    import glob

    parser = argparse.ArgumentParser(description="Maintain the flat apt repository.")
    sub = parser.add_subparsers(dest="command", required=True)
    publish = sub.add_parser("publish", help="copy packages into the repo directory, regenerate and sign the index")
    publish.add_argument("--debs", required=True, help="glob of .deb files")
    publish.add_argument("--repo", required=True, help="repository directory, existing packages are kept")
    publish.add_argument("--key", required=True, help="armored private signing key")
    args = parser.parse_args(argv)
    repo_dir = Path(args.repo).resolve()
    build_repo([Path(p) for p in sorted(glob.glob(args.debs))], repo_dir)
    sign_repo(repo_dir, Path(args.key).resolve())
    print(repo_dir)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
```

`build_repo` and `sign_repo` compute paths relative to `Path.cwd()`; `gh-pages/apt` is inside the checkout, so that holds in CI and locally.

- [ ] **Step 4: Makefile targets**

Append to `Makefile`:

```make
repo: build ## regenerate and sign the flat repo under dist/repo (needs ~/.config/pihero-apt-signing-key.asc)
	@$(UV) python -m pihero_testkit.repo publish --debs 'dist/*.deb' --repo dist/repo --key ~/.config/pihero-apt-signing-key.asc

release: ## run every tier locally, then tag VERSION (make release VERSION=2.0.0)
	@test -n "$(VERSION)" || { echo "usage: make release VERSION=X.Y.Z"; exit 2; }
	@git diff --quiet || { echo "working tree is dirty"; exit 1; }
	@$(MAKE) test-all
	git tag -a "v$(VERSION)" -m "v$(VERSION)"
	@echo "Tagged v$(VERSION). Push with: git push origin v$(VERSION)"
```

- [ ] **Step 5: Device file samples**

`devices/README.md`:

```markdown
# Device files

One directory per device, holding the cloud-init files that go onto the boot partition after flashing:
`user-data` (required), `network-config` (Wi-Fi, optional), `meta-data` (optional).

Real device directories are gitignored; keep them here or in a private repository. `sample/` is the reference.

Flash Raspberry Pi OS Lite (Trixie) with Raspberry Pi Imager, skip its customisation, then with the card still mounted:

    cp devices/<host>/user-data devices/<host>/network-config /Volumes/bootfs/

Boot. The device installs its packages, reboots once if a package asked for it, and appears as `<hostname>.local`.
```

`devices/sample/user-data` (paste the key from `docs/pihero-apt.asc` under `key:`, indented by eight spaces):

```yaml
#cloud-config
# board: Raspberry Pi Zero 2 W  image: Raspberry Pi OS Lite 64-bit (Trixie)
hostname: sample
manage_etc_hosts: true
timezone: Europe/Berlin
enable_ssh: true
ssh_pwauth: false
users:
  - name: pi
    groups: users,adm,dialout,audio,netdev,video,plugdev,input,gpio,spi,i2c,render,sudo
    shell: /bin/bash
    lock_passwd: true
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - ssh-ed25519 AAAA...your public key... you@mac
rpi:
  enable_usb_gadget: true
  spi: false
  i2c: false
  serial: true
package_update: true
apt:
  sources:
    pihero:
      source: deb [signed-by=$KEY_FILE] https://bkahlert.github.io/pihero/apt ./
      key: |
        -----BEGIN PGP PUBLIC KEY BLOCK-----
        ...contents of docs/pihero-apt.asc...
        -----END PGP PUBLIC KEY BLOCK-----
packages:
  - pihero
  - pihero-avahi
write_files:
  - path: /etc/pihero/device-info.conf
    content: MODEL=AirPort4
runcmd:
  - hostnamectl set-hostname --pretty "Sample Pi"
  - nmcli connection modify "USB Gadget (shared)" ipv4.addresses 10.10.10.10/29
power_state:
  mode: reboot
  condition: test -f /run/reboot-required
```

`devices/sample/network-config`:

```yaml
network:
  version: 2
  wifis:
    renderer: NetworkManager
    wlan0:
      dhcp4: true
      regulatory-domain: "DE"
      access-points:
        "My Network":
          password: "my-wifi-password"
      optional: true
```

- [ ] **Step 6: Validate and run the release candidate**

```bash
make test-tier0
make repo && ls dist/repo
git add .github Makefile devices docs/pihero-apt.asc testkit
git commit -m "feat: signed flat apt repository on GitHub Pages, release workflow, device file samples

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
git tag -a v2.0.0-rc.1 -m "v2.0.0-rc.1" && git push origin v2.0.0-rc.1
gh run watch
curl -fsS https://bkahlert.github.io/pihero/apt/InRelease | head -5
curl -fsS https://bkahlert.github.io/pihero/apt/Packages | grep -E '^(Package|Version):'
```

Expected: `dist/repo` contains `Packages`, `Packages.gz`, `Release`, `Release.gpg`, `InRelease`; the release workflow is green; `InRelease` begins with `-----BEGIN PGP SIGNED MESSAGE-----`; `Packages` lists `pihero` at `2.0.0~rc.1`.

---

## Task 13: `avahi-render`

The renderer behind `pihero-avahi`: pretty hostname, `model=` from the environment, `machine=` from the device tree, two Avahi service files, written only when their content changes.

**Files:**
- Create: `packages/pihero-avahi/root/usr/lib/pihero/avahi-render` (executable, `#!/usr/bin/python3`)
- Create: `packages/pihero-avahi/root/usr/share/pihero/avahi/device-info.service.in`, `ssh.service.in`
- Create: `packages/pihero-avahi/tests/test_render.py`

**Interfaces:**
- Produces (module): `pretty_hostname() -> str`, `machine(model_file: Path) -> str | None`, `txt_record(key, value) -> str`, `render(templates: Path, name: str, model: str, machine_name: str | None) -> dict[str, str]` (keys `device-info.service`, `ssh.service`), `write_if_changed(path, content) -> bool`.
- Produces (CLI): reads `MODEL` (default `AirPort4`), `PIHERO_AVAHI_SERVICES` (default `/etc/avahi/services`), `PIHERO_AVAHI_TEMPLATES` (default `/usr/share/pihero/avahi`), `PIHERO_DEVICE_TREE_MODEL` (default `/proc/device-tree/model`); writes `pihero-device-info.service` and `pihero-ssh.service` into the services directory; exit 0.

- [ ] **Step 1: Templates**

`packages/pihero-avahi/root/usr/share/pihero/avahi/device-info.service.in`:

```xml
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">${name}</name>
  <service>
    <type>_device-info._tcp</type>
    ${txt_records}
  </service>
</service-group>
```

`packages/pihero-avahi/root/usr/share/pihero/avahi/ssh.service.in`:

```xml
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">${name}</name>
  <service>
    <type>_ssh._tcp</type>
    <port>22</port>
  </service>
  <service>
    <type>_sftp-ssh._tcp</type>
    <port>22</port>
  </service>
</service-group>
```

- [ ] **Step 2: Write the failing tests**

`packages/pihero-avahi/tests/test_render.py`:

```python
import base64
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "root"
SCRIPT = PACKAGE_ROOT / "usr" / "lib" / "pihero" / "avahi-render"
TEMPLATES = PACKAGE_ROOT / "usr" / "share" / "pihero" / "avahi"
render_script = load_script(SCRIPT)


class TestRender:
    def test_uses_the_name_for_both_services(self):
        files = render_script.render(TEMPLATES, "Foo", "AirPort4", None)

        assert sorted(files) == ["device-info.service", "ssh.service"]
        assert all('<name replace-wildcards="yes">Foo</name>' in content for content in files.values())

    def test_escapes_xml_special_characters_in_the_name(self):
        files = render_script.render(TEMPLATES, "Foo & <Bar>", "AirPort4", None)

        assert "Foo &amp; &lt;Bar&gt;" in files["ssh.service"]
        ET.fromstring(files["ssh.service"])

    def test_keeps_unicode_names(self):
        files = render_script.render(TEMPLATES, "(ノಠ益ಠ)ノ彡 ⬬", "AirPort4", None)

        assert "(ノಠ益ಠ)ノ彡 ⬬" in files["device-info.service"]
        ET.fromstring(files["device-info.service"])

    def test_encodes_the_model_record_as_base64(self):
        files = render_script.render(TEMPLATES, "Foo", "MacPro7,1@ECOLOR=226,226,224", None)

        records = txt_records(files["device-info.service"])
        assert records == ["model=MacPro7,1@ECOLOR=226,226,224"]

    def test_adds_the_machine_record_when_known(self):
        files = render_script.render(TEMPLATES, "Foo", "AirPort4", "Raspberry Pi Zero W Rev 1.1")

        assert txt_records(files["device-info.service"]) == ["model=AirPort4", "machine=Raspberry Pi Zero W Rev 1.1"]

    def test_omits_the_machine_record_when_unknown(self):
        files = render_script.render(TEMPLATES, "Foo", "AirPort4", None)

        assert not any(record.startswith("machine=") for record in txt_records(files["device-info.service"]))


class TestMachine:
    def test_reads_the_device_tree_model_and_strips_the_trailing_nul(self, tmp_path):
        model = tmp_path / "model"
        model.write_bytes(b"Raspberry Pi Zero W Rev 1.1\x00")

        assert render_script.machine(model) == "Raspberry Pi Zero W Rev 1.1"

    def test_is_none_on_a_missing_file(self, tmp_path):
        assert render_script.machine(tmp_path / "model") is None


class TestWriteIfChanged:
    def test_writes_once_and_reports_no_change_afterwards(self, tmp_path):
        target = tmp_path / "x.service"

        first = render_script.write_if_changed(target, "a")
        second = render_script.write_if_changed(target, "a")

        assert (first, second) == (True, False)
        assert target.read_text() == "a"


class TestCli:
    def test_renders_both_services_with_defaults(self, tmp_path):
        services = tmp_path / "services"
        services.mkdir()

        result = cli(services, tmp_path / "missing-model", env={})

        assert result.returncode == 0, result.stderr
        device_info = ET.parse(services / "pihero-device-info.service").getroot()
        ET.parse(services / "pihero-ssh.service")
        assert txt_records(ET.tostring(device_info, encoding="unicode")) == ["model=AirPort4"]

    def test_applies_model_from_the_environment_unchanged(self, tmp_path):
        services = tmp_path / "services"
        services.mkdir()
        model_file = tmp_path / "model"
        model_file.write_bytes(b"QEMU virt\x00")

        cli(services, model_file, env={"MODEL": "MacPro7,1@ECOLOR=226,226,224"})

        assert txt_records((services / "pihero-device-info.service").read_text()) == ["model=MacPro7,1@ECOLOR=226,226,224", "machine=QEMU virt"]


def txt_records(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    return [base64.b64decode(element.text).decode() for element in root.iter("txt-record")]


def cli(services: Path, model_file: Path, env: dict) -> subprocess.CompletedProcess:
    base_env = {key: value for key, value in os.environ.items() if key != "MODEL"}
    full_env = {**base_env, "PIHERO_AVAHI_SERVICES": str(services), "PIHERO_AVAHI_TEMPLATES": str(TEMPLATES), "PIHERO_DEVICE_TREE_MODEL": str(model_file), **env}
    return subprocess.run([sys.executable, str(SCRIPT)], env=full_env, capture_output=True, text=True)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest packages/pihero-avahi/tests/test_render.py -v`
Expected: FAIL at import.

- [ ] **Step 4: Implement**

`packages/pihero-avahi/root/usr/lib/pihero/avahi-render`:

```python
#!/usr/bin/python3
"""Renders Pi Hero's Avahi service records from the device's identity.

Environment:
  MODEL                     device-info model string shown by macOS (default AirPort4)
  PIHERO_AVAHI_SERVICES     output directory (default /etc/avahi/services)
  PIHERO_AVAHI_TEMPLATES    template directory (default /usr/share/pihero/avahi)
  PIHERO_DEVICE_TREE_MODEL  device-tree model file (default /proc/device-tree/model)
"""

import base64
import os
import socket
import subprocess
import sys
from pathlib import Path
from string import Template
from xml.sax.saxutils import escape


def pretty_hostname() -> str:
    try:
        pretty = subprocess.run(["hostnamectl", "--pretty"], capture_output=True, text=True, check=False).stdout.strip()
    except FileNotFoundError:
        pretty = ""
    return pretty or socket.gethostname()


def machine(model_file: Path) -> str | None:
    try:
        return model_file.read_bytes().rstrip(b"\x00").decode().strip() or None
    except OSError:
        return None


def txt_record(key: str, value: str) -> str:
    encoded = base64.b64encode(f"{key}={value}".encode()).decode()
    return f'<txt-record value-format="binary-base64">{encoded}</txt-record>'


def render(templates: Path, name: str, model: str, machine_name: str | None) -> dict[str, str]:
    records = [txt_record("model", model)]
    if machine_name:
        records.append(txt_record("machine", machine_name))
    values = {"name": escape(name), "txt_records": "\n    ".join(records)}
    return {template.name.removesuffix(".in"): Template(template.read_text()).substitute(values) for template in sorted(templates.glob("*.service.in"))}


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text() == content:
        return False
    path.write_text(content)
    return True


def main() -> int:
    services = Path(os.environ.get("PIHERO_AVAHI_SERVICES", "/etc/avahi/services"))
    templates = Path(os.environ.get("PIHERO_AVAHI_TEMPLATES", "/usr/share/pihero/avahi"))
    device_tree = Path(os.environ.get("PIHERO_DEVICE_TREE_MODEL", "/proc/device-tree/model"))
    model = os.environ.get("MODEL") or "AirPort4"
    for name, content in render(templates, pretty_hostname(), model, machine(device_tree)).items():
        write_if_changed(services / f"pihero-{name}", content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`chmod 755 packages/pihero-avahi/root/usr/lib/pihero/avahi-render`

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest packages/pihero-avahi/tests/test_render.py -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add packages/pihero-avahi
git commit -m "feat(pihero-avahi): render device-info and ssh records from device identity

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 14: The `pihero-avahi` package

Manifest, render unit, purge fragment, and the installed-state tests across tiers. Adds `pihero-avahi` to the all-features device so tier 2 covers it.

**Files:**
- Create: `packages/pihero-avahi/nfpm.yaml`, `units.txt`, `scripts/postrm.sh`
- Create: `packages/pihero-avahi/root/usr/lib/systemd/system/pihero-avahi-render.service`
- Create: `packages/pihero-avahi/tests/test_installed.py`
- Modify: `testkit/src/pihero_testkit/devices/all-features/user-data` (add `pihero-avahi` to `packages`)

- [ ] **Step 1: Package files**

`packages/pihero-avahi/nfpm.yaml`:

```yaml
name: pihero-avahi
arch: all
platform: linux
version: ${VERSION}
section: admin
priority: optional
maintainer: Björn Kahlert <bkahlert@users.noreply.github.com>
description: |
  Pi Hero: advertise the device on the local network.
  Publishes _device-info._tcp with model and board, and _ssh._tcp/_sftp-ssh._tcp,
  under the pretty hostname.
homepage: https://github.com/bkahlert/pihero
license: MIT
depends:
  - pihero
  - avahi-daemon
contents:
  - src: root/
    dst: /
    type: tree
scripts:
  postinstall: .build/postinst
  preremove: .build/prerm
  postremove: .build/postrm
```

`packages/pihero-avahi/units.txt`:

```text
pihero-avahi-render.service
```

`packages/pihero-avahi/root/usr/lib/systemd/system/pihero-avahi-render.service`:

```ini
[Unit]
Description=Pi Hero: render Avahi service records
Before=avahi-daemon.service
After=systemd-hostnamed.service

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=-/etc/pihero/device-info.conf
ExecStart=/usr/lib/pihero/avahi-render
ExecStartPost=/bin/sh -c 'systemctl try-reload-or-restart avahi-daemon.service || true'

[Install]
WantedBy=multi-user.target
```

The `ExecStartPost` makes a manual `systemctl restart pihero-avahi-render` a complete change procedure without also naming avahi; at boot avahi has not started yet and the call is a no-op.

`packages/pihero-avahi/scripts/postrm.sh`:

```sh
# shellcheck shell=sh
rm -f /etc/avahi/services/pihero-device-info.service /etc/avahi/services/pihero-ssh.service
if [ -d /run/systemd/system ]; then
  systemctl try-reload-or-restart avahi-daemon.service >/dev/null 2>&1 || true
fi
```

Add `pihero-avahi` under `packages:` in `testkit/src/pihero_testkit/devices/all-features/user-data`, after `pihero`.

- [ ] **Step 2: Installed-state tests**

`packages/pihero-avahi/tests/test_installed.py`:

```python
import time

import pytest

pytestmark = pytest.mark.installed


class TestUnit:
    def test_is_enabled_and_active(self, host):
        unit = host.service("pihero-avahi-render")

        assert unit.is_enabled
        assert unit.is_running


class TestRecords:
    def test_files_are_rendered(self, host):
        assert host.file("/etc/avahi/services/pihero-device-info.service").contains("_device-info._tcp")
        assert host.file("/etc/avahi/services/pihero-ssh.service").contains("_sftp-ssh._tcp")

    def test_device_info_is_advertised(self, host, avahi_utils):
        browse = browse_until(host, "_device-info._tcp", "model=")

        expected = configured_model(host) or "AirPort4"
        assert f"model={expected}" in browse

    def test_ssh_is_advertised(self, host, avahi_utils):
        browse = browse_until(host, "_ssh._tcp", "_ssh._tcp")

        assert "22" in browse


class TestOverride:
    @pytest.mark.mutating
    def test_model_from_the_conffile_is_applied_on_restart(self, host, avahi_utils):
        previous = host.file("/etc/pihero/device-info.conf").content_string if host.file("/etc/pihero/device-info.conf").exists else None
        host.check_output("printf 'MODEL=Xserve\\n' | sudo tee /etc/pihero/device-info.conf >/dev/null")

        host.check_output("sudo systemctl restart pihero-avahi-render.service")

        assert "model=Xserve" in browse_until(host, "_device-info._tcp", "model=Xserve")
        restore = f"printf '%s' '{previous}' | sudo tee /etc/pihero/device-info.conf >/dev/null" if previous else "sudo rm -f /etc/pihero/device-info.conf"
        host.check_output(restore + " && sudo systemctl restart pihero-avahi-render.service")


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_removes_the_rendered_records(self, host, target):
        target.purge(["pihero-avahi"])

        assert not host.file("/etc/avahi/services/pihero-device-info.service").exists
        assert not host.file("/etc/avahi/services/pihero-ssh.service").exists

        target.reinstall()


@pytest.fixture(scope="module")
def avahi_utils(target):
    if not target.host.exists("avahi-browse"):
        target.install_extra(["avahi-utils"])


def configured_model(host) -> str | None:
    conf = host.file("/etc/pihero/device-info.conf")
    if not conf.exists:
        return None
    for line in conf.content_string.splitlines():
        if line.startswith("MODEL="):
            return line.removeprefix("MODEL=").strip()
    return None


def browse_until(host, service_type: str, needle: str, attempts: int = 10) -> str:
    output = ""
    for _ in range(attempts):
        output = host.run(f"avahi-browse -rpt {service_type}").stdout
        if needle in output:
            return output
        time.sleep(1)
    return output
```

- [ ] **Step 3: Tier 0 and tier 1**

```bash
make test-tier0
make test-tier1
```

Expected: the new unit passes `systemd-analyze verify`; in the container the render unit is active, both files exist, and `avahi-browse` shows `model=AirPort4`. If `avahi-browse` prints nothing in the container although the daemon is active, the container has no multicast-capable interface; check the spike notes, and if that was the finding, restrict `test_device_info_is_advertised` and `test_ssh_is_advertised` with `@pytest.mark.boot` so they run in tiers 2 and 4 only, keeping `test_files_are_rendered` in tier 1.

- [ ] **Step 4: Tier 2**

Run: `make test-tier2`
Expected: the VM installs `pihero-avahi` from the local repo; `avahi-browse` shows `model=MacPro7,1@ECOLOR=226,226,224` and `machine=linux,dummy-virt` (the model string QEMU's virt machine puts in the device tree), and the name `All Features`.

- [ ] **Step 5: Commit**

```bash
git add packages/pihero-avahi testkit
git commit -m "feat(pihero-avahi): package, render unit, installed-state tests

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 15: Checkpoint on real hardware

A single manual pass to confirm the pipeline meets reality, as the spec asks at step 3. Not a tier. Needs one Raspberry Pi with Wi-Fi or Ethernet, a card, and the Mac on the same network.

- [ ] **Step 1: Device file**

```bash
mkdir -p devices/checkpoint && cp devices/sample/user-data devices/sample/network-config devices/checkpoint/
```

Edit `devices/checkpoint/user-data`: `hostname: checkpoint`, your SSH public key, the pretty hostname `Checkpoint`, and replace the apt `source:` line with `deb [trusted=yes] https://bkahlert.github.io/pihero/apt ./` only if the release-candidate repository is unsigned; otherwise keep the signed form. Edit `network-config` with your Wi-Fi. `devices/checkpoint/` is gitignored.

- [ ] **Step 2: Flash and boot**

Flash Raspberry Pi OS Lite 64-bit (Trixie) with Raspberry Pi Imager 2.0 and decline its customisation. With the card mounted:

```bash
cp devices/checkpoint/user-data devices/checkpoint/network-config /Volumes/bootfs/
diskutil unmount /Volumes/bootfs
```

Boot the Pi and wait about three minutes.

- [ ] **Step 3: Verify**

```bash
dns-sd -B _device-info._tcp local. & sleep 3; kill %1
dns-sd -L Checkpoint _device-info._tcp local. & sleep 3; kill %1
ssh pi@checkpoint.local 'cat /run/motd.dynamic 2>/dev/null || /usr/lib/pihero/motd; cloud-init status --long; systemctl --failed'
uv run pytest -m installed --target=ssh --target-uri=pi@checkpoint.local
```

Expected: `Checkpoint` listed with the `model=` and `machine=Raspberry Pi ...` TXT records, the Pi shows up in Finder's network browser with its icon, the MOTD lists `pihero` and `pihero-avahi`, cloud-init `status: done`, no failed units, and the tier-4 run is green with the mutating tests skipped.

- [ ] **Step 4: Record**

Append a `## Checkpoint` section with the board, image date, time to first SSH, and any deviation to `docs/spikes/2026-09-27-tier2-vm.md`. Fix anything the checkpoint exposed in its own commit before moving on.

---

## Task 16: Tag `v2.0.0`

- [ ] **Step 1: Release**

```bash
make release VERSION=2.0.0
git push origin v2.0.0
gh run watch
curl -fsS https://bkahlert.github.io/pihero/apt/Packages | grep -A1 '^Package: pihero-avahi'
```

Expected: `make release` runs tiers 0 to 2 green and tags; the release workflow publishes; `Packages` lists `pihero` and `pihero-avahi` at `2.0.0`.

- [ ] **Step 2: Open the pull request**

```bash
gh pr create --base master --head pihero-2 --title "Pi Hero 2: packages, cloud-init, test harness, pihero and pihero-avahi" --body "$(cat <<'EOF'
Implements steps 1 to 3 of docs/superpowers/specs/2026-09-27-pihero-packages-design.md:
spikes, the package build and three-tier harness, the release pipeline, and the first two packages.

Ansible-based Pi Hero remains available at tag `pihero-ansible`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review

**Spec coverage.** Section 6 layout: Tasks 3, 4, 7, 14. Section 7 core package: Tasks 5, 6, 7. Section 8.1 `pihero-avahi`: Tasks 13, 14 (the `avahi-daemon.conf` edits were dropped by the spec's self-review and are correctly absent). Section 9 configuration contract: Task 9 device file, Task 10 bootfs and boot tests, Task 12 samples. Section 10 harness: Tasks 3, 4, 8, 9, 10, 11. Section 11 operations: reboot flags (Task 5), symmetric removal tests (Tasks 7, 14), release and signing (Task 12), `make deploy` (Task 10). Section 12 steps 1 to 3: Tasks 1, 2 (spikes), 3 to 12 (skeleton and `pihero`), 13 to 16 (`pihero-avahi`, checkpoint, tag). Sections 8.2 to 8.5 are later plans by design.

**Placeholders.** Three values are looked up during execution and are called out as such: the Debian image digest and nfpm version (Task 3), the Raspberry Pi OS image URL and checksum (Task 10 from Task 2), and the SSH public key line in the all-features device (Task 9, replaced in Task 10). No step says "add error handling" or "similar to Task N".

**Type consistency.** `tools.run(args, *, workdir, env, privileged, check, capture, mounts)` is used with those keywords in Tasks 4, 9, 10. The target protocol (`.host`, `.install_extra`, `.purge`, `.reinstall`, `.reboot`, `.stop`) is defined in Task 8 and implemented for podman (Task 8), VM (Task 10), and SSH (Task 10); tests in Tasks 7, 10, 14 use only those names. `build.build(pkg_dir, version, dist=DIST)` matches its test. `bootconfig` function names match between Task 5's tests and script. `render(templates, name, model, machine_name)` matches between Task 13's tests and script.

**Review Focus coverage.** Item 1 (multi-line `cmdline.txt`): `test_refuses_a_file_with_more_than_one_line` and `test_multiline_cmdline_exits_1_without_writing` in Task 5. Item 2 (same key in another section): `test_leaves_the_same_key_in_other_sections_alone` in Task 5. Item 3 (XML-special and Unicode names): `test_escapes_xml_special_characters_in_the_name` and `test_keeps_unicode_names` in Task 13. Item 4 (no device tree): `test_omits_the_machine_record_when_unknown`, `test_is_none_on_a_missing_file`, and the tier-1 run in Task 14 where containers have no device tree. Item 5 (`MODEL` with `@`, `,`, `=`): `test_encodes_the_model_record_as_base64` and `test_applies_model_from_the_environment_unchanged` in Task 13, and the tier-2 assertion on `model=MacPro7,1@ECOLOR=226,226,224` in Task 14.

## Deviations during execution

- Watchdog drop-in named `50-pihero-watchdog.conf`: Raspberry Pi OS's `40-rpi-enable-watchdog.conf` (`RuntimeWatchdogSec=1m`) sorted after `10-` and won.
- `avahi-render` publishes TXT records as plain text: avahi 0.8 ignores `value-format`, so base64 reached clients undecoded.
- The render unit reloads Avahi with `systemctl --no-block try-reload-or-restart`: the blocking form deadlocked the boot.
- The apt source is a `write_files` deb822 `.sources` entry in [devices/sample/user-data](../../../devices/sample/user-data) and [the all-features device](../../../testkit/src/pihero_testkit/devices/all-features/user-data); the tier-2 drop-in in [prepare-rootfs](../../../testkit/src/pihero_testkit/prepare-rootfs) no longer adds `apt_configure`, which Raspberry Pi OS's `cloud.cfg` does not schedule.
- `rpi:` interface keys are nested under `rpi.interfaces`, where `cc_raspberry_pi` reads them.
- The tier-2 repo is served from `dist/vm/<device>/repo`, so a run only sees its own debs.
- pytest runs with `-p no:pytest11.testinfra`: testinfra's own plugin registers after the testkit's and its `host` fixture shadowed the target's.
- The all-features device requests a reboot with `touch /run/reboot-required` so provisioning exercises `power_state`, and restarts `pihero-avahi-render.service` after setting the pretty hostname.
- Action versions bumped: `actions/checkout@v7`, `astral-sh/setup-uv@v10.2.0`, `docker/setup-qemu-action@v4`, `softprops/action-gh-release@v3`, `actions/cache@v6`.
- `bootconfig unset config KEY VALUE` takes the positional VALUE as the match value; a stray positional on `add` or `remove` is a usage error.
- Cards are written by `make flash DEVICE=<name> DISK=<diskN>` ([flash.py](../../../testkit/src/pihero_testkit/flash.py)): Raspberry Pi Imager's CLI cannot open the device from a terminal, and neither can `dd` as root, because macOS gates raw disk access behind `authopen`; the module uses it the way Imager does and verifies the written image.
- The hardware checkpoint (Task 15) found two Raspberry Pi OS quirks; the device files work around both: `rpi: enable_usb_gadget: true` aborts on a 15 s timeout inside cloud-init and never reboots, so the gadget is enabled from `runcmd` with the reboot flag; macOS 27 binds `g_ether`'s RNDIS configuration and passes no traffic, so `usb-gadget.service` loads `g_cdc` (CDC ECM) instead, after NetworkManager (macOS only asks for DHCP while the link comes up) and with MACs derived from the board serial (macOS creates a network service per MAC).
- `--target=ssh` asserts against the version installed on the device and builds nothing; the git-derived version only matches a device at a tag.
- `make flash` writes the Wi-Fi regulatory domain from `network-config` into `cmdline.txt`, as Imager does: on the checkpoint board a first boot without it never joined the network and cloud-init installed nothing; with it wlan0 connected at 68 s, NetworkManager-wait-online held the final stage until then, and apt installed every package on the first boot.
