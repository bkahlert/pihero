# Device files

One directory per device, holding the cloud-init files that go onto the boot partition after flashing:
`user-data` (required), `network-config` (Wi-Fi, optional), `meta-data` (optional).

Real device directories are gitignored; keep them here or in a private repository. [`sample/`](sample/) is the reference.

Write the card with the disk identifier from `diskutil list external`:

    make flash DEVICE=<host> DISK=disk9

This writes the pinned Raspberry Pi OS Lite (Trixie) image, reads it back to verify, copies the device files onto the boot partition, puts the
Wi-Fi regulatory domain from `network-config` on the kernel command line (Raspberry Pi OS has no Wi-Fi on the first boot without it), and
ejects the card. macOS asks once for authorization to write the disk. Raspberry Pi Imager works too: skip its customisation, then with the card still
mounted run `cp devices/<host>/user-data devices/<host>/network-config /Volumes/bootfs/`.

Boot. The device applies its interface settings and reboots, installs its packages, enables the USB gadget and reboots again, and appears as
`<hostname>.local` after about five minutes.
