#!/usr/bin/env bash

DEBUG_CMDLINE=(pfctl -s nat)

# Prints all downstream interfaces selected by the passed predicate (default: grep -q 'inet 10\.')
upstream_interface() {
    local route_output
    route_output=$(route -n get default) || return 1
    awk '/interface:/ {print $2}' <<<"$route_output"
}

# Prints all downstream interfaces selected by the passed predicate (default: grep -q 'inet 10\.')
downstream_interfaces() {
    local -a predicate
    local ifconfig_output none
    if [ "$#" -eq 0 ]; then
        predicate=(grep -q 'inet 10\.')
    else
        predicate=("$@")
    fi
    local interface
    for interface in $(ifconfig -lu); do
        ifconfig_output=$(ifconfig "$interface") || continue
        if printf %s "$ifconfig_output" | "${predicate[@]}" 2>/dev/null; then
            none=0
            echo "$interface"
        fi
    done
    [ -n "$none" ]
}

main() {
    [ "$(id -u || true)" -eq 0 ] || { printf "\e[31mERROR: This script must be run as root.\e[0m\n" >&2 && exit 1; }

    local u_interface
    u_interface=$(upstream_interface) || { printf "\e[31mERROR: No upstream interface found.\e[0m\n" >&2 && exit 1; }

    local d_interfaces
    d_interfaces=$(downstream_interfaces "$@") || { printf "\e[31mERROR: No downstream interfaces found.\e[0m\n" >&2 && exit 1; }

    printf '%s' 'Enabling IP forwarding... ' >&2
    if sysctl -w net.inet.ip.forwarding=1 2>/dev/null >&2; then
        printf "\e[32;1m✔\e[0m\n" >&2
    else
        printf "\e[31mERROR: Failed to enable IP forwarding.\e[0m\n" >&2
        exit 1
    fi
    pfctl -d 2>/dev/null >&2 || true
    pfctl -F all 2>/dev/null >&2 || true

    local d_interface
    while read -r d_interface; do
        printf "Enabling NAT on \e[3m%s\e[23m from \e[3m%s\e[23m... " "$u_interface" "$d_interface" >&2
        if echo "nat on $u_interface from $d_interface:network to any -> ($u_interface)" | pfctl -f - -e >&2 2>/dev/null; then
            printf "\e[32;1m✔\e[0m\n" >&2
            [ ! -p /dev/stdout ] || printf '%s\n' "$d_interface" # print interface if piped
        else
            printf "\e[31mFailed to enable NAT on \e[3m%s\e[23m from \e[3m%s\e[23m.\nOutput of \e[3m%s\e[23m:\n%s\e[0m\n" \
                "$u_interface" "$d_interface" "${DEBUG_CMDLINE[*]}" "$("${DEBUG_CMDLINE[@]}" 2>&1 || true)" >&2
            exit 1
        fi
    done < <(printf "%s\n" "${d_interfaces[@]}")
}

main "$@"
