#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
source "$SCRIPT_DIR/lib/lib.bash"

+diag() {
  local result
  checks_start "Bluetooth PAN diagnostics"

  check "/lib/systemd/system/hciuart.service exists" test -f /lib/systemd/system/hciuart.service

  check "systemd-networkd.service is not active" ! systemctl -q is-active systemd-networkd.service
  check "/etc/systemd/network/pan0.netdev is not present" test ! -f /etc/systemd/network/pan0.netdev
  check "/etc/systemd/network/pan0.network is not present" test ! -f /etc/systemd/network/pan0.network

  check "bt-network is active" systemctl -q is-active bt-network.service
  check "bt-agent is active" systemctl -q is-active bt-agent.service

  check "dnsmasq is installed" which dnsmasq >/dev/null
  check "dnsmasq is active" systemctl -q is-active dnsmasq.service
  check "pan0 interface exists" ip link show pan0 >/dev/null
  check "pan0 interface is configured" grep -q "^auto pan0$" /etc/network/interfaces.d/pan0
  check "pan0 interface is configured for dnsmasq" grep -q "^interface=pan0$" /etc/dnsmasq.d/pan0.conf
  check "pan0 dnsmasq config is not malformed" grep -v -q "^interface$" /etc/dnsmasq.d/pan0.conf
  check "pan0 dnsmasq config is not malformed" grep -v -q "^leasefile-ro=" /etc/dnsmasq.d/pan0.conf

  check_summary
  result=$?

  {
    printf -- "\n\e[4mUseful commands:\e[0m\n"
    printf -- "- print name of bluetooth adapter: \e[3m%s\e[23m\n" 'hciconfig hci0 name'
    printf -- "- print class of bluetooth adapter: \e[3m%s\e[23m\n" 'hciconfig hci0 class'
    printf -- "- print features of bluetooth adapter: \e[3m%s\e[23m\n" 'hciconfig hci0 features'
    printf -- "- list bluetooth adapter information: \e[3m%s\e[23m\n" 'bt-adapter --info'
    printf -- "- list connected devices: \e[3m%s\e[23m\n" 'bt-device --list'
    printf -- "- info about connected device: \e[3m%s\e[23m\n" 'bt-device --info=<name|mac>'
    for service in bt-network bt-agent dnsmasq; do
      printf -- "\e[1m- regarding service \e[3m%s\e[23m:\e[0m\n" "$service"
      printf -- "  - check status: \e[3m%s\e[23m\n" "systemctl status $service.service"
      printf -- "  - check logs: \e[3m%s\e[23m\n" "journalctl -b -e -u $service.service"
      printf -- "  - stop service: \e[3m%s\e[23m\n" "sudo systemctl stop $service.service"
      printf -- "  - start service interactively: \e[3m%s\e[23m\n" "$(service_start_cmdline "$service.service")"
    done
  } | sed 's/^/  /' >&2

  return $result
}
