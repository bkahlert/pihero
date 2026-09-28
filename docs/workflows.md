# Workflows

The day-to-day with Pi Hero 2. Commands run from the repository root on the Mac unless they say `pi@`.

## Set up the Mac once

```shell
brew bundle          # qemu, podman, uv
podman machine init && podman machine start
make doctor          # lists what is missing
make vm-prepare      # caches the tier-2 base image, about ten minutes once
```

## Bring up a new device

1. Describe it. One directory per device, gitignored unless it is the sample:
   ```shell
   mkdir devices/mypi && cp devices/sample/user-data devices/sample/network-config devices/mypi/
   ```
   In `user-data` set `hostname`, your SSH public key, the pretty name in `runcmd`, the `MODEL` for the Finder icon, and the USB
   subnet. In `network-config` set the Wi-Fi name and password and keep `regulatory-domain`.
2. Flash. Insert the card, find it, write it:
   ```shell
   diskutil list external
   make flash DEVICE=mypi DISK=disk9
   ```
   macOS asks once for authorization. The card is ejected when done.
3. Boot. Provisioning takes about six minutes and reboots twice: once for the interface settings, once for the USB gadget.
   Then the Pi answers `ssh pi@mypi.local`, appears in Finder with its icon, and a Mac on the USB cable gets an address from it.

If it does not show up, [devices/README.md](../devices/README.md) says where to look.

## Change a device

cloud-init runs once per card. A changed device file means a reflash. Small things are done live and survive updates:
the Finder icon in `/etc/pihero/device-info.conf` followed by `systemctl restart pihero-avahi-render.service`, network
settings with `nmcli`, boot settings with `/usr/lib/pihero/bootconfig` (which flags the reboot the MOTD then shows).

## Update devices

```shell
ssh pi@mypi.local sudo apt update '&&' sudo apt upgrade
```

The repository is signed; the device trusts only the key embedded in its device file. Reboot when the MOTD says so.

## Change a package

Everything of a feature lives under `packages/<name>/`. The loop:

```shell
make test-tier0                       # unit tests of the scripts, static checks of every package
make test-tier1                       # install, remove, purge in a systemd container
make test-tier1 PLATFORM=linux/arm/v7 # the 32-bit image's view
make deploy TARGET=pi@mypi.local      # the built .debs on a real device, no repository involved
make test-tier2                       # a VM boots the all-features device from a local repository
```

`uv run pytest packages/<name>/tests -m tier0` runs one package's unit tests. `make vm` keeps the tier-2 VM running for a
look inside. CI runs tiers 0 and 1 on every push and tier 2 weekly. What each tier proves and how it works is in
[testing.md](testing.md).

## Check a real device

```shell
uv run pytest -m installed --target=ssh --target-uri=pi@mypi.local
```

The tests compare against the version installed on the device and skip everything that would change it. The Avahi tests
need `avahi-utils` on the device.

## Release

```shell
make release VERSION=2.1.0        # clean tree required; runs tiers 0 to 2, then tags v2.1.0
git push origin v2.1.0            # the release workflow builds, signs, and publishes
curl -fsS https://bkahlert.github.io/pihero/apt/Packages | grep -A1 '^Package: pihero'
```

Tags with a pre-release suffix such as `v2.1.0-rc.1` publish as `2.1.0~rc.1` and are marked pre-release on GitHub. The
signing key is the `APT_SIGNING_KEY` secret of the `release` environment, which only `v*` tags can deploy to; `make repo`
builds and signs the same repository locally from `~/.config/pihero-apt-signing-key.asc`.
