#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" || true)")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

+diag() {
    local gadget_name
    if [ $# -gt 0 ]; then
        gadget_name=$1
        shift
    else
        gadget_name=pihero
    fi

    local config_name
    if [ $# -gt 0 ]; then
        config_name=$1
        shift
    else
        config_name=c.1
    fi

    local instance_name
    if [ $# -gt 0 ]; then
        instance_name=$1
        shift
    else
        instance_name=usb0
    fi

    check_start "USB gadget diagnostics"
    check "/boot/config.txt contains dtoverlay=dwc2" grep -q '^dtoverlay=dwc2\(,dr_mode=.*\)\?$' /boot/config.txt
    check "/boot/cmdline.txt contains modules-load=dwc2" grep -q "modules-load=dwc2" /boot/cmdline.txt
    check "libcomposite module is loaded" bash -c 'lsmod | grep -q "^libcomposite "'
    check "usb-gadget service is active" systemctl -q is-active usb-gadget.service

    check_unit "USB gadget $gadget_name"

    local CONFIGFS_HOME mnt_exit_code
    CONFIGFS_HOME=$(findmnt --output TARGET --noheadings configfs)
    mnt_exit_code=$?
    check "configfs is mounted" test "$mnt_exit_code" -eq 0
    if [ "$mnt_exit_code" -eq 0 ]; then
        local gadget_dir="$CONFIGFS_HOME/usb_gadget/$gadget_name"
        check "usb-gadget's vendor ID is configured" grep -q "^0x1d6b$" "$gadget_dir"/idVendor
        check "usb-gadget's product ID is configured" grep -q "^0x0104$" "$gadget_dir"/idProduct
        check "usb-gadget's bcd device is configured" grep -q "^0x0100$" "$gadget_dir"/bcdDevice
        check "usb-gadget's bcd USB is configured" grep -q "^0x0200$" "$gadget_dir"/bcdUSB
        check "usb-gadget's device class is configured" grep -q "^0xef$" "$gadget_dir"/bDeviceClass
        check "usb-gadget's device subclass is configured" grep -q "^0x02$" "$gadget_dir"/bDeviceSubClass
        check "usb-gadget's device protocol is configured" grep -q "^0x01$" "$gadget_dir"/bDeviceProtocol
        check "usb-gadget's serial number is not empty" grep -v -q "^$" "$gadget_dir"/strings/0x409/serialnumber
        check "usb-gadget's manufacturer is not empty" grep -v -q "^$" "$gadget_dir"/strings/0x409/manufacturer
        check "usb-gadget's product is not empty" grep -v -q "^$" "$gadget_dir"/strings/0x409/product
        check "usb-gadget is running" grep -q "^$(ls /sys/class/udc)$" "$gadget_dir"/UDC

        shopt -s nullglob
        local function_dir function
        for function_dir in "$gadget_dir"/functions/*; do
            function=${function_dir##*/}
            case $function in
            acm.*)
                check_unit 'serial port'
                check "instance name is $instance_name" test "$instance_name" = "${function#*.}"
                check "serial port is active" systemctl -q is-active serial-getty@ttyGS0.service
                ;;
            ecm.*)
                check_unit 'ethernet'
                check "instance name is $instance_name" test "$instance_name" = "${function#*.}"
                check "dnsmasq is installed" which dnsmasq >/dev/null
                check "dnsmasq is active" systemctl -q is-active dnsmasq.service
                check "usb0 interface exists" ip link show usb0 >/dev/null
                check "usb0 interface is configured" ip -4 -o addr show usb0 | grep -q ' {{ usb0_cidr }} '
                check "usb0 interface is dhcpcd-excluded" grep -q "^denyinterfaces usb0$" /etc/dhcpcd.conf
                check "usb0 interface is configured for dnsmasq" grep -q "^interface=usb0$" /etc/dnsmasq.d/usb0.conf
                check "usb0 dnsmasq config is not malformed" grep -v -q "^interface$" /etc/dnsmasq.d/usb0.conf
                check "usb0 dnsmasq config is not malformed (key-only entries with =)" grep -v -q "^leasefile-ro=" /etc/dnsmasq.d/usb0.conf
                ;;
            *.*)
                check_unit "${function%.*}"
                echo "No checks found for function ${function%.*}"
                ;;
            *)
                check_unit "$function"
                check "valid function name" false
                ;;
            esac
        done
    fi

    # shellcheck disable=SC2016
    {
        [ -z "$gadget_dir" ] || check_further '- check usb-gadget config:\n  `%s`' "ls -1lAFhctR '$gadget_dir'"
        check_further '- check usb-gadget service logs:\n  `%s`' "systemctl status usb-gadget.service; journalctl -b -u usb-gadget.service"
        check_further '- stop usb-gadget interactively:\n  `%s`' "pihero gadget stop"
        check_further '- start usb-gadget interactively:\n  `%s`' "pihero gadget start"
        if [ -n "$gadget_dir" ] && [ -d "$gadget_dir/functions/ecm.$instance_name" ]; then
            check_further '- scan for connected hosts:\n  `%s`' "command -v nmap >/dev/null 2>&1 || sudo apt-get install -yqq nmap; nmap -sn 10.10.10.11-14"
            check_further '- check networking:\n  `%s`' "systemctl status networking"
            for service in dnsmasq; do
                check_further_unit '%s service' "$service"
                check_further '- check status:\n  `%s`' "systemctl status $service.service"
                check_further '- check logs:\n  `%s`' "journalctl -b -e -u $service.service"
                check_further '- stop service:\n  `%s`' "sudo systemctl stop $service.service"
                check_further '- start service interactively:\n  `%s`' "$(service_start_cmdline "$service.service")"
            done
        fi
    }

    check_summary
}

+start() {
    /opt/pihero/usb-gadget start "$@"
}

+stop() {
    /opt/pihero/usb-gadget stop "$@"
}
