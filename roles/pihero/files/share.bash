#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

# TODO call share with sudo

+diag() {
    local result

    checks_start "Share diagnostics"
    check "dnsmasq is running" systemctl -q is-active dnsmasq.service

    check_summary
    result=$?

    return $result
}

+start() {
    sharectl start "$@"
}

+stop() {
    sharectl stop "$@"
}

sharectl() {
    local lease self_name host_ip host_name
    lease=$(newest_dhcp_lease 2>/dev/null) || {
        printf "\e[33mFailed to find host. No corresponding DHCP lease was found.\e[0m\n" >&2
        exit 1
    }
    IFS=' ' read -ra c <<<"$lease"
    self_name="$(hostnamectl --pretty status)"
    host_ip="${c[1]}" # [1]=IP, [2]=MAC, [3]=hostname
    host_name="${c[3]}"
    if [ "$1" = "start" ]; then
        printf "Preparing \e[3m%s\e[23m to use \e[3m%s\e[23m (\e[3m%s\e[23m) as upstream...\e[0m\n" \
            "$self_name" "$host_name" "$host_ip" >&2
        if add_default_route "$host_ip" && dns_set; then
            printf "Done \e[32m✔︎\e[0m\n" >&2
            printf "\e[1mDon't forget to activate routing on \e[3m%s\e[23m!\e[0m\n" "$host_name" >&2
        else
            printf "\e[31mFailed to prepare \e[3m%s\e[23m to use \e[3m%s\e[23m (\e[3m%s\e[23m) as upstream.\e[0m\n" \
                "$self_name" "$host_name" "$host_ip" >&2
            exit 1
        fi
    else
        printf "Stopping \e[3m%s\e[23m from using \e[3m%s\e[23m (\e[3m%s\e[23m) as upstream...\e[0m\n" \
            "$self_name" "$host_name" "$host_ip" >&2
        if dns_unset && delete_default_route "$host_ip"; then
            printf "Done \e[32m✔︎\e[0m\n" >&2
            printf "\e[1mDon't forget to deactivate routing on \e[3m%s\e[23m!\e[0m\n" "$host_name" >&2
        else
            printf "\e[31mFailed to stop \e[3m%s\e[23m from using \e[3m%s\e[23m (\e[3m%s\e[23m) as upstream.\e[0m\n" \
                "$self_name" "$host_name" "$host_ip" >&2
            exit 1
        fi
    fi
    ip route show
}

newest_dhcp_lease() {
    iface="${1:-.*}"
    journalctl --boot --unit dnsmasq.service --grep 'DHCPACK\('"$iface"'\)' --output cat --reverse --lines 1
}

dns_set() {
    dns_servers=('8.8.8.8' '8.8.4.4')
    printf "Configuring dnsmasq to use DNS servers \e[3m%s\e[23m...\n" "${dns_servers[*]}" >&2
    printf 'server=%s\n' "${dns_servers[@]}" >/etc/dnsmasq.d/pihero-dns.conf
    systemctl restart dnsmasq.service
}

dns_unset() {
    printf "Removing dnsmasq DNS servers...\n" >&2
    [ -f /etc/dnsmasq.d/pihero-dns.conf ] || { printf "No servers set.\n" >&2 && return 0; }
    rm /etc/dnsmasq.d/pihero-dns.conf
    systemctl restart dnsmasq.service
}

add_default_route() {
    host_ip="${1?host IP missing}"
    printf "Adding default route via \e[3m%s\e[23m...\n" "$host_ip" >&2
    ip route add default via "$host_ip"
}

delete_default_route() {
    host_ip="${1?host IP missing}"
    printf "Deleting default route via \e[3m%s\e[23m...\n" "$host_ip" >&2
    ip route delete default via "$host_ip"
}
