#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

+diag() {
    local result

    checks_start "System diagnostics"

    local os
    os=$(uname -o) || die "Failed to determine the operating system"
    case "$os" in
    *Linux*) : ;;
    *) die "The operating system %p is not supported." "$os" ;;
    esac

    local init_system
    init_system=$(</proc/1/comm) || die "Failed to determine the init system"

    case "$init_system" in
    systemd) ;;
    *)
        printf "\e[2mSkipping unsupported \e[3m%s\e[23m init system... \e[32;1m✔\e[0m\n" "$init_system"
        return 0
        ;;
    esac

    check_unit "/boot/cmdline.txt"
    check "it contains no line breaks" grep -q "\n" /boot/cmdline.txt

    check_unit "$init_system"
    if check --brief "system is operational" systemctl -q is-system-running --wait; then
        printf 'Getting the units that take the most time to initialize...\n'
        systemd-analyze blame | head -n4
    else
        local failed_unit failed_units=()
        while read -r line; do
            failed_units=("${failed_units[@]}" "$(echo "$line" | awk '{print $1}')")
        done < <(systemctl --failed --no-legend --no-pager)
        printf 'The following units failed: \e[3m%s\e[23m' "${failed_units[0]}"
        [ "${#failed_units[@]}" -le 1 ] || printf ', \e[3m%s\e[23m' "${failed_units[@]:1}"
        printf '\n'

        for failed_unit in "${failed_units[@]}"; do
            printf '\n'
            systemctl --no-pager status "$failed_unit"
        done
    fi

    check_summary
    result=$?

    {
        printf "\n\e[4mUseful commands:\e[0m\n"
        printf -- "- check boot log: \e[3m%s\e[23m\n" 'sudo cat /var/log/boot.log'
        printf -- "- check time to boot: \e[3m%s\e[23m\n" 'systemd-analyze'
        printf -- "- list running units ordered by their initialization time: \e[3m%s\e[23m\n" 'systemd-analyze blame'
        printf -- "- check time-critical chain of units: \e[3m%s\e[23m\n" 'systemd-analyze critical-chain'
        printf -- "- list all unit files: \e[3m%s\e[23m\n" 'systemctl list-unit-files'
        printf -- "- list failed units: \e[3m%s\e[23m\n" 'systemctl list-units --state=failed'
        printf -- "- check logs: \e[3m%s\e[23m\n" 'journalctl -b'
    } | sed 's/^/  /'
    return "$result"
}
