# shellcheck shell=sh
if [ -d /run/systemd/system ]; then
  systemctl daemon-reexec >/dev/null 2>&1 || true
fi
