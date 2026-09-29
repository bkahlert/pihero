# `pihero-usb-gadget`: Ethernet over USB as a package

Date: 2026-09-28. Status: approved design, ready for planning.

## Intent

Ethernet over USB is a Pi Hero feature today only in the sense that the [sample device file](../../../devices/sample/user-data)
carries it: two `write_files` entries (a modprobe.d file naming the gadget, a systemd unit loading `g_cdc` after
NetworkManager with MACs derived from the board serial) and two `runcmd` lines (`rpi-usb-gadget on -f` plus emptying its
modules-load file, and an `nmcli` line for the subnet). This moves the feature into a package, `pihero-usb-gadget`, that
delegates to upstream [`rpi-usb-gadget`](https://github.com/raspberrypi/rpi-usb-gadget) for everything upstream does well and
owns only what upstream gets wrong for a Mac host. It also fulfils the original request: the gadget is named after the board
from the device tree, so a Zero W shows up on the host as "Raspberry Pi Zero W Rev 1.1" instead of "Raspberry Pi USB Gadget".

Success looks like this: a device file lists `pihero-usb-gadget` under `packages` and optionally writes
`/etc/pihero/usb-gadget.conf`; after provisioning, a Mac on the USB cable gets an address from the Pi and lists the interface
under the board's name; `make test` proves the package builds, installs, enables, and purges cleanly; the ssh tier proves the
gadget on a real Pi.

## What upstream does and what we keep

`rpi-usb-gadget on` (verified against upstream 1.0.6, the version in the Raspberry Pi archive for Trixie, arm64 and armhf):

- writes `g_ether` to `/etc/modules-load.d/usb-gadget.conf`, the file that is also its on/off marker;
- appends `dtoverlay=dwc2,dr_mode=peripheral` to `config.txt`;
- creates two NetworkManager profiles on `usb0`, "USB Gadget (client)" (DHCP client, for host internet sharing) and
  "USB Gadget (shared)" (`ipv4.method shared` on `10.12.194.1/28`), and a dnsmasq snippet for short leases;
- enables `rpi-usb-gadget-ics.service`, a libnm watcher that flips between the two profiles;
- refuses to run at all unless `/proc/device-tree/model` contains "Raspberry Pi".

`rpi-usb-gadget off` reverts all of it. We keep all of it. What we replace, with the reasons recorded in
[raspberry-pi-os.md](../../raspberry-pi-os.md):

- `g_ether` passes no frames to macOS 27; `g_cdc` (CDC ECM plus an ACM port) works on macOS and Linux.
- The module has to load after NetworkManager, because macOS asks for DHCP only while the link comes up.
- The MACs come from the board serial so the host sees one device across boots; the product string comes from the board model.
- The shared subnet is a device setting.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Gadget implementation | `g_cdc` | Proven on macOS 27 and Linux in the field notes; one `modprobe`; the boot script is the single place a configfs NCM gadget could replace it later |
| Relationship to upstream | Hard dependency, `rpi-usb-gadget on -f` in postinst, `off` in purge | Upstream is maintained by Raspberry Pi and owns the boot overlay, the profiles, and internet-sharing detection |
| Neutralising `g_ether` | `blacklist g_ether` in `/usr/lib/modprobe.d/pihero-usb-gadget.conf` | `systemd-modules-load` applies kmod's blacklist (`KMOD_PROBE_APPLY_BLACKLIST` in systemd's `module-util.c`), so upstream's marker file keeps saying "on" while its module never loads, and rerunning `rpi-usb-gadget on` stays harmless |
| When the unit runs | `ConditionPathExistsGlob=/sys/class/udc/*` | A device controller exists only once the overlay is active in peripheral mode; before the enabling reboot, in containers, and in the VM the unit is skipped, never failed |
| Enabling | Installing the package turns the feature on | Same rule as the planned splash package; not installing is how the feature is off |
| Own code | Python 3 standard library | The design doc reserves shell for `ExecStart=` lines and maintainer scripts; argv lists avoid the kernel's quote syntax leaking through three layers of shell quoting |
| Configuration | `PRODUCT` and `CIDR` in `/etc/pihero/usb-gadget.conf`, both optional | The two things a device owner changes; manufacturer stays "Raspberry Pi Ltd."; USB IDs and `iSerialNumber` stay untouched |
| Change procedure | Edit the conffile, reboot | The module takes its parameters at load time; consistent with every other Pi Hero setting |

## Package anatomy

```
packages/pihero-usb-gadget/
  nfpm.yaml                                             # depends: pihero, rpi-usb-gadget
  units.txt                                             # pihero-usb-gadget.service
  root/usr/lib/pihero/usb-gadget                        # Python: identity, subnet, modprobe
  root/usr/lib/systemd/system/pihero-usb-gadget.service
  root/usr/lib/modprobe.d/pihero-usb-gadget.conf        # blacklist g_ether
  scripts/postinst.sh                                   # rpi-usb-gadget on -f, reboot request
  scripts/postrm.sh                                     # purge: rpi-usb-gadget off, reboot request
  tests/test_usb_gadget.py                              # tier 0
  tests/test_installed.py                               # tiers 1, 2, and ssh
```

`nfpm.yaml` follows `pihero-avahi`: `Architecture: all`, `Section: admin`, `depends: [pihero, rpi-usb-gadget]`, the tree under
`root/`, the generated maintainer scripts. The description says what the package does in two lines: Ethernet over USB named
after the board, on top of `rpi-usb-gadget`.

### The unit

```ini
[Unit]
Description=Pi Hero: USB Ethernet gadget (CDC ECM)
After=NetworkManager.service
Wants=NetworkManager.service
ConditionPathExistsGlob=/sys/class/udc/*

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=-/etc/pihero/usb-gadget.conf
ExecStart=/usr/lib/pihero/usb-gadget

[Install]
WantedBy=multi-user.target
```

No ordering against `rpi-usb-gadget-ics.service` is needed: the watcher polls NetworkManager for `usb0` and activates the
shared profile once the interface appears; the profile autoconnects anyway.

### The script

`/usr/lib/pihero/usb-gadget`, Python 3 standard library, no arguments. Environment:

| Variable | Meaning | Default |
|---|---|---|
| `PRODUCT` | USB product string | the device-tree model, NUL and whitespace stripped |
| `CIDR` | address of the "USB Gadget (shared)" profile | unset: the profile is left as upstream created it |
| `PIHERO_DEVICE_TREE` | directory holding `model` and `serial-number` | `/proc/device-tree` |

Steps, in order:

1. Read `serial-number` and `model`. Take the last ten hex digits of the serial, group them in pairs, and prefix `02:` for
   `host_addr` and `06:` for `dev_addr`, exactly what the sample unit's `sh` line computed. Product is `PRODUCT` if set,
   else the model. A missing serial, or neither `PRODUCT` nor a model, exits 1 with a message on stderr.
2. If `CIDR` is set: `nmcli connection modify "USB Gadget (shared)" ipv4.addresses <CIDR>`. Non-zero exit of `nmcli` exits 1;
   a missing profile means upstream is not on, which is a real failure.
3. `modprobe g_cdc host_addr=<h> dev_addr=<d> iManufacturer="Raspberry Pi Ltd." iProduct="<product>"`, each parameter one
   argv element, the two string values wrapped in literal double quotes because the kernel's parameter parser wants them for
   values containing spaces. Non-zero exit of `modprobe` exits 1.
4. Print one line to stdout naming the module and the arguments, so the journal shows what was loaded.

`modprobe` and `nmcli` are found through `PATH`, which is how the tests substitute recording stubs. The pure pieces have
names the tests call directly: reading a device-tree string, deriving the two MACs from a serial, and building the argv.

### Maintainer scripts

Generated from `units.txt` and the fragments, like every package. The fragments:

- `postinst.sh`: if `/proc/device-tree/model` contains "Raspberry Pi" and `/etc/modules-load.d/usb-gadget.conf` does not
  exist, run `rpi-usb-gadget on -f`, write `/run/reboot-required` with the text `bootconfig` writes (`*** System restart required ***`), and add `pihero-usb-gadget` to
  `/run/reboot-required.pkgs` once. Upstream already on means nothing to do and no reboot to request; an upgrade therefore
  never asks for one. The generated part then enables and restarts the unit, whose condition is false until the reboot.
- `postrm.sh` (purge block): if the model contains "Raspberry Pi", `rpi-usb-gadget` is still on `PATH`, and the marker file
  exists, run `rpi-usb-gadget off` and request the reboot the same way. The package owns the feature, so purging it turns the
  feature off.

Plain `remove` stops and masks the unit through the generated script and deletes the blacklist with the package; upstream
stays on, so the next boot runs upstream's stock `g_ether` gadget. That is the Debian meaning of remove versus purge and needs
no extra code.

## Configuration contract

`/etc/pihero/usb-gadget.conf` is optional, written by the device file, read with `EnvironmentFile=-`, `KEY=VALUE` per line.
Values with spaces are double-quoted, as systemd's environment-file syntax requires:

```
PRODUCT="Kitchen Pi"
CIDR=10.10.10.10/29
```

Nothing ships under `/etc/pihero/`; defaults live in the script. A change takes effect on the next boot.

## Device files

- [devices/sample/user-data](../../../devices/sample/user-data): `pihero-usb-gadget` joins `packages`; the `g_cdc.conf` and
  `usb-gadget.service` entries and the two gadget `runcmd` lines go; a `write_files` entry adds
  `/etc/pihero/usb-gadget.conf` with `CIDR=10.10.10.10/29` and a comment naming `PRODUCT` as the other key. The `bootcmd`,
  the apt source, the pretty-name lines, `power_state`, and the Tailscale lines stay as they are. The second provisioning
  reboot is now requested by the package's postinst instead of `runcmd`.
- `testkit/src/pihero_testkit/devices/all-features/user-data`: `pihero-usb-gadget` joins `packages`. In the VM the postinst
  skips upstream (not a Raspberry Pi) and the unit is skipped by its condition, which is exactly what tier 2 should prove.
  The explicit `touch /run/reboot-required` stays, since no package requests a reboot in the VM.

## Harness

The tier-1 container image (`testkit/src/pihero_testkit/tier1/Containerfile`) gains the Raspberry Pi archive
(`https://archive.raspberrypi.com/debian/`, suite `trixie`, component `main`) as a deb822 source signed by the archive key,
which is committed next to the Containerfile as `raspberrypi.asc` and copied into `/etc/apt/keyrings/`. Without it the
dependency on `rpi-usb-gadget` cannot resolve in tier 1. The archive also carries Raspberry Pi's versions of a few Debian
packages; apt preferring them brings tier 1 closer to Raspberry Pi OS and is accepted. The tier-1 image is tagged by platform only today and built when the tag is missing, so the harness
changes to tag it with a digest of the build context, as the tools image already is, and a changed Containerfile is rebuilt on
first use.

Installing `rpi-usb-gadget` pulls `network-manager` into the container, where it may not fully start for lack of
`CAP_NET_ADMIN`. The container is accepted in `degraded` state already, and no tier-1 test asserts on NetworkManager.

## Tests

Tier 0, `tests/test_usb_gadget.py`, runs the script as a subprocess with `PIHERO_DEVICE_TREE` pointing at a fixture directory
and a temporary directory first on `PATH` holding `modprobe` and `nmcli` stubs that append their argv to a log:

- MACs: the serial `00000000a1b2c3d4` yields `02:00:a1:b2:c3:d4` and `06:00:a1:b2:c3:d4`.
- Module arguments: the argv is `g_cdc`, the two MAC parameters, `iManufacturer="Raspberry Pi Ltd."`, and the quoted
  product, in that order, each one element.
- CLI defaults: with a model file `Raspberry Pi Zero W Rev 1.1\0` and no `PRODUCT`, `modprobe` receives
  `iProduct="Raspberry Pi Zero W Rev 1.1"`, and `nmcli` is not called.
- `PRODUCT` overrides the model; `CIDR` produces the `nmcli` call before the `modprobe` call with the given address.
- Exit 1 with a message on a missing serial, on a failing `nmcli`, and on a failing `modprobe`; `modprobe` is not called when
  `nmcli` fails.
- A `PRODUCT` containing a double quote exits 1 before any call; an empty `PRODUCT=` falls back to the model.

The existing tier-0 sweeps pick the new files up automatically: shellcheck over the fragments and generated scripts,
`systemd-analyze verify` over the unit, `cloud-init schema` over both device files, and the build of every package.

Tiers 1, 2, and ssh, `tests/test_installed.py`:

- The package is installed at the built version and `rpi-usb-gadget` is installed with it.
- `/usr/lib/pihero/usb-gadget` is `0755` root; `/usr/lib/modprobe.d/pihero-usb-gadget.conf` contains `blacklist g_ether`.
- The unit is enabled. On a Raspberry Pi (device-tree model contains "Raspberry Pi") it is active; elsewhere it is inactive
  and not failed.
- On a Raspberry Pi: `usb0` exists, `/sys/module/g_cdc/parameters/iProduct` equals `PRODUCT` from the conffile or the model,
  and `host_addr` there matches the serial-derived address.
- Purge (mutating) leaves neither the script, the unit, nor the modprobe.d file behind; then reinstall.

QA for the whole change: tiers 0 and 1 green on the branch on both platforms, tier 2 green, then `make deploy` to a Pi, the
ssh-tier tests green there, and a Mac listing the USB interface under the board name.

## Documentation

- [README.md](../../../README.md): a `pihero-usb-gadget` row in the package table; the quick start no longer lists the USB
  subnet as a device-file edit but points at the conffile.
- [docs/design.md](../../design.md): the "USB Ethernet" decision row names the package; the package anatomy tree and the
  architecture diagram list it; a `pihero-usb-gadget` section describes it; the planned-packages bullet goes; the
  "Identity" line in the configuration contract says the subnet comes from `/etc/pihero/usb-gadget.conf`.
- [devices/README.md](../../../devices/README.md): the `write_files` and `runcmd` descriptions shrink, a paragraph documents
  `/etc/pihero/usb-gadget.conf`, and the note about macOS keeping the old service name until it is removed in Network settings
  is added once confirmed on hardware.
- [docs/raspberry-pi-os.md](../../raspberry-pi-os.md): field notes that say "the device file does X" say "the package does X";
  the gadget-name sentence names the model.
- [docs/operations.md](../../operations.md): the bring-up step names the conffile for the subnet.
- [docs/testing.md](../../testing.md): the tier-1 image description mentions the Raspberry Pi archive; "what a container
  cannot show" gains the gadget.

## Out of scope

A configfs NCM gadget and Windows hosts; USB vendor and product IDs and `iSerialNumber`; upstream's MOTD hint about the
Windows RNDIS driver, which keeps printing while the marker file exists and is upstream's conffile; gadget functions beyond
Ethernet; reacting to a conffile change without a reboot.

## Risks and open points

- macOS names its network service when it first sees a host MAC. A Mac that already knows a Pi may keep showing
  "Raspberry Pi USB Gadget" until the service is removed in Network settings. To confirm on hardware and document.
- `ConditionPathExistsGlob=/sys/class/udc/*` assumes the `udc` class only holds controllers in peripheral or OTG mode; on
  every Raspberry Pi the sample targets, `dwc2` in host mode registers none. If a board ever shows a controller without the
  overlay, the unit runs and `modprobe` fails loudly, which is the intended failure mode.
- A `PRODUCT` containing a double quote would break the kernel's parameter parser. The script rejects it with exit 1 before
  calling anything: the conffile is owner input at a system boundary.
