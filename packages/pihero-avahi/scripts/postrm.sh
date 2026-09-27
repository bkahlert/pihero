# shellcheck shell=sh
rm -f /etc/avahi/services/pihero-device-info.service /etc/avahi/services/pihero-ssh.service
if [ -d /run/systemd/system ]; then
  systemctl try-reload-or-restart avahi-daemon.service >/dev/null 2>&1 || true
fi
