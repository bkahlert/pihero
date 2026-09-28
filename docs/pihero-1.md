# Pi Hero 1

Pi Hero 1 was an Ansible playbook run from a control machine against an inventory of boards. It is frozen at tag
[`pihero-ansible`](https://github.com/bkahlert/pihero/tree/pihero-ansible) and still works from there. This is what became of
each part in Pi Hero 2; the reasoning is in [design.md](design.md).

| Pi Hero 1 | Pi Hero 2 |
|---|---|
| Ansible playbook, inventory per host, provisioning over SSH from a control machine | One cloud-init file per device under `devices/`; the card provisions itself, changes are `apt upgrade` or a reflash |
| `patch --continuous` development loop | `make deploy TARGET=pi@host` |
| MOTD blocks | `pihero`: one `/etc/update-motd.d/` script |
| `kernel_parameters` module and `config.txt` edits | `pihero`: `bootconfig`, used only where cloud-init's `rpi:` and `raspi-config nonint` have no option |
| device_info role: Avahi install, pretty hostname, `_device-info._tcp`, `_ssh._tcp` | `pihero-avahi`, rendered at boot; Raspberry Pi OS ships Avahi |
| Splash screen during boot and shutdown (Plymouth theme) | planned as `pihero-splash` |
| Samba shares for the home directory and `/` | planned as `pihero-smb` |
| Bluetooth PAN with trusted devices and a per-device subnet | planned as `pihero-bt-pan`, on a NetworkManager bridge instead of ifupdown and dnsmasq |
| HDMI display configuration (`hdmi_group`, `hdmi_mode`, `hdmi_cvt`) | planned as `pihero-display-hdmi` with `video=` kernel parameters; Trixie runs full KMS, where the old keys are ignored |
| Ethernet over USB: dwc2, DHCP, NAT, connection sharing scripts | Upstream `rpi-usb-gadget` with its internet-sharing watcher, enabled from the device file, `g_cdc` instead of `g_ether` |
| Ethernet over USB with RNDIS for Windows | CDC ECM only, which macOS and Linux drive natively; Windows needs a driver until a configfs NCM gadget exists |
| Serial port over USB, mass storage, keyboard, mouse, composite gadget functions | Dropped; the GPIO UART is the serial path, the rest waits for an application that needs it |
| `pihero` CLI with `pihero diag` diagnostics and the `gum` interface | Dropped; the test tiers replace the diagnostics, and `gum` was too slow on old boards |
| apt-update pre-task, `AllowReleaseInfoChange`, user groups fact | Covered by apt and cloud-init `users:` |
| Tailscale notes | Commented lines in the sample device file, including the exit-node steps |
| Support for the 32-bit-only Raspberry Pi Zero W | Packages are architecture-independent and the 32-bit Trixie image runs them; `make flash` and the harness pin the 64-bit image |
| Not present: hardware watchdog, limits for applications | `pihero` arms the watchdog; [app-conventions.md](app-conventions.md) sets `Restart=` and `MemoryMax=` |
