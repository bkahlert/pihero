# Design

Pi Hero 2 makes a Raspberry Pi discoverable, reachable, and pleasant to use with three things: Debian packages as the unit of a
feature, one cloud-init file per device, and a test harness that proves every feature on a Mac before a Pi is involved. This
document records the decisions. [testing.md](testing.md) covers the harness, [raspberry-pi-os.md](raspberry-pi-os.md) the
platform quirks the device files work around, [devices/README.md](../devices/README.md) the device file, and
[pihero-1.md](pihero-1.md) what became of the Ansible version.

## Goals and constraints

- Tests come first. Every feature is proven automatically, and `make test` after a year of neglect is either green or says what
  rotted. Manual testing on hardware is what version 2 exists to end.
- Version 1's functionality stays; its implementation was free to change completely, and did.
- The hardware floor for applications is the Raspberry Pi Zero W (ARMv6, 512 MB). Every `pihero-*` package is therefore
  `Architecture: all` and depends only on packages present in both the 64-bit and the 32-bit Raspberry Pi OS archives, so no
  design element branches on the board. Containers are not the application plane: the `arm/v6` image ecosystem is thin, and
  SPI, GPIO, and framebuffer access from a container on 512 MB fights the platform. Applications are systemd services delivered
  as packages.
- The target OS is Raspberry Pi OS Lite on Debian 13 (Trixie), which ships cloud-init. The 32-bit image supports every board
  including the Zero W; the 64-bit image supports the Zero 2 W and up. Both are pinned in
  [images.lock](../testkit/src/pihero_testkit/images.lock): the device file names its image, 64-bit
  unless it says otherwise, and the harness runs the 64-bit one.
- Upstream mechanisms win over own code: `rpi-usb-gadget`, NetworkManager, `raspi-config nonint`, cloud-init's `rpi:` module.
  Own code exists only where they have no option, and then it is Python 3 standard library.
- The interactive CLI and `gum` are gone from the device: too slow on old boards, and the tests replace the diagnostics. Mac-side
  commands ask for what `make` was not given, with nothing beyond `input()`.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Delivery | Debian packages, a flat signed apt repository, cloud-init on the card | Idiomatic on a Debian-based OS, hard feature boundaries, testable at build, install, and boot, updates are `apt upgrade`, no control machine |
| USB Ethernet | `pihero-usb-gadget` on top of upstream `rpi-usb-gadget`, loading `g_cdc` from its own unit | Maintained by Raspberry Pi and handles internet-sharing detection; its `g_ether` default and its cloud-init hook both fail in practice, see [raspberry-pi-os.md](raspberry-pi-os.md) |
| USB serial console | Dropped for the GPIO UART (`rpi: interfaces: serial: true`) | A broken gadget broke its serial port too, so it never was an independent path |
| Custom gadget functions (mass storage, HID) | Deferred until an application needs one | Mutually exclusive with `rpi-usb-gadget` on one board |
| Samba shares | Dropped; `pihero-avahi` announces `_smb._tcp` with nothing behind it | The shares only ever put the Pi into Finder's network browser, which lists file servers and takes the icon from `_device-info._tcp` |
| Splash screen | Dropped; the console stays as Raspberry Pi OS ships it | Version 1's Plymouth theme needs `quiet`, `loglevel=3`, and `systemd.show_status=auto`, which hide the messages that matter when a headless board does not come up; installing Plymouth rebuilds both initrds three times, three and a half minutes on a Zero 2 W and double the emulated tier-2 run; a spinner is not worth that surface, see [raspberry-pi-os.md](raspberry-pi-os.md) |
| On-device logic | Python 3 standard library for anything that parses or edits files; shell only in `ExecStart=` lines and maintainer scripts | Idempotent edits of boot files are where shell bites; cloud-init guarantees Python on every image; the cast is the exception, see "Cast language" |
| Package build | `nfpm`; `cog` rebuilds Debian's source package with `dpkg-buildpackage` in its own image | One YAML manifest plus a file tree, builds in under a second, no Debian toolchain; the one package that is not Pi Hero's own code keeps Debian's packaging and adds a patch |
| Kiosk browser | Debian's `cog` 0.18.4-1 rebuilt as `0.18.4-1+pihero1` with the DRM SHM export fix, arm64 only | Software-rendered frames, which the tier 2 VM produces on its virtual GPU, crash the stock modeset renderer; the fix is unreleased upstream ([Igalia/cog#794](https://github.com/Igalia/cog/pull/794)); the same package name lets devices take it with `apt upgrade`; the 32-bit boards keep Debian's, see [`pihero-kiosk`](#pihero-kiosk) |
| Tests | pytest with pytest-testinfra | One assertion API over a podman container, a VM, and a real Pi |
| Core package name | `pihero` | Core plus suffix, as in `tailscale` or `git` |
| Cast package | `kaomoji`, a flat directory with a `build` script; one binary in `/usr/bin/`, a deb per architecture built in the tools image | `pihero` depends on it for its MOTD, so it cannot be a `pihero-*` feature package; the directory stays a runnable checkout for `go run kaomoji.go hero`, the GIF Makefile, `kaomoji-gif`, and the tests; a compiled program needs a deb per architecture, which a manifest alone cannot give, see [`kaomoji`](#kaomoji) |
| Cast language | Go, standard library only, one source file, no `go.mod` | The exception to "On-device logic": a terminal animation needs an instant start and a binary without a runtime, which neither bash (a second to the first frame on a Pi 1, bash 5 and ncurses needed) nor Python (a third of a second, Python needed) gives; Go cross-compiles for the Pi 1's ARMv6 and for a Mac with one command, where Rust needs a cross toolchain and a manifest beside the source; one file keeps `go run kaomoji.go hero` possible from a checkout |
| Device files that share content | Standalone copies | Simpler than a merge step |
| Card backup | `make backup` and `make restore`: a full raw xz image taken on the Mac through `authopen`, restored onto a card of the same size or larger | Brings back state no device file holds; the format is that of Raspberry Pi OS images, so `flash`'s writer and verifier restore it; shrinking so a nominally equal card fits is the planned follow-up |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Apps            pihole-chronometer, epaper-display, netmon   │  own repos, own packages, own tests
├─────────────────────────────────────────────────────────────┤
│ Pi Hero         pihero, pihero-avahi, pihero-usb-gadget,     │  this repo, packages/*
│                 pihero-kiosk, kaomoji, later pihero-bt-pan  │
├─────────────────────────────────────────────────────────────┤
│ Raspberry Pi OS Lite (Trixie), cloud-init, rpi-usb-gadget,   │  written by make flash or Imager
│ NetworkManager, avahi-daemon, raspi-config                   │
└─────────────────────────────────────────────────────────────┘
        ▲ described by one file: devices/<host>/user-data on the boot partition
```

Never losing contact with a device rests on three independent paths: physical (Ethernet over USB, the GPIO UART, later
Bluetooth PAN), remote (Tailscale, installed from its upstream repository through the device file, no Pi Hero code involved),
and self-healing (the hardware watchdog Raspberry Pi OS arms with a minute, plus the [unit conventions](app-conventions.md)
that keep a misbehaving application from starving sshd; no Pi Hero unit ever depends on an application unit).

## Repository layout and package anatomy

One directory per package, mirroring the target filesystem: everything a feature installs sits under `root/` where it lands on
the Pi, and its tests sit next to it.

```
packages/
  pihero/
    nfpm.yaml
    root/usr/lib/pihero/bootconfig                          # Python, boot-config editor
    root/usr/lib/pihero/motd                                # Python, MOTD generator
    root/etc/update-motd.d/50-pihero                        # sh, calls motd
    scripts/postinst.sh  scripts/prerm.sh  scripts/postrm.sh # optional hook fragments
    units.txt                                               # units to enable
    tests/test_<helper>.py                                  # tier 0
    tests/test_installed.py                                 # tiers 1, 2, and ssh
  pihero-avahi/
    root/usr/lib/pihero/avahi-render
    root/usr/lib/systemd/system/pihero-avahi-render.service
    root/usr/share/pihero/avahi/*.service.in
  pihero-usb-gadget/
    root/usr/lib/pihero/usb-gadget                          # Python, loads g_cdc named after the board
    root/usr/lib/systemd/system/pihero-usb-gadget.service
    root/usr/lib/modprobe.d/pihero-usb-gadget.conf          # blacklist g_ether
  kaomoji/                                                  # flat, no root/ and no nfpm.yaml: builds itself, see Decisions
    kaomoji.go                                              # Go, the engine and the three characters -> /usr/bin/kaomoji
    build  nfpm.yaml.in  bootstrap.sh                       # cross-compiles in the tools image, packs a deb per architecture, renders the curl-line scripts
    README.md                                               # the cast, shown as GIFs
    kaomoji-gif                                             # bash, records a command with asciinema and renders it with agg, Mac-side, not shipped
    Makefile  assets/*.gif                                  # the README's GIFs and how they are rendered, not shipped
    tests/test_<character>.py  test_kaomoji.py  test_bootstrap.py  test_build.py   # tier 0
    tests/test_installed.py                                 # tiers 1, 2, and ssh
  cog/                                                    # Debian's cog rebuilt with one patch, see pihero-kiosk; no nfpm.yaml
    Containerfile  build                                  # its own build image and script: dpkg-buildpackage on the pinned Debian source
    patches/0001-*.patch                                  # DEP-3, the two hunks of Igalia/cog#794 that matter
    tests/test_build.py  tests/test_installed.py          # tier 0; tiers 1, 2, and ssh
testkit/                                                    # the harness, a Python package
devices/                                                    # device files, gitignored except sample/
backups/                                                    # card images and their sidecars, gitignored
```

- **Names.** `pihero` is the core, everything else is `pihero-<feature>`, except `kaomoji`: the cast is no Pi Hero
  feature, and `pihero` depends on it. Units are `pihero-<feature>*.service`, rendered files
  carry the `pihero-` prefix.
- **Paths.** Executables in `/usr/lib/pihero/`, data and templates in `/usr/share/pihero/<feature>/`, units in
  `/usr/lib/systemd/system/`, device overrides in `/etc/pihero/<feature>.conf`, state in `/var/lib/pihero/`. `kaomoji` puts
  its one binary in `/usr/bin/`.
- **Manifest.** `nfpm.yaml` declares `Architecture: all`, `Section: admin`, the dependencies, the tree under `root/`, and the
  maintainer scripts; `kaomoji` has no manifest the build reads directly: a `build` script without a Containerfile runs in the tools image with the version and prints its debs, one per architecture, from a manifest template. `cog` has no manifest: a package directory with an executable `build` next to a
  `Containerfile` builds itself in that image, and the testkit takes the `.deb` paths the script prints. Every nfpm package
  carries the one version derived from `git describe`: `2.1.0` at the tag,
  `2.1.0+3.abc1234` three commits past it, `.dirty` appended for an uncommitted tree, `2.1.0~rc.1` for the pre-release tag
  `v2.1.0-rc.1`; `VERSION=` overrides it; `cog` keeps Debian's version with a `+pihero<n>` suffix.
- **Maintainer scripts.** Minimal POSIX shell that calls `deb-systemd-helper` and `deb-systemd-invoke`, as debhelper would emit,
  generated by the build into `packages/<name>/.build/` from `units.txt` and the optional `scripts/*.sh` fragments; edit
  those, never `.build/`. shellcheck runs over all of them.

## The `pihero` core package

Every other package depends on it.

**bootconfig** (`/usr/lib/pihero/bootconfig`) edits `/boot/firmware/config.txt` and `cmdline.txt` idempotently:
`set|unset config KEY [VALUE] [--section all]` and `add|remove cmdline PARAM[=VALUE]`. It changes exactly the addressed key,
leaves the rest byte-identical, respects `config.txt` sections, matches repeatable keys such as `dtoverlay` on the full
`key=value`, and matches command-line parameters by name so `add loglevel=3` replaces `loglevel=7`. A `cmdline.txt` with more
than one line is refused untouched. On change it touches `/run/reboot-required` and appends the calling package, passed with
`--package`, to `/run/reboot-required.pkgs`; it never reboots. `PIHERO_BOOTFS` redirects it for tests. It is used only where
cloud-init's `rpi:` module and `raspi-config nonint` have no option.

**MOTD.** `/etc/update-motd.d/50-pihero` runs `/usr/lib/pihero/motd`: a blank line to set it apart from Debian's kernel
line, the hero in the mood of the board, then the installed `pihero-*` packages with versions, failed units, whether a
reboot is pending and for which packages, and the address of `usb0` if present, closed by a blank line so sshd's
`Last login` line does not sit on the last row. The mood follows the lines below it: sad
when a unit has failed, puzzled (`unknown`) when a reboot is pending, happy otherwise; neutral, the hero at rest, is
left to the panels. The banner is `hero --mood <mood> --no-color` from `kaomoji`, found on `PATH` and run at every
login: plain, static, and 0.3–0.5 s on a Pi 1 next to the 2.4 s the probes take (busy-screen.local, 2026-09-30).
pam_motd runs the script in the C locale; reading the hero from `hero` and writing it to the terminal both rely on
Python's UTF-8 mode, which Python enters on its own in that locale (PEP 540). No colours, no animation, nothing beyond
Python and that one call. Debian's legal notice, `/etc/motd`, the static half pam_motd prints after the dynamic one, the
device file empties: base-files copies its default only when the file is missing, so an empty file stays and raises no
conffile prompt, where a deleted one comes back with the next base-files upgrade. `~/.hushlogin` silences the whole
greeting; sshd honours it before it shows the PAM messages, and login opens the session silent (2026-10-03).

**Watchdog.** Raspberry Pi OS arms the BCM2835 hardware watchdog itself, `RuntimeWatchdogSec=1m` in its
`40-rpi-enable-watchdog.conf`, and `pihero` leaves it there. 2.1.0 shipped a drop-in tightening it to 15 s, the hardware
maximum, and reset every Zero W during provisioning: systemd on that board needs 13.5 s for a `daemon-reload` at idle,
longer under dpkg's load, and every package's postinst reloads. Measured on liet, 2026-09-28; the drop-in went in 2.1.1.

## `pihero-avahi`

Depends on `pihero` and `avahi-daemon`. `pihero-avahi-render.service` (`Type=oneshot`, `RemainAfterExit=yes`,
`Before=avahi-daemon.service`, `EnvironmentFile=-/etc/pihero/device-info.conf`) runs `avahi-render` every boot, which writes
`/etc/avahi/services/pihero-device-info.service`, `pihero-ssh.service`, and `pihero-smb.service` from the templates: the
service name is the pretty hostname from `hostnamectl`, `_device-info._tcp` carries `model=` from `MODEL` (default `AirPort4`)
and `machine=` from `/proc/device-tree/model`, `_ssh._tcp` and `_sftp-ssh._tcp` point at port 22, and `_smb._tcp` at port
445. The SMB record is what puts the Pi into Finder's network browser: Finder lists file servers and uses `_device-info._tcp`
only for the icon, so without it neither shows. Nothing listens on 445, and opening the entry fails; a Samba of its own would
announce the plain hostname next to the pretty name, which is why version 1 turned Samba's registration off. Records are
plain text because avahi 0.8 ignores `value-format` and would hand a base64 value to clients undecoded. The unit reloads Avahi with
`systemctl --no-block try-reload-or-restart`; the blocking form deadlocked the boot. `/etc/avahi/avahi-daemon.conf` is not
touched: it is a conffile of `avahi-daemon`, and Debian's defaults already match what version 1 set. Purge removes the rendered
files.

## `pihero-usb-gadget`

Depends on `pihero` and Raspberry Pi's `rpi-usb-gadget`, which owns the `dwc2` overlay, the two NetworkManager profiles on
`usb0`, and the watcher that switches between them when the host shares its internet connection. postinst runs
`rpi-usb-gadget on -f` once and requests the reboot; purge runs `off` and requests one too. What upstream gets wrong for a
Mac the package replaces: `/usr/lib/modprobe.d/pihero-usb-gadget.conf` blacklists `g_ether`, which `systemd-modules-load`
honours, and `pihero-usb-gadget.service` (`Type=oneshot`, `After=NetworkManager.service`,
`ConditionPathExistsGlob=/sys/class/udc/*`, `EnvironmentFile=-/etc/pihero/usb-gadget.conf`) runs `usb-gadget` every boot,
which sets `CIDR` on the "USB Gadget (shared)" profile if given and loads `g_cdc` with `host_addr` and `dev_addr` derived
from the board serial, `iManufacturer` "Raspberry Pi Ltd.", and `iProduct` from `PRODUCT` or the device-tree model. The
condition keeps the unit skipped, not failed, until the enabling reboot and on anything without a device controller, which
is what the container and the VM are. Module parameters are read at load time, so a conffile change takes effect on the
next boot.

## `pihero-kiosk`

Depends on `pihero`, `cog`, `libgles2`, `fonts-dejavu-core`, and `adduser`, which its postinst needs for the `kiosk` user and
which Trixie's minimal images no longer carry. `pihero-kiosk.service` runs `/usr/lib/pihero/kiosk` as the system user
`kiosk` with the supplementary groups `video`, `render`, and `input`: the script waits until `URL` answers (file or http),
then execs `cog --platform=drm URL`, so WPE WebKit paints straight onto the DRM device with no X server, display manager, or
compositor. `URL` and `COG_ARGS` come from `/etc/pihero/kiosk.conf` (`EnvironmentFile=-`), the default page is a black
`/usr/share/pihero/kiosk/index.html` saying where to set the URL. `ConditionPathExistsGlob=/dev/dri/card*` keeps the unit
skipped, not failed, in the container, a VM started with `--display none`, and on a headless board; the tier 2 VM has a
virtual display by default since 2.4.0, where the unit runs on Pi Hero's cog; `Restart=always` with
`StartLimitIntervalSec=0` covers a panel that appears late; `MemoryMax=300M` binds once the device file has turned the
memory controller on (see [app-conventions.md](app-conventions.md)). Cog's own environment passes through, so a panel with
several modes takes `COG_PLATFORM_DRM_VIDEO_MODE=800x480` in the same file.

A panel on SPI with a `mipi-dbi` KMS driver (`ili9486` and its relatives, `dtoverlay=piscreen,drm` for the Waveshare 3.5-inch)
lists only XRGB8888 and RGB565. Cog's default "modeset" renderer scans out WPE's ARGB8888 buffer unchanged, so such a panel
refuses every frame with `failed to create framebuffer: Invalid argument` while cog still logs `Loaded successfully`, and the
console stays on the screen. `COG_ARGS=--platform-params=renderer=gles` makes cog draw into its own buffer in a format the
plane lists. The same board needs the vc4 card hidden from the unit (a drop-in with `DevicePolicy=closed` and `DeviceAllow=`
for the panel's card by path, the render node and `char-input`), `fbcon=map:1` so the panel's CRTC is lit before cog starts,
and `video=HDMI-A-1:d`; the busy-screen device file in its repository is the worked example (2026-09-29).

cog itself comes from this repository since 2026-10-01: [packages/cog](../packages/cog) rebuilds trixie's 0.18.4-1 as
`0.18.4-1+pihero1` with one patch, the two hunks of [Igalia/cog#794](https://github.com/Igalia/cog/pull/794) that keep the
modeset renderer's pointer out of the SHM buffer resource's user data, where libwayland keeps the `wl_shm_buffer`, and
release the client's buffer once its pixels are copied. Without them cog segfaults on the third frame wherever WPE renders
in software and hands cog `wl_shm` buffers, which is what the tier 2 VM does on its virtual GPU (macOS QEMU has no virgl).
A board renders on its GPU and exports dmabufs, so it never ran that code; it takes the package on its next upgrade because
apt prefers the higher version, and behaves as before. The package is arm64 only, the 32-bit boards keep Debian's, and it
goes away once Debian ships a cog whose SHM path works. The gles renderer has no SHM path at all
([Igalia/cog#722](https://github.com/Igalia/cog/issues/722)), so a device file that selects it for a panel renders its VM
copy without that setting. Design: [2026-10-01-cog-package-design.md](superpowers/specs/2026-10-01-cog-package-design.md).

Why cog: the Zero 2 W has 512 MB, and Chromium fit there only with a gigabyte of swap; WPE runs a page in roughly a third
of Chromium's footprint, and the whole stack is one upstream tool in one unit. Measured on the netmon board (2026-09-29,
the kiosk next to a JVM scanner): the kiosk's cgroup holds about 80 MB in RAM and swaps another 120 to 175 MB into the
zram device Raspberry Pi OS Trixie configures (`rpi-swap`), so `free -m` alone understates the footprint; tightening
`MemoryMax=` and `MemorySwapMax=` below that working set made the board thrash and the hardware watchdog reset it. The
caps are leak guards, not a budget, and `rpi-zram-writeback.timer`, which pages the zram device out to a file on the
SD card, is worth masking on a board that swaps. The documented fallback, not built, is `cage`
with `chromium --ozone-platform=wayland --kiosk` and zram swap: a different `ExecStart`, not a different design. The wait
for the URL replaces an ordering dependency: no Pi Hero unit depends on an application unit, yet the page an app serves
comes up seconds after the kiosk would otherwise have loaded an error page for the rest of the uptime.

## `kaomoji`

The Pi Hero cast, shipped as the package `kaomoji` from [packages/kaomoji](../packages/kaomoji): one Go program,
[kaomoji.go](../packages/kaomoji/kaomoji.go), standard library only, built into `/usr/bin/kaomoji` for armhf, arm64, and
amd64; `kaomoji hero`, `kaomoji wizard`, and `kaomoji visitor` print one face each. It depends on nothing; `pihero` depends
on it for its MOTD. Its tests run in tier 0 against the binary built for the Mac through the tools image, gofmt and go vet
pass over the source as shellcheck does over the scripts, and tier 1 installs the deb of the container's architecture and
runs the faces from `PATH`. The engine drives the terminal with ANSI sequences alone, no tput and no terminfo: hide and
show the cursor, erase to the end of the line, cursor up for the grid, SGR for colors. A sprite is a slice of graphemes,
each with its text, its cells from a small East Asian width table, and its style; a style is a basic color, which follows
the terminal's theme and is what the wizard and the visitor wear, or a hex color with the 256-color index that stands in
for it, the hero's palette, painted as truecolor when `COLORTERM` says so, by index on a `TERM` with `256color`, in
fbterm's own sequences on that framebuffer terminal, which ignores the standard ones, and dropped elsewhere.

The hero's hand is `━` at rest and `—` while hovering, both glyphs of DejaVu Sans Mono: fbterm draws a glyph its font
lacks from any installed font and clips it to the one cell wcwidth gives it, which cut the former `⫎` in half.

An animation runs on a clock. A character gives a timeline for a mood and a line width: the steps of its entrance, of one
hover cycle, of its exit, and the frame times the exit lasts. The frame of a step is a pure function, hover steps map
onto the first cycle, and the frame of a step is due when the one before has stayed its time, counted from when that one
was due; a late frame goes out at once and the schedule moves with it, so frames are never skipped and the output stays
deterministic, which the tests count frame by frame at `--frame-ms 0`. The hover shows a frame per frame time; the
entrance and the exit spread their duration under constant acceleration, the fastest interval a quarter of the mean and
the slowest one and three quarters, the entrance slowing down into the hover and the exit speeding up out of it. An exit
lasts half as many frame times as the entrance, twice its pace. The hero enters and leaves one cell per step, its exit
crossing the whole line in eight frame times however wide it is, so a 200-column terminal sees 200 frames half a
millisecond to four apart where a 40-column one sees 40. `hero` flies in from the left, hovers, and flies out through the
terminal's right edge; `wizard` slides in, conjures its magic particle by particle, runs the colors along it, and slides
out to the left; `visitor` peeks out from behind a wall that slides in, waves and blinks, and ducks back before the wall
slides out. The wizard's and the visitor's exits are their entrances run backwards, so an exit begun during the entrance
runs back from where the entrance stood, in as many steps; the hero leaves from wherever it is. Every call prints one
kaomoji: the first mood, static, colored on a terminal; `--animate` or any animation option animates it, and `--exit` on
an endless animation plays the exit when the program is stopped by SIGINT or SIGTERM, a second signal quitting at once,
so an app can show a face until it is done and let it leave; the grid quits on the first. `--no-animation` undoes the
animation options before it, the last one given winning as with `--color` and `--no-color`, so a wrapper appends it
to an app's flags; `ACCESSIBLE` in the environment, non-empty, keeps every call static whatever the flags, the user's
environment outranking the app's flags, the convention Charm's huh and gum set; color stays `NO_COLOR`'s, the two kept
apart as gh keeps its accessible prompter and colors. Neither reaches the MOTD nor the panels, which run without a
user's environment (2026-10-03). Go finishes a write a signal interrupted, so a frame is never torn. Only `--help`,
`--version`, and `--preview`, the grid, print anything else. A terminal moves text by whole cells and redraws at its
own rate, so beyond about sixty frames a second the clock buys timing accuracy, not visible motion.

The package builds itself: [build](../packages/kaomoji/build) runs in the tools image, which carries Debian's Go next to
nfpm, cross-compiles five static binaries, Linux armv6 for every 32-bit Pi and Linux and macOS arm64 and amd64, packs the
Linux ones from [nfpm.yaml.in](../packages/kaomoji/nfpm.yaml.in) with the architecture substituted, and renders
[bootstrap.sh](../packages/kaomoji/bootstrap.sh) as `kaomoji`, `hero`, `wizard`, and `visitor` with the version, the
character, and the binaries' hashes baked in. The release attaches all of it, created as a draft and published once every
asset is up, so `curl -fsSL https://github.com/bkahlert/pihero/releases/latest/download/hero | bash -s -- --animate`
fetches the binary of that script's own release once, into `~/.cache/kaomoji/<version>/`, checks the hash, and runs it: no
API call, no redirect service, no hosting, and script and binary cannot mismatch. The Debian version `2.1.0~rc.1` was
tagged `v2.1.0-rc.1`, which the script derives; a build between tags has no release and its script no working URL, which
is accepted since only the release workflow publishes scripts. The language is the exception to the on-device-logic rule,
recorded in the Decisions table: a terminal animation needs an instant start and a binary without a runtime, which neither
bash nor Python gives, and Go reaches the Pi 1 and a Mac from one build command.

[kaomoji-gif](../packages/kaomoji/kaomoji-gif) records the command given after `--` with asciinema on a virtual 256-color
terminal and renders the recording with agg: the terminal sized to the picture, the final newline and the cursor trimmed,
and the last frame held for the frames it repeats plus one more, since agg merges identical frames. It stays a bash script
beside the cast, self-contained and Mac-side, since asciinema and agg have no place on a Pi; the pictures are GIFs, not
animated SVG, because SVG text renders with the viewer's fonts and the faces depend on glyphs few machines share.
[packages/kaomoji/README.md](../packages/kaomoji/README.md) shows them, and `make -C packages/kaomoji` builds the Mac
binary through the tools image and re-renders the GIFs whose program or renderer changed; the badge in the repository's
README is a one-off cut with ffmpeg, kept with the logo (2026-09-30). The bash implementation this replaced stays
reachable at the tag `kaomoji-bash`.

**Performance.** The target is a Raspberry Pi 1 at 50 ms per frame. Measured on `busy-screen.local` (Pi 1, the kiosk
browser taking half the CPU, load average 4) with the binary of this change: a static plain hero in 55 ms; the first frame
of an animation after 30 ms plain and 40–65 ms colored; the whole of `--loops 1 --exit`, 2.2 s nominal, on 80 columns in
2.2 s plain and 2.4 s colored, on 200 columns in 2.6 s plain and 3.9 s colored, since the 199 exit frames at 4 ms each
meet the board's floor of about 8 ms per colored write and a wide colored exit stretches there to some 2.5 s; the longest
gap between frames stayed under 95 ms, the slowest entrance interval being 88 ms by design. The grid redraws in about
75 ms on the Pi 1, against 125–160 ms before, and stays a Mac-side tool. Before, in bash, the first frame showed after
0.8–1.2 s plain and 1.6–2 s colored, a cached frame cost 9 ms and a fresh one 25–70 ms, the engine never forked while
animating and batched its `tput` calls to get there, and the grid's startup took 3.5–8 s (2026-10-02). The exit was
halved to eight frame times after that measurement, `--loops 1 --exit` now being 1.8 s nominal; on the Pi 1 the colored
hero's exit frames, 5 ms apart on 80 columns, fall under the board's write floor, so its exit stretches there to about
0.6 s plain and keeps the 2.5 s on 200 columns (2026-10-02, not re-measured).

## Planned packages

Each follows the same pattern: files under `root/`, a render unit ordered before its consumer where a value must end up in a
file another daemon reads, defaults in code, overrides from `/etc/pihero/<feature>.conf`, tests next to it.

- **`pihero-display-hdmi`**: dropped. Trixie runs full KMS, where version 1's `hdmi_group`, `hdmi_mode`, and `hdmi_cvt` are
  ignored; a display with EDID works with the stock configuration, and a panel without one (the HAMTYSAN 7-inch reports no
  EDID and no hotplug) needs a single kernel parameter, `video=HDMI-A-1:800x480M@60e`, which is one `bootconfig add cmdline`
  line in its device file. A package that renders one never-changing parameter from one conffile key is a render unit for a
  device constant.
- **`pihero-bt-pan`**: depends on `bluez`, `bluez-tools`, and `network-manager`; a render unit applies `CLASS` and
  `DISCOVERABLE_TIMEOUT` to `/etc/bluetooth/main.conf`, writes the PIN file from `/etc/pihero/bt-pan.devices`, and ensures a
  NetworkManager bridge `pan0` with `ipv4.method shared` on `CIDR` (default `10.11.10.10/29`), so NetworkManager provides DHCP
  and NAT and no dnsmasq or ifupdown configuration exists. `bt-network --server nap pan0` and `bt-agent` run as units; listed
  devices are trusted through `bluetoothctl` before the server starts. Tier 2 can test the adapter with `hci_vhci` and `btvirt`
  from `bluez-test-tools`; the data path needs hardware.

## Configuration contract

- **One file describes a device.** `devices/<host>/user-data` is written in the repository and copied onto the boot partition;
  `network-config` holds Wi-Fi. Real device files are gitignored; `devices/sample/` is the committed reference. The keys and
  the reasons behind them are in [devices/README.md](../devices/README.md).
- **Defaults and overrides never share a file.** Packages ship nothing under `/etc/pihero/`; defaults live in the script or
  unit. A device writes `/etc/pihero/<feature>.conf` as `KEY=VALUE` through `write_files`, and the unit reads it with
  `EnvironmentFile=-`. No config library on the device, and no dpkg conffile prompt, which would otherwise fire because
  cloud-init writes files before it installs packages.
- **Render at boot.** Where a value must end up in a file another daemon reads, a oneshot render unit ordered `Before=` the
  consumer writes it on every boot. Editing a conffile and rebooting is therefore a complete change procedure, and every
  renderer is a pure function the tests call with environment variables.
- **Identity.** Hostname from cloud-init; the pretty hostname from one `runcmd` line, read back from `hostnamectl` so
  `/etc/machine-info` stays the single source; the board model from the device tree; the USB gadget's name and subnet
  from `/etc/pihero/usb-gadget.conf`.
- **Secrets.** The boot partition is unencrypted FAT. Public keys and password hashes are fine there; a Wi-Fi passphrase or a
  Tailscale auth key is exposed to anyone holding the card. Accepted for devices under physical control; Tailscale keys are
  single-use with an expiry.
- **Day two.** cloud-init runs once per card. Changes are `apt upgrade`, a conffile edit plus reboot, or a reflash.
- **Validation.** `cloud-init schema` runs against every committed device file in tier 0.

## Operations

- **Failures are loud.** Renderers exit non-zero when they cannot do their job, consumers are ordered after them,
  `systemctl --failed` is the diagnostic, and the MOTD surfaces it.
- **Reboots are requested, never taken.** Postinst touches `/run/reboot-required` and `/run/reboot-required.pkgs`; the first
  boot reboots through cloud-init's `power_state` on that condition, a running device reboots when its owner decides.
- **Removal is symmetric.** `prerm` disables and stops units, `postrm purge` deletes rendered files and reverts boot config
  lines. Tier 1 asserts install, remove, and nothing left behind.
- **Upgrades never prompt**, because no package ships a file under `/etc/pihero/` and rendered files are regenerated at boot.
- **Rollback is a version pin.** The repository keeps every published `.deb`: `apt install pihero=2.0.0` rolls back,
  `apt-mark hold` freezes.
- **Backup is a card image.** `make backup` reads the whole card into `backups/<host>-<date>.img.xz` with a sidecar naming
  size and sha256; `make restore` refuses a smaller card before writing, verifies by reading back, and points at
  `raspi-config --expand-rootfs` on a larger one. Shrinking the image so a nominally equal card fits is the planned follow-up.
- **A new card forgets Ghostty's cache.** Ghostty's `ssh-terminfo` integration installs its terminfo once per `user@host`,
  caches that forever, and on a cache hit sends `TERM=xterm-ghostty`; a card flashed or restored under a known name would
  get the `TERM` without the terminfo and lose colours. `make flash` and `make restore` therefore drop the host from
  `ghostty +ssh-cache`, finding the CLI in the app bundle since it is on `PATH` only inside a Ghostty shell.
- **Release is a tag.** `make release VERSION=X.Y.Z` runs tiers 0 to 2 locally and tags only on green; pushing the tag makes
  CI build every package at that version, regenerate the flat repository with `apt-ftparchive`, sign it with the key in the
  `APT_SIGNING_KEY` secret, push to `gh-pages`, and create the GitHub release with the `.deb` files. Pre-release tags such as
  `v2.1.0-rc.1` publish as `2.1.0~rc.1`. One signing key exists; its public half is embedded in device files, so a device
  trusts nothing else, and rotation is a manual procedure.
  The published release is then proven on hardware: the two checkpoints, a 64-bit Zero 2 W with the gadget and a 32-bit
  Zero on a USB Ethernet hub, are reflashed from device directories a gitignored `.env` names, and `make checkpoint` runs
  the ssh tier on each as `pi@<name>.local`, the directory named after its board, accepting the reflashed board's new host
  key. One board per image; the Zero never takes the gadget.
- **Development loop.** `make deploy TARGET=pi@host` builds, asks the device which of the packages it has, and
  reinstalls those of its architecture over SSH with `apt install ./pkg.deb`, skipping the repository. A package the device never had is not
  added: its postinst would run for a board it was not meant for, as the gadget's once did on a Model B. A device without
  any of the packages is flashed, not deployed to. The ssh tier asks the same question and skips the tests of the packages the device
  lacks, so a board with a subset is green.

## Applications

Applications live in their own repositories as their own packages and follow [app-conventions.md](app-conventions.md): a
dedicated system user, `Restart=always`, `MemoryMax=`, hardware access through groups, overrides in `/etc/<app>/<app>.conf`.
Their tests depend on `pihero-testkit` pinned to a tag and reuse its tiers, with a tier-2 device file that adds the app's apt
source, `http://10.0.2.2:8000/` with `Trusted: yes`, to a copy of the all-features device; the harness serves that
repository on a free port and rewrites the URL's port when it stages the file, so tier-2 runs of several repositories share
a Mac. A device file then names the app's repository and packages next to Pi Hero's.

## Out of scope

Gadget functions beyond Ethernet, an automated hardware tier (power cycling, unattended flashing), fleet tooling, monitoring,
remote logging, and re-provisioning a running device from a changed device file.
