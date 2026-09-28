# shellcheck shell=sh
# rpi-usb-gadget refuses anything but a Raspberry Pi. Turning it on is the one step that needs a reboot; an upgrade finds it on.
if grep -qs 'Raspberry Pi' /proc/device-tree/model && [ ! -f /etc/modules-load.d/usb-gadget.conf ]; then
  rpi-usb-gadget on -f >/dev/null
  printf '*** System restart required ***\n' >/run/reboot-required
  grep -qsx pihero-usb-gadget /run/reboot-required.pkgs || echo pihero-usb-gadget >>/run/reboot-required.pkgs
fi
