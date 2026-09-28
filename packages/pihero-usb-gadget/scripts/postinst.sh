# shellcheck shell=sh
# rpi-usb-gadget refuses anything but a Raspberry Pi and asks before enabling a board it does not list. The piped "n" turns
# that question into a loud failure, so a 3B or CM4 never loses its only USB controller to peripheral mode. Turning it on is
# the one step that needs a reboot; an upgrade finds it on.
if grep -qs 'Raspberry Pi' /proc/device-tree/model && [ ! -f /etc/modules-load.d/usb-gadget.conf ]; then
  printf 'n\n' | rpi-usb-gadget on
  printf '*** System restart required ***\n' >/run/reboot-required
  grep -qsx pihero-usb-gadget /run/reboot-required.pkgs || echo pihero-usb-gadget >>/run/reboot-required.pkgs
fi
