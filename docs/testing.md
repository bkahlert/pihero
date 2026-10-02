# Testing

Every test is pytest. Machine assertions use pytest-testinfra, whose backends let one test file run against a podman container,
a QEMU VM over SSH, or a real Pi over SSH. Tests pick a target with `--target=podman|vm|ssh` and a tier with the markers
`tier0`, `installed`, `boot`, and `mutating`. The harness is the Python package under [testkit/](../testkit); apps depend on
it as a pinned git dependency.

## Tiers

| Tier | Target | Budget | Proves |
|---|---|---|---|
| 0 | tools container | seconds | Python helpers against fixtures, shellcheck, `systemd-analyze verify`, `cloud-init schema` for the device files, every package builds |
| 1 | systemd podman container, `linux/arm64` and `linux/arm/v7` | about a minute | install, dependencies resolve on both archives, units enable and start, renderers write the right files, remove and purge leave nothing behind |
| 2 | QEMU `virt` VM with the real Raspberry Pi OS Lite root filesystem | under ten minutes | a device file boots to a provisioned system: cloud-init done without errors, no failed unit, Avahi records, boot config edits that survive a reboot, watchdog armed, the `power_state` reboot, the kiosk active on a virtual display, a screenshot of it |
| ssh | a Raspberry Pi | seconds | the `installed` tests of the packages the device has; the other packages' tests and mutating tests are skipped |

Tiers 1, 2, and ssh run the same `test_installed.py` files.

```shell
make test-tier0
make test-tier1 PLATFORM=linux/arm/v7          # default linux/arm64
make test-tier2                                # make vm keeps the VM running
make test                                      # tiers 0 and 1
make test-all                                  # tiers 0 to 2, what make release runs
uv run pytest -m installed --target=ssh --target-uri=pi@mypi.local
uv run pytest packages/pihero/tests -m tier0   # one package
```

## Writing tests

The plugin, [plugin.py](../testkit/src/pihero_testkit/plugin.py), provides the markers, fixtures, and options. Markers go in
`pytestmark` at module level: `tier0` runs against fixtures and the tools container with no target; `installed` runs against
any target with the packages installed; `boot` needs a booted system and is skipped on podman; `mutating` changes the
target's state and is skipped over ssh. Fixtures: `host` is the testinfra host; `target` is the container, VM, or ssh target
with `install_extra`, `purge`, `reinstall`, and `reboot`; `version` is what the installed packages must report, the built
version or, over ssh, the one on the device; `packages` are the built `.deb` paths. Options beyond `--target` and
`--target-uri`: `--platform` for podman, `--qemu-accel` for the VM, `--device` for a device directory other than the testkit's
`all-features`, `--display` for the VM's virtual display (`WIDTHxHEIGHT`, default `800x480`, or `none`), and `--keep` to
leave the container or VM running. `VERSION=` overrides the git-derived version. A tier-0 test of a Mac-side command that
needs macOS tools is `skipif` not darwin: it runs locally and under `make release`, and CI's Linux runners skip it.

On-device executables are extensionless Python files; tier-0 tests import them with `pihero_testkit.scripts.load_script` and
call their functions, so a script keeps its logic in functions with injectable dependencies (`environ`, `execvp`, `sleep`,
`now`) rather than at module level. One `test_installed.py` runs on all three targets, which differ: a container has no
`/proc/device-tree/model`, no USB device controller, and no DRM device, so a unit with `ConditionPathExistsGlob=` is skipped
there, not active; assert on the condition, or check the device exists before asserting `is_running`. A `mutating` test
restores what it changed: `target.reinstall()` after a purge, the previous conffile after an override.

## Tools container

Linux-side tooling (nfpm, cloud-init, shellcheck, apt-utils, mtools, dosfstools, e2fsprogs, qemu-utils) runs in one image built
from `debian:trixie-slim` pinned by digest, tagged by the hash of its Containerfile, built on first use and rebuilt when the
file changes. It is built for the host architecture on purpose: a cross-architecture pull once left a wrong-arch image under the
same tag, which `podman build` then silently reused. The command comes from the `PODMAN` environment variable, `podman` by
default. Mac-side tooling is QEMU, podman, and uv from the [Brewfile](../Brewfile); [uv.lock](../uv.lock) pins pytest and
testinfra; upstream inputs are pinned in [images.lock](../testkit/src/pihero_testkit/images.lock) and cached under
`~/.cache/pihero/`. `make doctor` reports what is missing.

A package directory with a `build` script next to a `Containerfile` builds itself: `make build` builds that image for
`linux/arm64` whatever the host is, runs the script with the repository mounted at `/work`, and takes the `.deb` paths it
prints. [packages/cog](../packages/cog) is the one such package; its image carries cog's build dependencies, which would
double the tools image, and is the slow part, cached by the Containerfile's digest. The package itself builds in seconds.
While a `.deb` of the package exists in `dist/`, the testkit returns it without building even the image, so `make clean`
is what rebuilds it; CI caches that `.deb` keyed on `packages/cog/`.

## Tier 1

The base image is `debian:trixie-slim` with `systemd`, `dbus`, `apt-utils`, and `sudo`, plus the Raspberry Pi archive as an apt
source, because `pihero-usb-gadget` depends on `rpi-usb-gadget`, which only that archive carries. The archive key committed next
to the Containerfile is the one from `raspberrypi-archive-keyring` 2025.1, re-signed with SHA512; the export at
`raspberrypi.gpg.key` still carries only SHA1 self-signatures, which Trixie's apt rejects since 2026-02-01. One image per
platform, tagged with a digest of its build context so a changed Containerfile is rebuilt on first use, started with
`podman run --systemd=always … /sbin/init`. The image's `/usr/sbin/policy-rc.d` is removed so package postinsts can start
services. The built packages are mounted, and those marked `all` or built for the container's architecture are installed with
`apt install ./pkg.deb`; the arm64 `cog` stays out of the armhf container, which takes Debian's through `pihero-kiosk`. testinfra gets a `podman://<name>`
host. `/boot/firmware/` is a fixture directory with the stock `config.txt` and `cmdline.txt`.

What a container cannot show: `RuntimeWatchdogUSec` is `0` inside podman, so the watchdog, left at Raspberry Pi OS's minute,
is asserted on the manager in tier 2 only. Avahi records published inside an arm64 container are visible to `avahi-browse` in the same
container, so browse tests work in tier 1. The 32-bit view is CI's job: a 64-bit Arm kernel runs `arm/v7` userland natively,
while on the Mac it needs a `qemu-arm` binfmt handler in the podman machine that Fedora CoreOS does not ship, and even with one
registered, systemd as PID 1 in an `arm/v7` container comes up degraded. The container has no USB device controller, so
`pihero-usb-gadget.service` is skipped by its condition there and in the VM; the gadget itself is proven on a Pi over ssh.

## Tier 2

The harness plays the firmware.

- **Root filesystem, prepared once and cached** (`make vm-prepare` does it ahead of the first run, about ten minutes).
  `prepare-rootfs` runs in the tools container, privileged and with `/dev` bind
  mounted (podman populates `/dev` once at start, so without the mount `losetup --partscan` never sees the partition nodes it
  creates). It extracts the root partition of the pinned Raspberry Pi OS Lite arm64 image, chroots in, installs Debian's
  `linux-image-arm64` (the Raspberry Pi kernel hooks skip it harmlessly), sets `MODULES=most` for the initramfs (the image's
  `MODULES=dep` leaves out `virtio_blk` and the boot drops to an initramfs shell), masks `rpi-eeprom-update.service` (a shell
  arithmetic error without EEPROM hardware, the only failed unit otherwise), drops `netplan_nm_patch` from `cloud.cfg` (see
  [raspberry-pi-os.md](raspberry-pi-os.md)), rewrites `/etc/fstab` to labels, packs the tree with `mkfs.ext4 -d`, and copies
  out the kernel and initrd. The cache key is the image checksum plus the kernel package.
- **Boot partition, per run.** A FAT image labelled `bootfs` with the stock `config.txt` and `cmdline.txt` and the device's
  `user-data`, `network-config`, `meta-data`, attached as a second virtio disk. The guest mounts it at `/boot/firmware` by
  label, so cloud-init and Raspberry Pi tooling see the real paths; `config.txt` has no effect in the VM and is asserted as file
  content.
- **Kernel command line.** On every boot the harness reads `cmdline.txt` from the bootfs image and passes it with `-append`,
  replacing `root=` and `console=` with the label and `ttyAMA0` and dropping `resize` (its initramfs script expects a
  partition). Everything else passes verbatim, so a test can edit a parameter, reboot, and assert `/proc/cmdline`.
- **Disk and QEMU.** A copy-on-write overlay per run over the pristine base; `qemu-system-aarch64 -M virt` with HVF on the Mac
  (`--qemu-accel=tcg` elsewhere), 1 GiB, two cores, user-mode networking with a port forward for SSH, `-no-reboot` so a guest
  reboot returns to the harness, serial console logged under `dist/vm/<device>/`, a `virtio-gpu-pci` display at the
  configured size whose EDID makes the guest's connector `Virtual-1` prefer it, and a QMP monitor on a localhost TCP port
  through which `Vm.screenshot(path)` saves a PNG of the display (`VM_DISPLAY=none` for the headless VM).
- **Repository.** The run builds every package, generates a flat unsigned repository under `dist/vm/<device>/repo`, serves it
  from the Mac, and the all-features device file points its apt source at the QEMU host address with `Trusted: yes`.
- **Lifecycle.** Boot, wait for SSH (7 s under HVF), `cloud-init status --wait`, follow the `power_state` reboot, run the tests,
  tear down. On failure the serial log and the overlay stay for a look; `make vm` boots the VM and keeps it.
- **Device file.** `testkit/src/pihero_testkit/devices/all-features/user-data` installs every package, requests a reboot so
  provisioning exercises `power_state`, and sets `rpi: interfaces:` only: `rpi-usb-gadget` refuses to run on a machine whose
  device tree is not a Raspberry Pi.

The SSH client passes `-o IdentitiesOnly=yes` with the harness key: an agent holding several keys otherwise exhausts sshd's
attempts before the right key is offered, which looks like a boot failure. pytest runs with `-p no:pytest11.testinfra`:
testinfra's own plugin registers after the testkit's, and its local-host `host` fixture would shadow the target's.

## Real devices

`--target=ssh --target-uri=pi@host[:port]` builds nothing. It compares against the version installed on the device, because
the git-derived version only matches a device at a tag, and asks the device which packages it has, as `make deploy` does:
the installed tests of the others are skipped as "not installed on pi@host". The Avahi tests need `avahi-utils` on the device.

Neither tier is a Raspberry Pi, so a release is proven on two real boards, the checkpoints, one per image. A 64-bit Zero 2 W
on Wi-Fi with `pihero-usb-gadget` is the gadget's board: only a fresh card there shows its postinst turning `rpi-usb-gadget`
on and requesting the reboot, purge turning it off, and a Mac on the cable getting an address. A 32-bit Zero, the hardware
floor, on a USB Ethernet hub covers ARMv6 timing and NetworkManager over a cable; it never takes the gadget, because
peripheral mode claims the Zero's one USB controller and leaves a board on a hub dark. Neither has a display, so the kiosk
is proven in tier 2 and on application boards. The checkpoints are disposable: their device directories live outside this
checkout, a release reflashes both, and nothing is kept on them.

A gitignored `.env` at the repository root, which `make` reads, names the directories and the boards:

    PIHERO_DEVICES=~/fleet/devices       # the directory holding the device directories
    CHECKPOINTS=checkpoint checkpoint32  # their names under it, which are their hostnames; one per image

`make flash DEVICE=<name>` finds a device directory there as well as under `devices/`, and `make checkpoint` runs the ssh tier
against every board in `CHECKPOINTS` as `pi@<name>.local`, prints one verdict per board with ssh's error for an unreachable
one, and exits non-zero when one failed or was unreachable. Its login probe accepts a board's new host key, so a reflashed
board needs only the `ssh-keygen -R` that forgets the old one.
`make deploy TARGET=pi@host` reinstalls the freshly built packages the device already has over SSH for the development loop;
it adds none.

## CI

Tiers 0 and 1 run on every push on GitHub's Arm runners ([ci.yml](../.github/workflows/ci.yml)), tier 1 for both
platforms. Tier 2 needs hardware virtualization, which GitHub's Arm runners do not offer, so it runs locally as part of
`make release` and weekly in CI under software emulation (about 25 minutes). The weekly job runs as root: the runner's
podman is rootless, and even a privileged rootless container gets no loop device for `prepare-rootfs`, while a rootful
container alone leaves the boot image owned by root where QEMU, as the runner user, cannot open it. The weekly run is
the "what rotted" signal. The release workflow builds, signs, and publishes on every `v*` tag.

`main` takes changes only through pull requests with tiers 0 and 1 green and can neither be force-pushed nor deleted; `v*` tags
cannot be moved or deleted. Workflows run with a read-only token, only the release job may write, and it alone sees the signing
key. Actions are pinned to commits and the repository refuses unpinned ones; Dependabot proposes the monthly bump. Workflows
from external forks wait for approval before they run.

## Release

```shell
make release VERSION=2.1.0        # clean tree required; runs tiers 0 to 2, then tags v2.1.0
git push origin v2.1.0            # the release workflow builds, signs, and publishes
curl -fsS https://bkahlert.github.io/pihero/apt/Packages | grep -A1 '^Package: pihero'
make flash DEVICE=checkpoint DISK=disk9      # then the hardware step: reflash both checkpoints, one card at a time
make flash DEVICE=checkpoint32 DISK=disk9
ssh-keygen -R checkpoint.local; ssh-keygen -R checkpoint32.local   # reflashed boards have new host keys
make checkpoint                   # the ssh tier on both, once they have booted (about 6 min for the Zero 2 W, 16 for the Zero)
```

The hardware step comes after publishing because a fresh card installs from the repository, so the checkpoints prove the
release as devices receive it. Their device directories are rendered as the repository holding them describes; the boards,
their images, and `.env` are in "Real devices" above.

Tags with a pre-release suffix such as `v2.1.0-rc.1` publish as `2.1.0~rc.1` and are marked pre-release on GitHub. The
signing key is the `APT_SIGNING_KEY` secret of the `release` environment, which only `v*` tags can deploy to. The key itself
is kept in KeePassXC as the attachment of the `PIHERO_APT_SIGNING_KEY` entry. `make repo` builds and signs the same
repository locally and reads the key from `~/.config/pihero-apt-signing-key.asc`, so export it there for the run and remove
it afterwards:

```shell
keepassxc-cli attachment-export <vault>.kdbx PIHERO_APT_SIGNING_KEY pihero-apt-signing-key.asc ~/.config/pihero-apt-signing-key.asc
make repo
rm -P ~/.config/pihero-apt-signing-key.asc
```
