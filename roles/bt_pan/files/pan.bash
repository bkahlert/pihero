#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" || true)")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

+diag() {
    check_start "Bluetooth PAN diagnostics"

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

    # shellcheck disable=SC2016
    {
        check_further '- print name of bluetooth adapter:\n  `%s`' 'hciconfig hci0 name'
        check_further '- print class of bluetooth adapter:\n  `%s`' 'hciconfig hci0 class'
        check_further '- print features of bluetooth adapter:\n  `%s`' 'hciconfig hci0 features'
        check_further '- list bluetooth adapter information:\n  `%s`' 'bt-adapter --info'
        check_further '- list connected devices:\n  `%s`' 'bt-device --list'
        check_further '- info about connected device:\n  `%s`' 'bt-device --info=<name|mac>'
        for service in bt-network bt-agent dnsmasq; do
            check_further_unit '%s service' "$service"
            check_further '- check status:\n  `%s`' "systemctl status $service.service"
            check_further '- check logs:\n  `%s`' "journalctl -b -e -u $service.service"
            check_further '- stop service:\n  `%s`' "sudo systemctl stop $service.service"
            check_further '- start service interactively:\n  `%s`' "$(service_start_cmdline "$service.service")"
        done
    }
    check_summary
}
