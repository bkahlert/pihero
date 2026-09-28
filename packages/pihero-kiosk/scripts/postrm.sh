# shellcheck shell=sh
rm -rf /var/cache/pihero-kiosk /var/lib/pihero-kiosk /run/pihero-kiosk
if getent passwd kiosk >/dev/null; then
  deluser --quiet --system kiosk >/dev/null 2>&1 || true
fi