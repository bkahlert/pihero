# shellcheck shell=sh
# Purging the package turns the feature off. rpi-usb-gadget may already be gone when both are purged in one run.
if grep -qs 'Raspberry Pi' /proc/device-tree/model && command -v rpi-usb-gadget >/dev/null && [ -f /etc/modules-load.d/usb-gadget.conf ]; then
  rpi-usb-gadget off >/dev/null
  printf '*** System restart required ***\n' >/run/reboot-required
  grep -qsx pihero-usb-gadget /run/reboot-required.pkgs || echo pihero-usb-gadget >>/run/reboot-required.pkgs
fi
