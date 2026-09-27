# Pi Hero 2: Debian packages, cloud-init, and a test harness

Design spec, 2026-09-27. Status: approved in conversation, awaiting written review.

## 1. Purpose

Pi Hero makes a Raspberry Pi discoverable, reachable, and pleasant to use. Version 1 is an
Ansible playbook (tagged `pihero-ansible`). It works, but every change is verified by hand on
real hardware, and after a year away the toolchain has drifted enough that nothing can be trusted
until it is re-tested manually.

Version 2 keeps the functionality and replaces the implementation with three things:

1. **Debian packages** as the unit of a feature. One feature is one `.deb`, installed and removed
   like any other package, updated with `apt upgrade`.
2. **cloud-init** as the way a device is described. One file on the boot partition replaces the
   Ansible inventory entry and provisions a freshly flashed card without a control machine.
3. **An automated test harness** that proves each feature on the Mac, in seconds to minutes,
   without a Raspberry Pi attached, and that the same assertions can later run against real
   hardware.

Success looks like this: `make test` is green after a year of neglect, or tells you exactly what
rotted. A new device is flashed, gets its device file copied onto the card, boots, and appears in
Finder with its icon. Adding a feature means adding one directory under `packages/`.

## 2. Requirements and constraints

Stated by the owner:

- Tests are the top priority. Automated, per feature, fast turnaround on the Mac. Manual testing
  is what version 2 exists to end.
- Keep the functionality of version 1. The implementation is free to change completely.
- Migrate one feature at a time.
- Hardware floor for applications is the Raspberry Pi Zero W (ARMv6, 512 MB). Zero 2 W is
  acceptable but Zero W is preferred.
- Emulation only for now. A hardware tier must be possible later without redesign.
- Simple, well tailored, clean separation. Prefer upstream solutions over own code. Prefer modern
  drivers and mechanisms. Problems that fall out of that are solved later, by the apps if they are
  app problems.
- The interactive bash CLI and `gum` go. `gum` is slow on old boards and the CLI's diagnostics
  are replaced by the tests.

Derived constraints:

- Containers are not the application plane. The Zero W has almost no `arm/v6` image ecosystem,
  and SPI, GPIO, and framebuffer access from a container on 512 MB is fighting the platform.
  Apps are systemd services delivered as packages.
- Every `pihero-*` package is `Architecture: all` and depends only on packages that exist on
  both the 64-bit and the 32-bit Raspberry Pi OS archives, so the design contains no per-model
  branch.
- Target OS is Raspberry Pi OS Lite on Debian 13 (Trixie). The 32-bit Trixie image supports all
  boards including the Zero W; the 64-bit image supports Zero 2 W and up. cloud-init ships in
  both since November 2025.

## 3. Decisions

| Decision | Choice | Why |
|---|---|---|
| Delivery model | Debian packages, flat apt repo, cloud-init bootstrap | Idiomatic on a Debian-based OS; hard feature boundaries; testable at build, install, and boot; updates are `apt upgrade`; no control machine |
| USB Ethernet | Upstream `rpi-usb-gadget`, enabled with `rpi: enable_usb_gadget: true` | Maintained by Raspberry Pi, handles macOS and Windows drivers and internet-sharing detection; per-device subnet is one `nmcli` override |
| USB serial console | Dropped in favour of the GPIO UART (`rpi: serial: true`) | `rpi-usb-gadget` uses the monolithic `g_ether`, which cannot carry an ACM function; a broken gadget breaks its serial port too, so it never was an independent path |
| Custom gadget functions (mass storage) | Deferred, package `pihero-usb-gadget-composite` only if an app needs it | Mutually exclusive with `rpi-usb-gadget` on one board; nobody depends on it today |
| On-device logic language | Python 3 standard library for anything that parses or edits files; shell only in `ExecStart=` lines and maintainer scripts | Editing boot config idempotently is where bash bites; cloud-init guarantees Python on every Trixie image |
| Package build tool | `nfpm` | One YAML manifest plus a file tree, builds in under a second, no Debian toolchain |
| Test framework | pytest with pytest-testinfra | One assertion API over podman, SSH to a VM, and SSH to a real Pi |
| Interactive CLI, `gum`, hero animation on device | Dropped | Slow on old boards; tests replace the diagnostics; the hero art survives as a static MOTD banner |
| Core package name | `pihero` | The idiomatic core-plus-suffix scheme, as in `tailscale` or `git` |
| `set-chassis embedded` | Dropped | Nothing on a headless Pi consumes it |
| Device files sharing content | Standalone files, duplication accepted | Simpler than a merge step; revisit if it hurts |

## 4. Architecture

Three layers, each owned by a different party and updated independently.

```
┌───────────────────────────────────────────────────────────┐
│ Apps            pihole-chronometer, epaper-display, netmon  │  app repos, own packages, own tests
├───────────────────────────────────────────────────────────┤
│ Pi Hero         pihero, pihero-avahi, pihero-smb,           │  this repo, packages/*
│                 pihero-splash, pihero-display-hdmi,         │
│                 pihero-bt-pan                               │
├───────────────────────────────────────────────────────────┤
│ Raspberry Pi OS Lite (Trixie) + cloud-init + rpi-usb-gadget │  flashed with Imager
│                 + NetworkManager + avahi-daemon + raspi-config│
└───────────────────────────────────────────────────────────┘
        ▲ described by one file: devices/<host>/user-data on the boot partition
```

Never-lose-contact is served by three independent paths:

- **Physical**: USB Ethernet via `rpi-usb-gadget`, the GPIO UART, and Bluetooth PAN via
  `pihero-bt-pan`.
- **Remote**: Tailscale, installed from its upstream repo through the device file. No Pi Hero
  code involved.
- **Self-healing**: the hardware watchdog armed by `pihero`, and the documented app-unit
  conventions (`Restart=`, `MemoryMax=`) so a misbehaving app cannot starve sshd. Base units
  never depend on app units.

## 5. Feature mapping from version 1

Legend. **Covered**: upstream does it now, Pi Hero code disappears. **Package**: becomes a
`pihero-*` package. **Config**: becomes lines in the device file. **Tests**: the logic moves into
the harness. **Dropped**: gone.

| Version 1 | Version 2 | Notes |
|---|---|---|
| Ansible playbook, inventory per host | Config: one `user-data` per device | Feature dict becomes `packages:` plus a few `write_files` |
| `patch --continuous` dev loop | `make deploy TARGET=host` | Builds the package, installs over SSH, same path the tests use |
| `scripts/*_connection_share.*` | Covered by `rpi-usb-gadget` ICS watcher | Auto-detects host internet sharing and switches client/shared mode |
| apt-update pre-task, `AllowReleaseInfoChange` | Covered by apt | Obsolete on a current image |
| `group_members` fact, user groups | Covered by cloud-init `users:` | Groups like `gpio`, `spi`, `lp` declared there |
| `bkahlert.gum` role | Dropped | Only the TUI needed it; slow on old boards |
| CLI menu, animation, cache, extensions | Dropped | |
| CLI `diag` checks | Tests, plus systemd | Each check becomes an assertion; units carry `Condition*` and `ExecStartPre` so failures show in `systemctl --failed` |
| Shared bash lib copied into netmon | Dropped here | netmon vendors its copy until it is refactored |
| MOTD blocks | Package `pihero`, one `/etc/update-motd.d/` script | Installed features, failed units, reboot pending, usb0 address, static hero banner |
| `kernel_parameters` module, `config.txt` ini edits | Package `pihero`: `pihero-bootconfig` | Only where cloud-init `rpi:` or `raspi-config nonint` has no option |
| device_info: install avahi | Covered | Raspberry Pi OS ships `avahi-daemon` |
| device_info: pretty hostname, `_device-info._tcp`, `_ssh._tcp`, `_sftp-ssh._tcp` | Package `pihero-avahi` | Rendered at boot; `machine=` read from the device tree, `model=` from config |
| smb_shares | Package `pihero-smb` | Password stays a documented `smbpasswd -a` step |
| splash: theme | Package `pihero-splash` | Theme files plus `plymouth-set-default-theme -R` |
| splash: silent boot parameters | Package `pihero-splash` via `pihero-bootconfig` | All parameters set by the package; `raspi-config` is unusable on Lite for this |
| hdmi role | Package `pihero-display-hdmi`, after a KMS spike | Trixie runs full KMS where `hdmi_group/mode/cvt` are ignored; custom modes are `video=` kernel parameters |
| usb_gadget: dwc2, Ethernet, DHCP, NAT, host compat | Covered by `rpi-usb-gadget` | Enabled in the device file; per-device subnet via `nmcli` |
| usb_gadget: serial over USB | Dropped; GPIO UART instead | See decisions |
| usb_gadget: custom functions | Deferred | See decisions |
| bt_pan | Package `pihero-bt-pan` | `bluez-tools` for NAP and agent; `pan0` becomes a NetworkManager bridge with shared IPv4, replacing ifupdown and dnsmasq |
| Tailscale (TODO) | Config | Upstream apt source and package, `tailscale up` in `runcmd` |
| Not present: watchdog, app limits | Package `pihero` and docs | `RuntimeWatchdogSec=15` drop-in; unit conventions documented |

## 6. Repository layout and package anatomy

One directory per package, mirroring the target filesystem. Everything a feature installs sits
under `root/` exactly where it lands on the Pi. Tests live next to the feature.

```
pihero/
  packages/
    pihero/
      nfpm.yaml
      root/usr/lib/pihero/bootconfig                          # Python, boot-config editor
      root/usr/lib/pihero/motd                                # Python, MOTD generator
      root/etc/update-motd.d/50-pihero                        # sh, calls motd
      root/etc/systemd/system.conf.d/50-pihero-watchdog.conf  # sorts after rpt's 40-rpi-enable-watchdog.conf
      scripts/postinst  scripts/prerm  scripts/postrm
      tests/
    pihero-avahi/
      nfpm.yaml
      root/usr/lib/pihero/avahi-render                        # Python
      root/usr/lib/systemd/system/pihero-avahi-render.service
      root/usr/share/pihero/avahi/device-info.service.in
      root/usr/share/pihero/avahi/ssh.service.in
      scripts/  tests/
    pihero-smb/
    pihero-splash/
    pihero-display-hdmi/
    pihero-bt-pan/
  testkit/                  # shared harness, a Python package (see section 10)
  devices/                  # gitignored except devices/sample/; all-features lives in testkit/src/pihero_testkit/devices/
  docs/
    app-conventions.md      # unit template for apps: Restart=, MemoryMax=, user, groups
  assets/                   # logo, banner, hero script (build-time only)
  Makefile
  Brewfile                  # qemu, podman, uv
  .github/workflows/ci.yml
```

Conventions:

- **Names**: `pihero` core, `pihero-<feature>` for everything else. Units are
  `pihero-<feature>*.service`. Rendered files carry the `pihero-` prefix.
- **Paths**: executables in `/usr/lib/pihero/`, data and templates in
  `/usr/share/pihero/<feature>/`, units in `/usr/lib/systemd/system/`, device overrides in
  `/etc/pihero/<feature>.conf` (never shipped by a package), state in `/var/lib/pihero/`.
- **Manifest**: `nfpm.yaml` declares `Architecture: all`, `Depends`, `Section: admin`, contents
  as `type: tree` from `root/`, and the maintainer scripts.
- **Version**: all packages share one SemVer version taken from the git tag. Version 2 starts
  at `2.0.0`.
- **Maintainer scripts**: minimal POSIX shell generated from one shared template that calls
  `deb-systemd-helper` and `deb-systemd-invoke`, which is what debhelper emits. Feature-specific
  lines are appended per package.
- **Languages**: Python 3 standard library for helpers, tested with pytest. Shell only in
  `ExecStart=` and maintainer scripts, checked with shellcheck.

## 7. The `pihero` core package

Every other `pihero-*` package depends on it.

### 7.1 `pihero-bootconfig`

Idempotent editor for `/boot/firmware/config.txt` and `/boot/firmware/cmdline.txt`.

```
pihero-bootconfig set    config  <key> <value> [--section all]
pihero-bootconfig unset  config  <key>         [--section all]
pihero-bootconfig add    cmdline <param>[=<value>]
pihero-bootconfig remove cmdline <param>
```

- Changes exactly the addressed key and leaves the rest of the file byte-identical. Exits 0 in
  both the changed and the unchanged case; prints which.
- `config.txt` sections (`[all]`, `[pi0]`, ...) are respected; default section is `[all]`. Keys
  that may repeat (`dtoverlay`) are matched on the full `key=value`.
- `cmdline.txt` stays a single line. A parameter is matched on its name, so `add loglevel=3`
  replaces an existing `loglevel=7`.
- On change it touches `/run/reboot-required` and appends the calling package name, passed with
  `--package`, to `/run/reboot-required.pkgs`. It never reboots.
- File locations are overridable through `PIHERO_BOOTFS` for tests.
- Rule of use: only when cloud-init `rpi:` or `raspi-config nonint` offers no option.

### 7.2 MOTD

`/etc/update-motd.d/50-pihero` runs `/usr/lib/pihero/motd`, which prints the static hero banner
rendered once at build time from [assets/hero](../../../assets/hero) with
`--mood neutral --no-color`, then: installed `pihero-*` packages and their versions, failed
units, whether a reboot is pending and for which packages, and the address of `usb0` if it
exists. No colors, no animation, no dependencies beyond Python.

### 7.3 Watchdog

`/etc/systemd/system.conf.d/50-pihero-watchdog.conf`, named to sort after Raspberry Pi OS's
`40-rpi-enable-watchdog.conf` (`RuntimeWatchdogSec=1m`), which otherwise wins:

```
[Manager]
RuntimeWatchdogSec=15
```

systemd opens `/dev/watchdog` and pings it every 7.5 s. If the kernel or systemd hangs, the
BCM2835 watchdog resets the board. Fifteen seconds is the hardware maximum. No configuration.
postinst runs `systemctl daemon-reexec` so the watchdog arms immediately; purge removes the
drop-in and reexecs again.

## 8. Feature packages

Each package follows the same pattern: files under `root/`, an optional render unit ordered
before its consumer, defaults in code, overrides from `/etc/pihero/<feature>.conf` via
`EnvironmentFile=-`, and tests in `tests/`.

### 8.1 `pihero-avahi`

- Depends: `pihero`, `avahi-daemon`.
- `pihero-avahi-render.service`: `Type=oneshot`, `RemainAfterExit=yes`,
  `Before=avahi-daemon.service`, `EnvironmentFile=-/etc/pihero/device-info.conf`,
  `WantedBy=multi-user.target`.
- `avahi-render` writes `/etc/avahi/services/pihero-device-info.service` and
  `/etc/avahi/services/pihero-ssh.service` from the templates.
  - Service name: pretty hostname from `hostnamectl --pretty`, falling back to the hostname.
  - `_device-info._tcp` TXT records: `model=` from `MODEL` (default `AirPort4`), `machine=` from
    `/proc/device-tree/model` with the trailing NUL stripped. Both as plain text; avahi 0.8
    ignores `value-format`, so a base64 value would reach clients undecoded.
  - `_ssh._tcp` and `_sftp-ssh._tcp` on port 22.
- Config keys: `MODEL`.
- `/etc/avahi/avahi-daemon.conf` is left untouched. It is a dpkg conffile of `avahi-daemon`, and
  Debian's defaults already match what version 1 set (`publish-workstation=no`,
  `disallow-other-stacks=no`). Version 1's `publish-hinfo=yes` is dropped as cosmetic.
- Purge removes the rendered files.
- Tests: tier 0 renders with environment variables and a fake device-tree file and compares the
  XML. Tiers 1, 2, 4 assert the files, the unit, and `avahi-browse -rpt _device-info._tcp`
  inside the target shows the records.

### 8.2 `pihero-smb`

- Depends: `pihero`, `samba`.
- `pihero-smb-render.service`, `Before=smbd.service`: backs up the existing
  `/etc/samba/smb.conf` to `/var/lib/pihero/smb.conf.orig` on first run, then writes
  `/etc/samba/smb.conf` from the template: each user's home read-write, `rootfs` (`/`)
  read-only, as in version 1. Writes `/etc/avahi/services/pihero-smb.service`.
- Debian's `smb.conf` is not a dpkg conffile (it is managed by ucf), so overwriting it does not
  cause a dpkg prompt. Purge restores the backup.
- Config keys: none in 2.0.
- Password: `sudo smbpasswd -a $USER`, documented. Not automated because cloud-init has no
  prompt and a plaintext password does not belong on the FAT partition.
- Tests: tier 0 renders the template. Tiers 1, 2, 4 assert the files and that `smbclient -L
  localhost -N` lists the shares. Tier 2 additionally sets a test password and mounts the share
  from inside the VM.

### 8.3 `pihero-splash`

- Depends: `pihero`, `plymouth`, `plymouth-themes`.
- Ships the theme under `/usr/share/plymouth/themes/pihero/`.
- postinst: `pihero-bootconfig` adds `quiet`, `splash`, `plymouth.ignore-serial-consoles`,
  `logo.nologo`, `loglevel=3`, `udev.log_level=3`, `rd.udev.log_level=3`,
  `systemd.show_status=auto`, `vt.global_cursor_default=0`, `consoleblank=0` to `cmdline.txt`
  and `disable_splash=1` to `config.txt`; then `plymouth-set-default-theme -R pihero`.
  `raspi-config nonint do_boot_splash` is deliberately not used: it refuses to run unless the
  desktop's `pix` theme is installed, which Lite lacks.
- Purge reverts every parameter it added and resets the theme.
- Config keys: none in 2.0. Not installing the package is how you disable the splash.
- Tests: tier 1 asserts the theme is the default and the boot files contain the parameters, then
  removes the package and asserts they are gone. Tier 2 reboots and asserts `/proc/cmdline`.

### 8.4 `pihero-display-hdmi`

- Depends: `pihero`.
- Contract: `VIDEO` in `/etc/pihero/display-hdmi.conf`, for example
  `HDMI-A-1:800x480M@60`, becomes `video=<VIDEO>` on the kernel command line, applied by a
  render unit through `pihero-bootconfig`.
- The exact set of supported keys is fixed after the KMS spike (section 12). Version 1's
  `hdmi_group/mode/cvt`, `disable_overscan`, and the fkms switch are not carried over.
- Tests: tier 0 for the parameter mapping, tiers 1 and 2 for the file contents.

### 8.5 `pihero-bt-pan`

- Depends: `pihero`, `bluez`, `bluez-tools`, `network-manager`.
- `pihero-bt-pan-render.service`, `Before=bluetooth.service`: applies `CLASS` and
  `DISCOVERABLE_TIMEOUT` to `/etc/bluetooth/main.conf` idempotently, writes
  `/etc/bluetooth/pihero-pins` from `/etc/pihero/bt-pan.devices`, and ensures a NetworkManager
  bridge connection `pan0` with `ipv4.method shared` and `ipv4.addresses <CIDR>`. NetworkManager
  provides DHCP and NAT; no dnsmasq unit, no `/etc/network/interfaces.d/`.
- `pihero-bt-network.service`, `After=bluetooth.service`: `ExecStartPre=/usr/lib/pihero/bt-trust`
  marks every listed device trusted through `bluetoothctl`, which needs bluetoothd running and
  therefore cannot live in the render step; then `bt-network --server nap pan0`.
- `pihero-bt-agent.service`: `bt-agent -c NoInputNoOutput -p /etc/bluetooth/pihero-pins`.
- Config: `/etc/pihero/bt-pan.conf` with `CIDR` (default `10.11.10.10/29`), `CLASS` (default
  `0x0108`), `DISCOVERABLE_TIMEOUT` (default `0`). `/etc/pihero/bt-pan.devices` in `bt-agent`
  pins format, one `MAC PIN` per line, `*` for any PIN. Listed devices are trusted.
- Tests: tier 0 for the renderers. Tier 2 loads `hci_vhci`, starts `btvirt`, and asserts
  bluetoothd sees an adapter, the NAP server is registered, and `pan0` has its address. Data
  path is tier 4.

## 9. Configuration contract

### 9.1 The device file

`devices/<host>/user-data` is a cloud-init file written in the repo and copied onto the boot
partition after flashing. It is the complete description of the device. A one-line comment
header names the board and the image to flash. Real device files are gitignored or kept in a
private repo; `devices/sample/user-data` is committed as the reference.

```yaml
#cloud-config
# board: Raspberry Pi Zero W  image: Raspberry Pi OS Lite 32-bit (Trixie)
hostname: pihole
users:
  - name: bkahlert
    groups: [sudo, spi, gpio]
    ssh_authorized_keys: [ssh-ed25519 AAAA...]
    sudo: ALL=(ALL) NOPASSWD:ALL
ssh_pwauth: false
rpi:
  enable_usb_gadget: true
  interfaces:
    spi: true
packages: [pihero-avahi, pihero-smb, pihero-splash, pihole-chronometer, epaper-display]
write_files:
  - path: /etc/apt/sources.list.d/pihero.sources
    content: |
      Types: deb
      URIs: https://bkahlert.github.io/pihero/apt
      Suites: ./
      Signed-By:
       -----BEGIN PGP PUBLIC KEY BLOCK-----
       ...
  - path: /etc/pihero/device-info.conf
    content: MODEL=MacPro7,1@ECOLOR=226,226,224
runcmd:
  - hostnamectl set-hostname --pretty "(ノಠ益ಠ)ノ彡 ⬬"
  - nmcli connection modify "USB Gadget (shared)" ipv4.addresses 10.10.10.60/29
power_state:
  mode: reboot
  condition: test -f /run/reboot-required
```

The apt source is a `write_files` entry, not cloud-init's `apt:` block: Raspberry Pi OS's
`cloud.cfg` does not schedule `apt_configure`, so an `apt:` block is silently ignored there.

Wi-Fi goes into `network-config` next to it, as Imager writes it.

### 9.2 Defaults and overrides never share a file

Packages ship nothing under `/etc/pihero/`. Defaults live in the script or unit. A device writes
`/etc/pihero/<feature>.conf` through `write_files`; the unit reads it with
`EnvironmentFile=-/etc/pihero/<feature>.conf`. Format is `KEY=VALUE`, parsed by systemd, so no
config library on the device. This also avoids dpkg's conffile prompt, which would otherwise
fire because cloud-init writes files before it installs packages.

### 9.3 Render at boot

Where a value must end up inside a file another daemon reads, the package has a oneshot render
unit ordered `Before=` the consumer. It runs every boot and is idempotent. Editing a conffile and
rebooting is therefore a complete change procedure, and every renderer is a pure function the
tests call with environment variables.

### 9.4 Identity

Hostname from cloud-init. Pretty hostname via one `runcmd` line; the Avahi renderer reads it from
`hostnamectl` so `/etc/machine-info` stays the single source. Board model from the device tree
at boot. USB subnet via one `nmcli` line against the profile `rpi-usb-gadget` installs.

### 9.5 Secrets

The boot partition is unencrypted FAT. SSH public keys and password hashes are fine there. A
Wi-Fi PSK or a Tailscale auth key is exposed to anyone holding the card. Accepted for hobby
devices under physical control; Tailscale keys should be single-use with an expiry.

### 9.6 Day two

cloud-init runs once per card. Changes are `apt upgrade`, a conffile edit plus reboot, or a
reflash. There is no re-provisioning step.

### 9.7 Validation

`cloud-init schema --config-file` runs against every committed device file in tier 0.

## 10. Test harness

### 10.1 Principles

- All tests are pytest. Machine assertions use pytest-testinfra, whose backends make one test
  file run against a podman container, a VM over SSH, or a real Pi over SSH.
- Tests select a target with `--target=podman|vm|ssh` and a tier with markers `tier0`,
  `installed`, `boot` and `mutating`.
- Static checks: shellcheck for shell, `systemd-analyze verify` for units, `cloud-init schema`
  for device files, and building all packages.

### 10.2 Tiers

| Tier | Target | Budget | Proves |
|---|---|---|---|
| 0 unit | tools container | under 30 s | Python helpers against fixtures, static checks, packages build |
| 1 package | systemd-enabled podman container, `linux/arm64` and `linux/arm/v7` | under 2 min | install, dependencies resolve on both archives, units enable and start, renderers write the right files, remove leaves nothing behind |
| 2 system | QEMU `virt` VM with the real Raspberry Pi OS Lite root filesystem | under 10 min for the suite | a device file boots to a provisioned system: cloud-init done without errors, no failed units, Avahi records, boot config, watchdog armed, Samba reachable, reboot flow |
| 3 fidelity, later | QEMU `raspi0` and `raspi3b`, stock image and kernel, software emulation | tens of minutes | real kernel, real 32-bit ARMv6 userland |
| 4 hardware, later | a Pi over SSH, manually triggered | minutes | dwc2, displays, Bluetooth data path |

Tiers 1, 2, and 4 run the same `test_installed.py` files.

### 10.3 Tier 1 mechanics

A base image built from `debian:trixie-slim` with `systemd`, `apt-utils`, and `dbus`, one per
platform. The harness starts it with `podman run --systemd=always ... /sbin/init`, mounts the
built packages, installs them with `apt install ./pkg.deb`, and hands testinfra a
`podman://<name>` host. `/boot/firmware/` is a fixture directory with a stock `config.txt` and
`cmdline.txt`.

### 10.4 Tier 2 mechanics

The harness plays the firmware.

- **Root filesystem, prepared once, cached.** Extract the root partition of the pinned
  Raspberry Pi OS Lite arm64 image, chroot into it inside the tools container run privileged
  (arm64 native, so no CPU emulation), install `linux-image-arm64`, rewrite `/etc/fstab` to
  `LABEL=rootfs` and `LABEL=bootfs`, pack with `mkfs.ext4 -d`, and copy out `vmlinuz` and
  `initrd.img`. Cache key: image sha256 plus kernel version, recorded in `testkit/images.lock`.
- **Boot partition, per run.** A FAT image labelled `bootfs` built with `mkfs.vfat` and `mcopy`,
  containing the stock `config.txt` and `cmdline.txt` and the device's `user-data`,
  `network-config`, `meta-data`. Attached as a virtio disk; the guest mounts it at
  `/boot/firmware`, so cloud-init and Raspberry Pi tooling see the real paths.
- **Kernel command line.** On every boot the harness reads `cmdline.txt` from the bootfs image
  and passes it with `-append`, substituting `root=` with the rootfs label and `console=` with
  `ttyAMA0`. Everything else passes verbatim, so tests can edit boot parameters, reboot, and
  assert `/proc/cmdline`. `config.txt` has no effect in the VM and is asserted as file content.
- **Disk.** A copy-on-write overlay per run over the cached base; the base stays pristine.
- **QEMU.** `qemu-system-aarch64 -M virt -accel hvf -cpu host -m 1024 -smp 2`, user-mode
  networking with `hostfwd` for SSH, serial console logged to a file.
- **Repository.** The harness builds all packages, generates a flat unsigned repo, serves it
  with a local HTTP server, and the test device file points its apt source at the QEMU host
  address with `trusted=yes`.
- **Lifecycle.** Boot, wait for SSH, `cloud-init status --wait`, follow the reboot if
  `power_state` triggers one, run tests, tear down. On failure keep the serial log and the
  overlay so the broken state can be booted again.
- **Device files.** `testkit/src/pihero_testkit/devices/all-features/user-data` installs every
  pihero package. Apps add their own repository and packages to a copy of it.

### 10.5 Layout

```
testkit/
  pyproject.toml         # package "pihero-testkit"; apps depend on it as a pinned git dependency
  plugin.py              # --target, tier markers, host fixture
  vm.py                  # prepare, bootfs, boot, wait, reboot, teardown
  repo.py                # build packages, generate and serve the flat repo
  tools/Containerfile    # Debian trixie + nfpm + cloud-init + systemd + shellcheck + apt-utils
                         # + mtools + dosfstools + e2fsprogs + xz-utils
  images.lock            # Raspberry Pi OS image URL and sha256, Debian kernel version
  src/pihero_testkit/devices/all-features/user-data
packages/<name>/tests/
  test_<helper>.py       # tier 0
  test_installed.py      # tiers 1, 2, 4
```

### 10.6 Reproducibility

- Linux-side tooling runs in one tools container pinned by digest.
- Mac-side: QEMU, podman, uv from a `Brewfile`; `uv.lock` pins pytest and testinfra.
- Upstream inputs pinned in `images.lock`; downloads cached under `~/.cache/pihero/`.
- `make doctor` reports missing or drifted tools. `make test` runs tiers 0 and 1; `make test-all`
  adds tier 2.

### 10.7 CI

Tiers 0 and 1 on every push on `ubuntu-24.04-arm`. Tier 2 needs hardware virtualization, which
GitHub's arm64 runners do not offer, so it runs locally as part of `make release` and weekly in
CI under software emulation with a generous timeout. The weekly run is the "what rotted" signal.

### 10.8 Known limits

- Bluetooth in tier 2 gets a virtual adapter via `hci_vhci` and `btvirt`; adapter, NAP
  registration, and `pan0` are provable, data flow is not.
- Displays and dwc2 are tier 4 only.
- The gadget composition tests via `dummy_hcd` are not needed while `rpi-usb-gadget` owns the
  gadget; the approach stays available if the composite package is ever built.

## 11. Operations

- **Failures are loud.** Renderers exit non-zero when they cannot do their job; consumers are
  ordered after them. `systemctl --failed` is the diagnostic; the MOTD surfaces it.
- **Reboots are requested, never taken.** Postinst touches `/run/reboot-required` and
  `/run/reboot-required.pkgs`. First boot reboots through cloud-init `power_state` on that
  condition. Running devices reboot when the owner decides.
- **Removal is symmetric.** `prerm` disables and stops units; `postrm purge` deletes rendered
  `pihero-*` files and reverts boot config lines. Tier 1 asserts install, remove, nothing left.
- **Upgrades never prompt.** No package ships a file under `/etc/pihero/`; rendered files are
  regenerated at boot. `make upgrade TARGET=host` runs `apt upgrade` over SSH. Unattended
  upgrades from the pihero origin are an opt-in block in the sample device file.
- **Rollback is a version pin.** The pool keeps every published `.deb`; `apt install
  pihero-splash=2.1.0` rolls back, `apt-mark hold` freezes.
- **Release is a tag.** `vX.Y.Z` makes CI build all packages at that version, run tiers 0 and 1,
  regenerate the flat repo with `apt-ftparchive`, sign `Release` with the key in repository
  secrets, and push to `gh-pages`. `make release` runs tier 2 locally first and refuses to tag
  on red. Release notes are GitHub's generated ones.
- **Signing key.** One key pair. Public half pasted into device files. Rotation is a documented
  manual procedure.
- **Development loop.** `make deploy TARGET=host` builds and installs over SSH with `apt install
  ./pkg.deb`, skipping the repository.

## 12. Migration order and spikes

Principle: the first slice pushes one tiny feature through the entire pipeline; every later
feature only adds a package. Every step ends with tiers 0 to 2 green, tagged, published. The
first implementation plan covers steps 1 to 3; each later step gets its own plan.

1. **Spikes, time-boxed to a day each.**
   - VM preparation: Raspberry Pi OS Lite arm64 rootfs plus Debian kernel boots under HVF,
     mounts the bootfs image, consumes `user-data`, installs from the host-served repo.
     Fallback if it fails: Debian's official arm64 cloud image, at the cost of raspi-config,
     `rpi-usb-gadget`, and NetworkManager fidelity.
   - `linux/arm/v7` containers under podman on the Mac (binfmt in the podman machine).
   - `btvirt` availability in Debian Trixie (`bluez-test-tools` or build from source).
   - Behaviour of `rpi: enable_usb_gadget: true` in a VM without dwc2: does cloud-init fail or
     degrade gracefully, and does the NetworkManager profile exist for the `nmcli` override.
2. **Skeleton plus `pihero`.** Layout, tools container, Makefile, testkit tiers 0 to 2, CI for
   tiers 0 and 1, GitHub Pages repo, signing key. `pihero-bootconfig` with unit tests, MOTD,
   watchdog. Tag `v2.0.0`. Version 1 stays reachable at tag `pihero-ansible`.
3. **`pihero-avahi`.** The visible payoff. Flash one real Pi once as a sanity check of the
   pipeline against reality; not a tier, a checkpoint.
4. **`pihero-splash`.** First real user of `pihero-bootconfig` and the reboot flow; rebuilds the
   initramfs in the VM.
5. **`pihero-smb`.**
6. **`pihero-bt-pan`.**
7. **`pihero-display-hdmi`** after its KMS spike: how `video=` modes and forced hotplug behave
   on Trixie for the panels in use.
8. **Retire Ansible.** Delete `roles/`, `playbook.yml`, `inventory/`, `patch`, `scripts/`,
   `modules/`, `tasks/`, `group_vars/`, `test/`, `ansible.cfg`, `requirements.yml`,
   `requirements.txt`. Fold the Tailscale notes from `TODO.md` into the sample device file.
   Rewrite [README.md](../../../README.md) around flashing, a device file, and `make test`.
9. **Apps.** Each gets its own brainstorm and spec against the shared harness. pihole first,
   with the `panel-mipi-dbi` spike for the SPI panel; netmon next, with the Wayland kiosk spike.

## 13. What an app looks like

For reference when the app specs are written. Example: pihole.

- **`epaper-display`**: architecture-independent package. Flask app under
  `/usr/lib/epaper-display/`, Python dependencies from apt rather than a venv, the two Waveshare
  driver files vendored. Unit runs as a dedicated user in `spi` and `gpio`. SPI enabled by
  `rpi: spi: true`.
- **`pihole-chronometer`**: template, refresh script, unit.
- **`pihole-unattended`**: oneshot unit that runs the upstream unattended installer once, guarded
  by a condition on the pihole binary, plus the update timer. Pi-hole v6 uses `pihole.toml`.
- **fbcp-ili9341** may vanish: it reads the GPU framebuffer through dispmanx, which does not
  exist under KMS. The modern route is the `panel-mipi-dbi` DRM driver as a `dtoverlay` line.
  Spike on the actual panel; fallback is an architecture-specific package built in CI.
- **`devices/pihole.local/user-data`**: hostname, two apt sources, packages, `rpi:` flags,
  conffiles. Private.
- **Tests** depend on `pihero-testkit` pinned to a tag: pytest for the app, tier 1 install,
  tier 2 boot with a device file that adds the app repo.
- **Unit conventions** from `docs/app-conventions.md`: `Restart=always`, `MemoryMax=`, dedicated
  user, no dependency from any `pihero-*` unit onto an app unit.

## 14. Out of scope

- `pihero-usb-gadget-composite` and any gadget function beyond Ethernet.
- Automated hardware tier (power cycling, unattended flashing). Tier 4 is manual when it comes.
- Tier 3 fidelity runs.
- App migrations; each is its own spec.
- Fleet tooling, monitoring, remote logging.
- Re-provisioning a running device from a changed device file.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Raspberry Pi OS rootfs does not boot with Debian's kernel in `virt` | Tier 2 loses OS fidelity | Spike first; fallback to Debian cloud image |
| podman machine lacks `arm/v7` emulation | Tier 1 runs arm64 only | Enable binfmt in the machine; fallback to CI-only armhf |
| `btvirt` not packaged | Bluetooth tier 2 shrinks to unit checks | Build from bluez source in the tools container |
| `rpi:` cloud-init module misbehaves without hardware | Tier 2 device file diverges from real ones | Keep the difference to one documented line |
| GitHub arm64 runners lack KVM | Tier 2 in CI is slow | Weekly schedule with long timeout; local run gates releases |
| Trixie KMS changes display behaviour | `pihero-display-hdmi` contract shifts | Package is last; spike before it |
