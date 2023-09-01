#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

+diag() {
    local result theme

    checks_start "Splash diagnostics"

    check_unit "/boot/config.txt"
    check "splash is disabled" grep -q "^disable_splash=1$" /boot/config.txt

    check_unit "/boot/cmdline.txt"
    check "quiet is specified" grep -q " quiet" /boot/cmdline.txt
    check "loglevel is specified right after quiet" grep -q " quiet loglevel=" /boot/cmdline.txt
    check "splash is specified" grep -q " splash" /boot/cmdline.txt
    check "vt.global_cursor_default is set to 0" grep -q " vt.global_cursor_default=0" /boot/cmdline.txt

    check "logo.nologo is specified" grep -q " logo.nologo" /boot/cmdline.txt

    check "plymouth.enable is set to 1" grep -q " plymouth.enable=1" /boot/cmdline.txt
    check "plymouth.ignore-serial-consoles is specified" grep -q " plymouth.ignore-serial-consoles" /boot/cmdline.txt

    check_unit "plymouth"
    check "plymouth is installed" dpkg -s plymouth >/dev/null
    check "plymouth-themes are installed" dpkg -s plymouth-themes >/dev/null
    printf "\e[1mAvailable plymouth themes:\e[0m"
    while read -r theme; do
        printf " %s" "$theme"
    done < <(plymouth-set-default-theme --list)
    printf "\n"

    check_summary
    result=$?

    {
        printf -- '\n\e[4mUseful commands:\e[0m\n'
        printf -- '- add \e[3m%s\e[23m to \e[3m%s\e[23m to enable debug logs\n' 'plymouth.debug' '/boot/cmdline.txt'
        printf -- '- debug logs are located at \e[3m%s\e[23m\n' '/var/log/plymouth-debug.log'
        printf -- '- for tips and tricks, see %s\n' 'https://wiki.archlinux.org/title/plymouth#Tips_and_tricks'
    } | sed 's/^/  /'

    return $result
}

+enable() {
    printf "Enabling Plymouth... "
    if sudo sed -i 's/\bplymouth.enable=0\b/plymouth.enable=1/' /boot/cmdline.txt; then
        printf '\e[32;1m✔\e[0m\n'
    fi
    printf "Suppressing successful systemd messages... "
    if sudo sed -i 's/\bsystemd.show_status=true\b/systemd.show_status=auto/' /boot/cmdline.txt; then
        printf '\e[32;1m✔\e[0m\n'
    fi
}

+disable() {
    printf "Disabling Plymouth... "
    if sudo sed -i 's/\bplymouth.enable=1\b/plymouth.enable=0/' /boot/cmdline.txt; then
        printf '\e[32;1m✔\e[0m\n'
    fi
    printf "Printing successful systemd messages... "
    if sudo sed -i 's/\bsystemd.show_status=auto\b/systemd.show_status=true/' /boot/cmdline.txt; then
        printf '\e[32;1m✔\e[0m\n'
    fi
}

+list() {
    plymouth-set-default-theme --list
}

+get() {
    plymouth-set-default-theme
}

+set() {
    local theme
    if [ "${1:-}" ]; then
        theme="$1"
    else
        local themes=() && readarray -t themes < <(+list)
        local PS3="Select a theme: "
        select theme in "${themes[@]}"; do
            [ -n "$theme" ] || break
            printf ' \e[31m✘\e[0m %s\n' "Invalid selection"
        done
    fi

    printf "Setting theme to \e[3m%s\e[23m... " "$theme"
    if sudo plymouth-set-default-theme --rebuild-initrd "$theme"; then
        printf '\e[32;1m✔\e[0m\n'
    fi
}

# not working because of read command
#+test-all() {
#  with_themes +test
#}

+test() {
    printf 'Testing theme \e[3m%s\e[23m... ' "$(+get)"
    if sudo plymouthd && sudo plymouth show-splash; then
        printf "Press enter to quit... "
        read -rsn1
    fi

    if sudo plymouth quit; then
        printf '\e[32;1m✔\e[0m\n'
    fi
}

+test-variants-all() {
    with_themes +test-variants
}

+test-variants() {
    if sudo plymouthd && sudo plymouth show-splash; then
        printf "Starting in %d seconds...\n" 10
        sleep 10
        printf "Testing display-message... "
        if sudo plymouth display-message --text="Hello World!"; then
            printf '\e[32;1m✔\e[0m\n'
        fi
        sleep 2
        printf "Testing progress... "
        sudo plymouth system-update --progress=0
        sleep 1
        sudo plymouth system-update --progress=10
        sleep 1
        sudo plymouth system-update --progress=30
        sleep 1
        sudo plymouth system-update --progress=60
        sleep 1
        sudo plymouth system-update --progress=90
        sleep 1
        sudo plymouth system-update --progress=95
        sleep 1
        sudo plymouth system-update --progress=100
        printf '\e[32;1m✔\e[0m\n'
        sleep 2
        printf "Testing updates mode... "
        if sudo plymouth change-mode --updates; then
            printf '\e[32;1m✔\e[0m\n'
        fi
        sleep 2
        printf "Testing shutdown mode... "
        sudo plymouth change-mode --shutdown
        sudo plymouth system-update --progress=0
        sleep 1
        sudo plymouth system-update --progress=30
        sleep 1
        sudo plymouth system-update --progress=40
        sleep 1
        sudo plymouth system-update --progress=60
        sleep 1
        printf '\e[32;1m✔\e[0m\n'
    fi
    if sudo plymouth quit; then
        printf 'Done \e[32;1m✔\e[0m\n'
    fi
}

+debug() {
    local line events=10 debug_file=/tmp/plymouth-debug-out
    printf -v line "\e[1m%0.s—\e[0m" $(seq 1 "$(tput cols)")
    printf "Debugging theme with debug file \e[3m%s\e[23m...\n" "$debug_file"
    if sudo plymouthd --debug --debug-file="$debug_file" && sudo plymouth show-splash; then
        local i
        for i in $(seq 1 "$events"); do
            printf "\nEvent %d/%d\n%s\n" "$i" "$events" "$line"
            sudo plymouth --update=event"$i"
            sleep 1
        done
    fi
    if sudo plymouth quit; then
        printf "%s\nDone \e[32;1m✔\e[0m\n" "$line"
    fi
}

with_themes() {
    local backup theme
    backup="$(plymouth-set-default-theme)"
    while read -r theme; do
        printf "\e[1mWith theme \e[3m%s\e[23m\e[0m...\n" "$theme"
        if sudo plymouth-set-default-theme --rebuild-initrd "$theme"; then
            "$@" "$theme"
        else
            printf "\e[31mFailed to set theme %s\e[0m\n" "$theme"
        fi
    done <<<"$(plymouth-set-default-theme --list)"
    sudo plymouth-set-default-theme --rebuild-initrd "$backup"
}
