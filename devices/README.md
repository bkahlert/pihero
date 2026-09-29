# Devices

One directory per device with the cloud-init files that go onto the boot partition after flashing: `user-data` (required),
`network-config` (Wi-Fi, optional), `meta-data` (optional). Directories other than [`sample/`](sample) are gitignored; keep
them here or in a private repository. Everything an operator does with a device is on this page; the Mac needs
[Homebrew](https://brew.sh/) and `brew bundle` first.

## Describe a device

### user-data

[sample/user-data](sample/user-data) is a complete device. Its keys, top to bottom:

| Key                               | Sets                                                                                                                                    | Notes                                                                                                                                                   |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `# image:` (header comment)       | The image `make flash` writes: `raspios_lite_arm64` for the Zero 2 W and up, `raspios_lite_armhf` for the Zero W and other ARMv6 boards | 64-bit when absent; the names are the tables of [images.lock](../testkit/src/pihero_testkit/images.lock)                                                |
| `hostname`, `timezone`, `users`   | Hostname, time zone, the `pi` user with your public key                                                                                 | Plain cloud-init. Keep `lock_passwd: true` and `ssh_pwauth: false`; the key is the only way in                                                          |
| `rpi: interfaces:`                | SPI, I²C, and the GPIO UART                                                                                                             | Changing them costs the first of the two provisioning reboots                                                                                           |
| `bootcmd`                         | Orders cloud-init's final stage after the clock is synced                                                                               | Without it apt rejects the repository signatures on a fresh card; see [docs/raspberry-pi-os.md](../docs/raspberry-pi-os.md)                             |
| `packages`                        | What to install; add applications here                                                                                                  | `package_update: true` refreshes the index first                                                                                                        |
| `write_files`                     | The signed apt source, `/etc/pihero/device-info.conf` (`MODEL`, the Finder icon), `/etc/pihero/usb-gadget.conf` (`PRODUCT`, `CIDR`)     | The key is inline, so the device trusts nothing else                                                                                                    |
| `runcmd`                          | The pretty name the Pi is advertised under, then restarts the Avahi renderer                                                            | Holds the commented Tailscale lines: install, join with an auth key, and for an exit node forwarding plus `--advertise-exit-node`                       |
| `power_state`                     | Reboots when a package left `/run/reboot-required` behind                                                                               | `pihero-usb-gadget` does on its first install                                                                                                           |

The reasons behind the workarounds are in [docs/raspberry-pi-os.md](../docs/raspberry-pi-os.md).

### network-config

[sample/network-config](sample/network-config) is netplan as Imager writes it: one access point with its passphrase, DHCP,
`optional: true`, and `regulatory-domain`. `make flash` copies the domain onto the kernel command line; without it the first
boot has no Wi-Fi.

### The Finder icon

`MODEL` in `device-info.conf` selects the icon. `AirPort4` is the default: recognised everywhere and a small network device
rather than a computer. Other good choices:

| Model     |                                             `AirPort4`                                             |                                             `AirPort5`                                             |                                          `AirPort6`                                          |                                         `Macmini8,1`                                         |                                         `Macmini9,1`                                         |                                             `MacPro6,1`                                             |                                    `MacPro5,1`                                    |                         `MacPro7,1`<br/>`@ECOLOR=`<br/>`225,225,223`                        |                                   `MacPro7,1`<br/>`@ECOLOR=`<br/>`226,226,224`                                  |                                    `Xserve3,1`                                    |
| --------- | :------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------: | :------------------------------------------------------------------------------------------: | :-------------------------------------------------------------------------------------------------: | :-------------------------------------------------------------------------------: | :-----------------------------------------------------------------------------------------: | :-------------------------------------------------------------------------------------------------------------: | :-------------------------------------------------------------------------------: |
| Kind      |                                                Mac                                                 |                                          AirPort Extreme                                           |                                         Time Capsule                                         |                                             Mac                                              |                                             Mac                                              |                                                 Mac                                                 |                                        Mac                                        |                                             Mac                                             |                                                       Mac                                                       |                                        Mac                                        |
| Icon      |           ![com.apple.airport-express.png](../docs/models/com.apple.airport-express.png)           |           ![com.apple.airport-extreme.png](../docs/models/com.apple.airport-extreme.png)           |           ![com.apple.time-capsule.png](../docs/models/com.apple.time-capsule.png)           |           ![com.apple.macmini-2018.png](../docs/models/com.apple.macmini-2018.png)           |           ![com.apple.macmini-2020.png](../docs/models/com.apple.macmini-2020.png)           |            ![com.apple.macpro-cylinder.png](../docs/models/com.apple.macpro-cylinder.png)           |            ![com.apple.macpro.png](../docs/models/com.apple.macpro.png)           |            ![com.apple.macpro-2019.png](../docs/models/com.apple.macpro-2019.png)           |            ![com.apple.macpro-2019-rackmount.png](../docs/models/com.apple.macpro-2019-rackmount.png)           |            ![com.apple.xserve.png](../docs/models/com.apple.xserve.png)           |
| Sidebar   |   ![com.apple.airport-express-sidebar.png](../docs/models/com.apple.airport-express-sidebar.png)   |   ![com.apple.airport-extreme-sidebar.png](../docs/models/com.apple.airport-extreme-sidebar.png)   |   ![com.apple.time-capsule-sidebar.png](../docs/models/com.apple.time-capsule-sidebar.png)   |   ![com.apple.macmini-2018-sidebar.png](../docs/models/com.apple.macmini-2018-sidebar.png)   |   ![com.apple.macmini-2020-sidebar.png](../docs/models/com.apple.macmini-2020-sidebar.png)   |    ![com.apple.macpro-cylinder-sidebar.png](../docs/models/com.apple.macpro-cylinder-sidebar.png)   |    ![com.apple.macpro-sidebar.png](../docs/models/com.apple.macpro-sidebar.png)   |    ![com.apple.macpro-2019-sidebar.png](../docs/models/com.apple.macpro-2019-sidebar.png)   |    ![com.apple.macpro-2019-rackmount-sidebar.png](../docs/models/com.apple.macpro-2019-rackmount-sidebar.png)   |    ![com.apple.xserve-sidebar.png](../docs/models/com.apple.xserve-sidebar.png)   |

Changing it later: edit `/etc/pihero/device-info.conf` on the Pi and `systemctl restart pihero-avahi-render.service`.

### Ethernet over USB

`pihero-usb-gadget` turns on Raspberry Pi's `rpi-usb-gadget` and loads a CDC ECM gadget with MACs derived from the board
serial, so a Mac sees the same device on every boot. `/etc/pihero/usb-gadget.conf` takes two optional keys:

| Key         | Default                                                   | Notes                                                                                                            |
| ----------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `PRODUCT`   | The board model, such as `Raspberry Pi Zero 2 W Rev 1.0`  | The name the host lists the gadget under; double-quoted when it contains spaces. The sample uses the pretty name |
| `CIDR`      | Upstream's `10.12.194.1/28`                               | The address the Pi serves to the host                                                                            |

Changing them later: edit the file on the Pi and reboot. `rpi-usb-gadget` supports the Zero, Zero W, Zero 2 W, 3A+, 4B, 5,
500, and Compute Modules 0 and 5; any other board refuses the package on purpose, because peripheral mode would take the
board's only USB controller away from its USB ports and Ethernet. Windows has no driver for CDC ECM;
[docs/raspberry-pi-os.md](../docs/raspberry-pi-os.md) says why upstream's `g_ether` is not used and how macOS names the gadget.

## Flash

Find the card with `diskutil list external`, then:

    make flash DEVICE=<host> DISK=disk9

This

1. writes the pinned Raspberry Pi OS Lite image the device file names,
2. reads it back to verify,
3. copies the device files onto the boot partition,
4. puts the Wi-Fi regulatory domain on the kernel command line,
5. ejects the card.

macOS asks once for authorization; the card takes about two minutes. Raspberry Pi Imager works too: set the Wi-Fi country
in its customisation and nothing else, then copy `user-data` and `network-config` to `/Volumes/bootfs/` before ejecting.

## First boot

Provisioning takes about six minutes and reboots twice, once for the interface settings and once for the USB gadget. Then
`ssh pi@<host>.local` greets you with the MOTD, the Pi is in Finder with its icon, and a Mac on the USB cable has an address
from it. A display shows `Failed to start userconfig.service` once and re-prints the login prompt when an address changes;
both are Raspberry Pi OS behaviour.

### If the Pi does not show up

1. After ten minutes, connect over USB (`ssh pi@10.10.10.10` with the sample's subnet) or Wi-Fi and read
   `/var/log/cloud-init-output.log`, then `cloud-init status --long` and `journalctl -b -u NetworkManager`.
2. With no way in, put the card back into the Mac: `/Volumes/bootfs` holds `cmdline.txt` and `config.txt`.
3. The root partition can be read with `debugfs -c` in the tools container from a dump; see
   [docs/raspberry-pi-os.md](../docs/raspberry-pi-os.md).

## Change a device

cloud-init runs once per card, so a changed device file means a reflash. Small things are done live on the Pi and survive
updates:

- the Finder icon: `/etc/pihero/device-info.conf`, then `systemctl restart pihero-avahi-render.service`
- the gadget's name and subnet: `/etc/pihero/usb-gadget.conf`, then a reboot
- network settings: `nmcli`
- boot settings: `/usr/lib/pihero/bootconfig`

## Update a device

```shell
ssh pi@mypi.local sudo apt update '&&' sudo apt upgrade
```

The repository is signed; the device trusts only the key embedded in its device file. Reboot when the MOTD says so.

## Back up a device

Before a risky change, or once a device holds state its device file cannot recreate, image its card. Power the Pi off, put the
card into the Mac, and:

```shell
make backup                       # asks which card; the image is named after the Pi and the day
make restore                      # asks which image and which card, confirms, writes, verifies, ejects
```

Images land in `backups/<hostname>-<date>.img.xz`, gitignored, next to a `.toml` with the size and checksum a restore checks
first. The hostname comes from the card's `user-data`; `NAME=` overrides it, and `DISK=` and `IMAGE=` skip the questions; a
restore given both writes without asking.
A 16 GB card took six minutes to back up and nineteen to restore, the card's own write speed setting the latter; a 32 GB card
takes about twice that. Restore needs a card at least as large as the one imaged, and a nominally equal card from another
maker can be a few megabytes short, so when replacing a card buy the next size up. On a larger card the root filesystem keeps
its old size until `sudo raspi-config --expand-rootfs` and a reboot.

## Cards from before pihero-usb-gadget

A card provisioned before `pihero-usb-gadget` existed carries its own `usb-gadget.service` and `g_cdc.conf` from the old
sample; they would race the package's unit for the module. Reflash it, or remove them before installing the package and
reboot afterwards:

    sudo systemctl disable --now usb-gadget.service
    sudo rm /etc/systemd/system/usb-gadget.service /etc/modprobe.d/g_cdc.conf
    sudo systemctl daemon-reload
