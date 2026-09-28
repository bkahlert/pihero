# Device files

One directory per device, holding the cloud-init files that go onto the boot partition after flashing:
`user-data` (required), `network-config` (Wi-Fi, optional), `meta-data` (optional).

Real device directories are gitignored; keep them here or in a private repository. [`sample/`](sample/) is the reference.

Write the card with the disk identifier from `diskutil list external`:

    make flash DEVICE=<host> DISK=disk9

This writes the pinned Raspberry Pi OS Lite (Trixie) image, reads it back to verify, copies the device files onto the boot partition, and ejects
the card. macOS asks once for authorization to write the disk. Raspberry Pi Imager works too: skip its customisation, then with the card still
mounted run `cp devices/<host>/user-data devices/<host>/network-config /Volumes/bootfs/`.

Boot. The device installs its packages, reboots once if a package asked for it (and once more when `rpi: enable_usb_gadget: true` is set), and
appears as `<hostname>.local`.
