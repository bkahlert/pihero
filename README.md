# Pi Hero <img src="assets/hero-badge.gif" alt="Pi Hero kaomoji, hovering" height="20"> [![CI](https://github.com/bkahlert/pihero/actions/workflows/ci.yml/badge.svg)](https://github.com/bkahlert/pihero/actions/workflows/ci.yml) [![License](https://img.shields.io/github/license/bkahlert/pihero?color=29ABE2&label=License)](https://github.com/bkahlert/pihero/blob/master/LICENSE) [![Buy Me A Unicorn](https://img.shields.io/static/v1?label=&message=Buy%20Me%20A%20Unicorn&color=c21f73)](https://www.buymeacoffee.com/bkahlert)

![Pi Hero Banner](assets%2Fpihero-banner.svg)

## About

**Pi Hero** makes your [Raspberry Pi](https://www.raspberrypi.com/) discoverable, reachable, and pleasant to use.

Version 2 ships every feature as a Debian package from a signed apt repository and describes a device with one
[cloud-init](https://cloudinit.readthedocs.io/) file on the boot partition. There is no control machine and no playbook:
flash a card, copy the device file, boot. The Pi installs its packages and shows up in your network.

| Package        | What it does                                                                                                                                                                            |
|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `pihero`       | Core: `bootconfig` edits `config.txt` and `cmdline.txt` and flags a reboot, the MOTD lists installed Pi Hero packages, failed units, pending reboots, and the USB address; hardware watchdog set to 15 s |
| `pihero-avahi` | The Pi appears in Finder's network browser with an icon and its device information; SSH is advertised too                                                                              |

Planned, one package each: `pihero-splash`, `pihero-smb`, `pihero-bt-pan`, `pihero-display-hdmi`. The design is in
[docs/superpowers/specs/2026-09-27-pihero-packages-design.md](docs/superpowers/specs/2026-09-27-pihero-packages-design.md).

Pi Hero 1, the Ansible playbook, is frozen at tag [`pihero-ansible`](https://github.com/bkahlert/pihero/tree/pihero-ansible) and
documented in [docs/ansible.md](docs/ansible.md).

| [![network browser](docs%2Fnetwork-browser.png) Pis in the network browser](./docs/network-browser.png) | [![network info foo](docs%2Fnetwork-info-foo.png) device information](./docs/network-info-foo.png) | [![device info bar](docs%2Fdevice-info-bar.png) device information with a custom model](./docs/device-info-bar.png) |
|---------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|

## Quick start

You need a Mac with [Homebrew](https://brew.sh/), a Raspberry Pi that runs the 64-bit Raspberry Pi OS (Zero 2 W and up), and an SD card.

1. **Describe the device.** Copy the sample and edit it: hostname, your SSH public key, the pretty name, the model, and Wi-Fi in
   `network-config`. Device directories other than `sample/` are gitignored.
   ```shell
   mkdir devices/mypi && cp devices/sample/user-data devices/sample/network-config devices/mypi/
   ```
2. **Flash.** Find the card with `diskutil list external`, then:
   ```shell
   brew bundle
   make flash DEVICE=mypi DISK=disk9
   ```
   This writes the pinned Raspberry Pi OS Lite (Trixie) image, reads it back to verify, copies the device files onto the boot
   partition, and ejects the card. macOS asks once for authorization. Raspberry Pi Imager works as well: decline its
   customisation and copy the two files to `/Volumes/bootfs/` yourself.
3. **Boot.** cloud-init installs the packages from the Pi Hero repository and reboots once if a package asked for it, plus once
   more when the USB gadget is enabled. After a few minutes `ssh pi@mypi.local` greets you with the MOTD, and the Pi is in Finder.

## The device file

[devices/sample/user-data](devices/sample/user-data) is the complete description of a device:

- `hostname`, `users` with your key, `timezone`, and `ssh_pwauth: false`: plain cloud-init.
- `rpi:` enables Raspberry Pi specifics: `enable_usb_gadget: true` for Ethernet over USB, `interfaces:` for SPI, I²C, and serial.
- `packages:` lists the Pi Hero packages to install; `write_files` adds the signed apt source and `/etc/pihero/device-info.conf`.
- `runcmd` sets the pretty hostname the Pi is advertised under, restarts the Avahi render unit, and adjusts the USB subnet.
- `power_state` reboots when a package left `/run/reboot-required` behind.

Wi-Fi goes into [network-config](devices/sample/network-config) next to it. Changing a device means editing its file and
reflashing; updating means `sudo apt upgrade` on the Pi. See [devices/README.md](devices/README.md).

The `MODEL` in `device-info.conf` selects the icon Finder shows. `AirPort4` is the default: recognised everywhere, looks like a small
network device rather than a computer. Other good choices:

| Model   |                                           `AirPort4`                                            |                                           `AirPort5`                                            |                                        `AirPort6`                                         |                                       `Macmini8,1`                                        |                                       `Macmini9,1`                                        |                                           `MacPro6,1`                                           |                                  `MacPro5,1`                                  |                      `MacPro7,1`<br/>`@ECOLOR=`<br/>`225,225,223`                       |                                `MacPro7,1`<br/>`@ECOLOR=`<br/>`226,226,224`                                 |                                  `Xserve3,1`                                  |
|---------|:-----------------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------:|:---------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------:|
| Kind    |                                               Mac                                               |                                         AirPort Extreme                                         |                                       Time Capsule                                        |                                            Mac                                            |                                            Mac                                            |                                               Mac                                               |                                      Mac                                      |                                           Mac                                           |                                                     Mac                                                     |                                      Mac                                      |
| Icon    |         ![com.apple.airport-express.png](docs%2Fmodels%2Fcom.apple.airport-express.png)         |         ![com.apple.airport-extreme.png](docs%2Fmodels%2Fcom.apple.airport-extreme.png)         |         ![com.apple.time-capsule.png](docs%2Fmodels%2Fcom.apple.time-capsule.png)         |         ![com.apple.macmini-2018.png](docs%2Fmodels%2Fcom.apple.macmini-2018.png)         |         ![com.apple.macmini-2020.png](docs%2Fmodels%2Fcom.apple.macmini-2020.png)         |         ![com.apple.macpro-cylinder.png](docs%2Fmodels%2Fcom.apple.macpro-cylinder.png)         |         ![com.apple.macpro.png](docs%2Fmodels%2Fcom.apple.macpro.png)         |         ![com.apple.macpro-2019.png](docs%2Fmodels%2Fcom.apple.macpro-2019.png)         |         ![com.apple.macpro-2019-rackmount.png](docs%2Fmodels%2Fcom.apple.macpro-2019-rackmount.png)         |         ![com.apple.xserve.png](docs%2Fmodels%2Fcom.apple.xserve.png)         |
| Sidebar | ![com.apple.airport-express-sidebar.png](docs%2Fmodels%2Fcom.apple.airport-express-sidebar.png) | ![com.apple.airport-extreme-sidebar.png](docs%2Fmodels%2Fcom.apple.airport-extreme-sidebar.png) | ![com.apple.time-capsule-sidebar.png](docs%2Fmodels%2Fcom.apple.time-capsule-sidebar.png) | ![com.apple.macmini-2018-sidebar.png](docs%2Fmodels%2Fcom.apple.macmini-2018-sidebar.png) | ![com.apple.macmini-2020-sidebar.png](docs%2Fmodels%2Fcom.apple.macmini-2020-sidebar.png) | ![com.apple.macpro-cylinder-sidebar.png](docs%2Fmodels%2Fcom.apple.macpro-cylinder-sidebar.png) | ![com.apple.macpro-sidebar.png](docs%2Fmodels%2Fcom.apple.macpro-sidebar.png) | ![com.apple.macpro-2019-sidebar.png](docs%2Fmodels%2Fcom.apple.macpro-2019-sidebar.png) | ![com.apple.macpro-2019-rackmount-sidebar.png](docs%2Fmodels%2Fcom.apple.macpro-2019-rackmount-sidebar.png) | ![com.apple.xserve-sidebar.png](docs%2Fmodels%2Fcom.apple.xserve-sidebar.png) |

## The apt repository

Releases are published to `https://bkahlert.github.io/pihero/apt`, a flat repository signed with the key in
[docs/pihero-apt.asc](docs/pihero-apt.asc) (fingerprint `DE60 9D7F F5BE 430D AC8C C807 081F 70E6 A077 DF7A`). The sample device
file embeds that key, so a device trusts nothing else. Pre-release tags such as `v2.0.0-rc.1` publish as `2.0.0~rc.1` and are
marked pre-release on GitHub.

## Development

Everything runs on the Mac; no Raspberry Pi is needed until the last step.

```shell
brew bundle        # qemu, podman, uv
make doctor        # checks the tooling
make build         # all packages into dist/
make test          # tiers 0 and 1
make test-all      # tiers 0 to 2
```

| Tier | What runs                                                                                    | Command                                                                  |
|------|----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| 0    | Unit tests of the scripts and the testkit, static checks of every package                   | `make test-tier0`                                                        |
| 1    | Packages installed, removed, and purged in a systemd container, `arm64` and `arm/v7`        | `make test-tier1 PLATFORM=linux/arm/v7`                                  |
| 2    | A QEMU VM boots Raspberry Pi OS with a device file and provisions itself from a local repo  | `make test-tier2`, `make vm` keeps it running                            |
| ssh  | The `installed` tests against a real device, mutating tests skipped                          | `uv run pytest -m installed --target=ssh --target-uri=pi@mypi.local`    |

`make deploy TARGET=pi@mypi.local` installs the freshly built packages on a device without going through the repository.

A feature is one directory under [packages/](packages/): `nfpm.yaml`, the files under `root/`, maintainer script fragments under
`scripts/`, the units to enable in `units.txt`, and its `tests/`. The harness lives in [testkit/](testkit/); conventions for
applications built on top are in [docs/app-conventions.md](docs/app-conventions.md). CI runs tiers 0 and 1 on every push, tier 2
weekly, and the release workflow builds, signs, and publishes on every `v*` tag.

## Contributing

Want to contribute? Awesome! The most basic way to show your support is to star the project, or to raise issues. You
can also support this project by making
a [PayPal donation](https://www.paypal.me/bkahlert) to ensure this journey continues indefinitely!

Thanks again for your support, it is much appreciated! :pray:

## License

MIT. See [LICENSE](LICENSE) for more details.
