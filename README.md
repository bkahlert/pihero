# Pi Hero <img src="assets/hero-badge.gif" alt="Pi Hero kaomoji, hovering" height="20"> [![CI](https://github.com/bkahlert/pihero/actions/workflows/ci.yml/badge.svg)](https://github.com/bkahlert/pihero/actions/workflows/ci.yml) [![License](https://img.shields.io/github/license/bkahlert/pihero?color=29ABE2&label=License)](https://github.com/bkahlert/pihero/blob/main/LICENSE) [![Buy Me A Coffee](https://img.shields.io/static/v1?label=&message=%E2%98%95%20Buy%20Me%20A%20Coffee&color=FFDD00)](https://www.buymeacoffee.com/bkahlert)

![Pi Hero Banner](assets%2Fpihero-banner.svg)

## About

**Pi Hero** makes your [Raspberry Pi](https://www.raspberrypi.com/) discoverable, reachable, and pleasant to use.

Every feature is a Debian package from a signed apt repository, and one [cloud-init](https://cloudinit.readthedocs.io/) file
on the boot partition describes a device. Flash a card, boot, and the Pi installs its packages and shows up in your network:
no control machine, no playbook.

| Package             | What it does                                                                                                                                                    |
|---------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `pihero`            | The MOTD lists installed features, failed units, pending reboots, and the USB address; `bootconfig` edits the boot files safely                                 |
| `pihero-avahi`      | The Pi appears in Finder's network browser with an icon and its device information, announced as an SMB server because that is what Finder lists; SSH is advertised too |
| `pihero-usb-gadget` | Ethernet over USB on top of Raspberry Pi's `rpi-usb-gadget`: a Mac on the cable gets an address from the Pi and lists the interface under the board's name      |

| [![network browser](docs%2Fnetwork-browser.png) Pis in the network browser](./docs/network-browser.png) | [![network info foo](docs%2Fnetwork-info-foo.png) device information](./docs/network-info-foo.png) | [![device info bar](docs%2Fdevice-info-bar.png) device information with a custom model](./docs/device-info-bar.png) |
|---------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|

Planned, one package each: Bluetooth PAN, HDMI modes. Pi Hero 1, the Ansible playbook, is frozen
at tag [`pihero-ansible`](https://github.com/bkahlert/pihero/tree/pihero-ansible); [docs/pihero-1.md](docs/pihero-1.md) says
what became of each of its features.

## Quick start

You need a Mac with [Homebrew](https://brew.sh/), a Raspberry Pi (Zero W and up), and an SD card.

1. **Describe the device.** Copy the sample and edit it: hostname, your SSH public key, the pretty name, the Finder icon, the
   USB gadget's name, and your Wi-Fi in `network-config`; a Zero W or another ARMv6 board takes `# image: raspios_lite_armhf`
   in the header. The sample installs `pihero`, `pihero-avahi`, and
   `pihero-usb-gadget`; device directories other than `sample/` are gitignored.
   ```shell
   mkdir devices/mypi && cp devices/sample/user-data devices/sample/network-config devices/mypi/
   ```
2. **Flash.** Find the card with `diskutil list external`, then:
   ```shell
   brew bundle
   make flash DEVICE=mypi DISK=disk9
   ```
   Two minutes: the image is written, verified, and completed with your files. Raspberry Pi Imager works as well.
3. **Boot.** Six minutes and two reboots later `ssh pi@mypi.local` greets you with the MOTD, the Pi is in Finder, and a Mac on
   the USB cable gets an address from the gadget `pihero-usb-gadget` brought up, listed under the name you gave it.

Every key of the device file, the icon choices, and what to do if the Pi does not show up are in
[devices/README.md](devices/README.md). Updating a device is `sudo apt upgrade` on the Pi; changing it is a reflash.

## The apt repository

Releases are published to [bkahlert.github.io/pihero](https://bkahlert.github.io/pihero/), a flat repository signed with the
key in [docs/pihero-apt.asc](docs/pihero-apt.asc) (fingerprint `DE60 9D7F F5BE 430D AC8C C807 081F 70E6 A077 DF7A`). The
device file embeds that key, so a device trusts nothing else.

## Development

Everything runs on the Mac; a Raspberry Pi is optional.

```shell
brew bundle        # qemu, podman, uv
make doctor        # checks the tooling
make test          # unit tests, static checks, and install tests in systemd containers
make test-all      # plus a QEMU VM that boots Raspberry Pi OS from a device file
```

A feature is one directory under [packages/](packages/); the harness lives in [testkit/](testkit/). The day-to-day is in
[docs/workflows.md](docs/workflows.md), the test tiers in [docs/testing.md](docs/testing.md), the decisions in
[docs/design.md](docs/design.md), the Raspberry Pi OS quirks the device file works around in
[docs/raspberry-pi-os.md](docs/raspberry-pi-os.md), and the conventions for applications built on top in
[docs/app-conventions.md](docs/app-conventions.md).

## Contributing

Want to contribute? Awesome! The most basic way to show your support is to star the project, or to raise issues. You
can also support this project by making
a [PayPal donation](https://www.paypal.me/bkahlert) to ensure this journey continues indefinitely!

Thanks again for your support, it is much appreciated! :pray:

## License

MIT. See [LICENSE](LICENSE) for more details.
