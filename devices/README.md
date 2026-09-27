# Device files

One directory per device, holding the cloud-init files that go onto the boot partition after flashing:
`user-data` (required), `network-config` (Wi-Fi, optional), `meta-data` (optional).

Real device directories are gitignored; keep them here or in a private repository. [`sample/`](sample/) is the reference.

Flash Raspberry Pi OS Lite (Trixie) with Raspberry Pi Imager, skip its customisation, then with the card still mounted:

    cp devices/<host>/user-data devices/<host>/network-config /Volumes/bootfs/

Boot. The device installs its packages, reboots once if a package asked for it, and appears as `<hostname>.local`.
