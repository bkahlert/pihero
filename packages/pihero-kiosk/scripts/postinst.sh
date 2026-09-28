# shellcheck shell=sh
if ! getent passwd kiosk >/dev/null; then
  adduser --quiet --system --group --no-create-home --home /nonexistent --shell /usr/sbin/nologin kiosk
fi