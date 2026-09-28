# Testing

Every test is pytest. Machine assertions use pytest-testinfra, whose backends let one test file run against a podman container,
a QEMU VM over SSH, or a real Pi over SSH. Tests pick a target with `--target=podman|vm|ssh` and a tier with the markers
`tier0`, `installed`, `boot`, and `mutating`. The harness is the Python package under [testkit/](../testkit/); apps depend on
it as a pinned git dependency.

## Tiers

| Tier | Target | Budget | Proves |
|---|---|---|---|
| 0 | tools container | seconds | Python helpers against fixtures, shellcheck, `systemd-analyze verify`, `cloud-init schema` for the device files, every package builds |
| 1 | systemd podman container, `linux/arm64` and `linux/arm/v7` | about a minute | install, dependencies resolve on both archives, units enable and start, renderers write the right files, remove and purge leave nothing behind |
| 2 | QEMU `virt` VM with the real Raspberry Pi OS Lite root filesystem | under ten minutes | a device file boots to a provisioned system: cloud-init done without errors, no failed unit, Avahi records, boot config edits that survive a reboot, watchdog armed, the `power_state` reboot |
| ssh | a Raspberry Pi | seconds | the `installed` tests against the packages a real device has; mutating tests are skipped |

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

## Tools container

Linux-side tooling (nfpm, cloud-init, shellcheck, apt-utils, mtools, dosfstools, e2fsprogs, qemu-utils) runs in one image built
from `debian:trixie-slim` pinned by digest, tagged by the hash of its Containerfile, built on first use and rebuilt when the
file changes. It is built for the host architecture on purpose: a cross-architecture pull once left a wrong-arch image under the
same tag, which `podman build` then silently reused. The command comes from the `PODMAN` environment variable, `podman` by
default. Mac-side tooling is QEMU, podman, and uv from the [Brewfile](../Brewfile); `uv.lock` pins pytest and testinfra;
upstream inputs are pinned in `testkit/src/pihero_testkit/images.lock` and cached under `~/.cache/pihero/`. `make doctor`
reports what is missing.

## Tier 1

The base image is `debian:trixie-slim` with `systemd`, `dbus`, `apt-utils`, and `sudo`, one per platform, started with
`podman run --systemd=always … /sbin/init`. The image's `/usr/sbin/policy-rc.d` is removed so package postinsts can start
services. The built packages are mounted and installed with `apt install ./pkg.deb`, and testinfra gets a `podman://<name>`
host. `/boot/firmware/` is a fixture directory with the stock `config.txt` and `cmdline.txt`.

What a container cannot show: `RuntimeWatchdogUSec` is `0` inside podman, so the watchdog is asserted on its drop-in there
and on the manager in tier 2. Avahi records published inside an arm64 container are visible to `avahi-browse` in the same
container, so browse tests work in tier 1. The 32-bit view is CI's job: a 64-bit Arm kernel runs `arm/v7` userland natively,
while on the Mac it needs a `qemu-arm` binfmt handler in the podman machine that Fedora CoreOS does not ship, and even with one
registered, systemd as PID 1 in an `arm/v7` container comes up degraded.

## Tier 2

The harness plays the firmware.

- **Root filesystem, prepared once and cached.** `prepare-rootfs` runs in the tools container, privileged and with `/dev` bind
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
  reboot returns to the harness, serial console logged under `dist/vm/<device>/`.
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

`--target=ssh --target-uri=pi@host[:port]` builds nothing and compares against the version installed on the device, because
the git-derived version only matches a device at a tag. The Avahi tests need `avahi-utils` on the device. `make deploy
TARGET=pi@host` installs freshly built packages over SSH for the development loop.

## CI

Tiers 0 and 1 run on every push on `ubuntu-24.04-arm`, tier 1 for both platforms. Tier 2 needs hardware virtualization, which
GitHub's Arm runners do not offer, so it runs locally as part of `make release` and weekly in CI under software emulation
(about 25 minutes). The weekly job runs as root: the runner's podman is rootless, and even a privileged rootless container gets
no loop device for `prepare-rootfs`, while a rootful container alone leaves the boot image owned by root where QEMU, as the
runner user, cannot open it. The weekly run is the "what rotted" signal. The release workflow builds, signs, and publishes on
every `v*` tag.
