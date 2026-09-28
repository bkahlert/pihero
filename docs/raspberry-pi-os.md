# Raspberry Pi OS and cloud-init

Field notes from the Raspberry Pi OS Lite 64-bit (Trixie) image of 2026-09-15 on a Raspberry Pi Zero 2 W, on Wi-Fi and on the
USB port of a Mac running macOS 27. Each note names the symptom, the cause, and what the packages, the
[sample device file](../devices/sample/user-data), or `make flash` do about it. None of these is a Pi Hero bug; all of them cost a first boot to find.

## How the image runs cloud-init

The stock boot partition already carries `user-data`, `network-config`, and `meta-data`; `meta-data` sets `dsmode: local`, and
`/etc/cloud/cloud.cfg.d/99_raspberry-pi.cfg` seeds NoCloud from `/boot/firmware`. Consequences:

- **Init modules run before the network.** With the datasource in local mode, cloud-init applies `bootcmd`, `write_files`,
  `users`, and `ssh` in `cloud-init-local.service`, before NetworkManager starts. Nothing in `bootcmd` can wait for the network.
- **`runcmd` is written in the config stage but executed in the final stage**, after the packages are installed; Raspberry Pi
  OS's `cloud.cfg` lists `runcmd` under `cloud_config_modules` and `package_update_upgrade_install` under `cloud_final_modules`.
- **`apt:` is ignored.** `apt_configure` is not scheduled, so an `apt:` block does nothing. The pihero source is a `write_files`
  entry writing a deb822 `.sources` file with the key inline.
- **`cc_netplan_nm_patch` is missing.** `cloud.cfg` schedules a module the package does not ship. Every boot ends
  `degraded done` with that warning; harmless. The tier-2 root filesystem drops it from the list so the VM reports `done`.
- **A reboot hides failures.** cloud-init re-runs its stages on the next boot, most modules skip as already done, and
  `cloud-init status` shows `done` with `errors: []` even when the package install failed the boot before. Read
  `/var/log/cloud-init-output.log` before believing the status.

## First boot

- **No Wi-Fi without the regulatory domain on the kernel command line.** Raspberry Pi's patched netplan writes
  `cfg80211.ieee80211_regdom=` to `cmdline.txt` during the first boot, too late for that boot: NetworkManager-wait-online gives
  up, the final stage runs without a network, apt installs nothing. With the domain already there, wlan0 joins at about 70 s
  and the final stage waits for it. Imager writes it at flash time; `make flash` does the same from `network-config`.
- **The clock starts at the image build date.** Trixie ships no fake-hwclock; systemd restores the time systemd-timesyncd
  last saved, which on a fresh card is the build date. cloud-init's final stage runs `apt-get update` as soon as the network
  is up, before the clock is stepped, and sqv rejects every `InRelease` signature as "not live yet": the repositories count as
  unsigned, nothing installs, and the reboot hides it. The device file's `bootcmd` orders `cloud-final.service` after
  `time-sync.target` and enables `systemd-time-wait-sync` with a five-minute cap. Re-provisioning the same card never shows
  this, because its saved clock is recent; only a fresh card does.
- **`rpi: enable_usb_gadget: true` never works on a fresh card.** cloud-init runs `rpi-usb-gadget on -f` with a 15 s timeout,
  the script itself waits 5 s and 10 s for a `usb0` that only exists after a reboot, the module aborts, the rest of `rpi:` is
  skipped, and no reboot is requested. `pihero-usb-gadget`'s postinst runs `rpi-usb-gadget on -f`, which has no timeout, and
  requests the reboot `power_state` takes. In the tier-2 VM the postinst skips it: the script refuses a device tree that is
  not a Raspberry Pi.
- **Two reboots, about six minutes.** First boot 2.5 min (Wi-Fi at 70 s, `rpi: interfaces:` applied, reboot), second boot
  2 min (time sync, apt, gadget, reboot), third boot done after 47 s. Re-provisioning a card with `cloud-init clean --logs`
  takes about 4.5 min. SSH answers 70 to 90 s after power-on on any boot.
- **Console messages that are not errors.** `Failed to start userconfig.service` appears once: cloud-init creates the user
  through `userconf-pi` and masks the dialog unit while it is starting. The login prompt is printed again whenever an address
  changes, with a different IPv6 address each time: `/etc/issue.d/IP.issue` uses agetty's `\4 \6` escapes. Console blanking is
  off by default. An HDMI display attached with a properly seated cable shows the console with the stock configuration.

## USB Ethernet with macOS

- **`g_ether` passes no frames to macOS 27.** The host binds the module's RNDIS configuration, which macOS no longer drives.
  `g_cdc` (CDC ECM plus an ACM serial port the Mac sees as `/dev/tty.usbmodem*`) works on macOS and Linux; Windows has no
  inbox ECM driver and would need RNDIS or, later, a configfs NCM gadget. `pihero-usb-gadget` blacklists `g_ether`, which
  `systemd-modules-load` honours, so `rpi-usb-gadget`'s on/off marker stays as it is, and loads `g_cdc` from its own unit.
- **macOS asks for DHCP only while the link comes up**, then settles for a self-assigned address. `g_ether` loaded at 10 s,
  NetworkManager served DHCP at 25 s. The unit is ordered `After=NetworkManager.service`.
- **macOS creates a network service per host MAC**, and `g_cdc` picks random ones. The unit derives both MACs from the board
  serial and names the gadget after the board, `Raspberry Pi Zero 2 W Rev 1.0`, so several Pis stay apart in a Mac's network
  list.
- The Raspberry Pi kernel has no `g_ncm` module, only `usb_f_ncm` for configfs.

## Plymouth, tried and dropped

Version 1's splash was built as `pihero-splash`, verified on a Zero 2 W, and dropped on 2026-09-28; these are the facts behind
the decision in [design.md](design.md).

- **Two kernels, two initrds.** The 64-bit image installs `linux-image-rpi-v8` and `linux-image-rpi-2712`; `update-initramfs`
  builds `/boot/initrd.img-<version>` for each, and `raspi-firmware`'s hook copies them to `/boot/firmware/initramfs8` and
  `initramfs_2712`. `update_initramfs=yes`, not `all`, so a bare `update-initramfs -u` covers the running kernel only, and from
  a maintainer script it defers to the dpkg trigger; a theme package has to run `plymouth-set-default-theme -R`, which is
  `update-initramfs -u -k all`.
- **Plymouth comes from Debian**, 24.004.60-5 in Trixie; the Raspberry Pi archive carries none. Installing `plymouth`,
  `plymouth-themes`, and the theme rebuilt both initrds three times, 64 s, 55 s, and 76 s in dpkg's log on a Zero 2 W, and
  doubled the emulated tier-2 run to 50 minutes. `plymouthd.conf` is Plymouth's conffile, so a theme package that sets `Theme=`
  has to hand the file back byte for byte on purge.
- **The quiet boot hides the console.** `quiet loglevel=3 systemd.show_status=auto` and the splash itself cover the boot
  messages until `plymouth-quit`, 36 s into the boot on the checkpoint. A board that does not come up shows a spinner instead of
  the unit that failed. Console blanking is off by default, so version 1's `consoleblank=0` never did anything.

## Debugging a card

- The journal is volatile even with `/var/log/journal` present; a first boot's NetworkManager log survives only if `runcmd`
  copies it to the boot partition.
- The card's ext4 root is readable on the Mac: obtain a raw dump through `authopen` (see `testkit/src/pihero_testkit/flash.py`
  for the descriptor passing, the same route Raspberry Pi Imager takes) and read it with `debugfs -c` in the tools container.
  Neither Imager's CLI nor `dd` as root can open the device from a terminal; macOS gates raw disk access behind `authopen`.
- `losetup` inside a privileged podman container needs `/dev` bind mounted, or the partition nodes it creates never appear.
- Raspberry Pi OS's `40-rpi-enable-watchdog.conf` sets `RuntimeWatchdogSec=1m`; a drop-in that wants to win must sort after it.
  Do not tighten it: on a Zero W `systemctl daemon-reload` takes 13.5 s at idle, and a 15 s timeout reset the board during
  provisioning, twice per run, each time a postinst or `runcmd` reloaded systemd under dpkg's I/O load (pihero 2.1.0).
- `bluez-test-tools` from the Raspberry Pi archive ships `btvirt` for a virtual Bluetooth adapter.
