#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" || true)")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

+diag() {
    check_start "System diagnostics"

    case $OSTYPE in
    linux*) : ;;
    *) die '%s: operating system unsupported' "$OSTYPE" ;;
    esac

    local init_system
    init_system=$(</proc/1/comm) || die "Failed to determine the init system"

    case $init_system in
    systemd) ;;
    *)
        check_raw '%s\n' '```' "UNSUPPORTED INIT SYSTEM: $init_system" '```'
        check_summary
        return
        ;;
    esac

    check_unit "/boot/cmdline.txt"
    check "it contains no line breaks" grep -q "\n" /boot/cmdline.txt

    check_unit "$init_system"
    if check --brief "system is operational" systemctl -q is-system-running --wait; then
        local slowest_units=()
        readarray -t slowest_units < <(systemd-analyze blame | head -n4 || true)
        check_raw '%s\n' '```' 'SLOWEST UNITS:' "${slowest_units[@]}" '```'
    else
        local failed_unit failed_units=()
        while read -r failed_unit; do
            failed_units+=("${failed_unit}")
        done < <(systemctl --failed --no-legend --no-pager | awk '{print $2}' || true)
        check_raw '%s\n' '```' "FAILED: ${failed_units[*]}" '```'

        for failed_unit in "${failed_units[@]}"; do
            local -a output=()
            readarray -t output < <(systemctl --no-pager status "$failed_unit" | remove_ansi_escapes | sed 's/^/  /' || true)
            check_raw '%s\n' '```' "$failed_unit:" "${output[@]}" '```'
        done
    fi

    # shellcheck disable=SC2016
    {
        check_further '- check boot log:\n  `%s`' 'sudo cat /var/log/boot.log'
        check_further '- check time to boot:\n  `%s`' 'systemd-analyze'
        check_further '- list running units ordered by their initialization time:\n  `%s`' 'systemd-analyze blame'
        check_further '- check time-critical chain of units:\n  `%s`' 'systemd-analyze critical-chain'
        check_further '- list all unit files:\n  `%s`' 'systemctl list-unit-files'
        check_further '- list failed units:\n  `%s`' 'systemctl list-units --state=failed'
        check_further '- check logs:\n  `%s`' 'journalctl -b'
    }
    check_summary
}
