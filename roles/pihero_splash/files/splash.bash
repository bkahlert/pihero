#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
source "$SCRIPT_DIR/lib/lib.bash"

+diag() {
    local result theme

    checks_start "Splash diagnostics"

    check_unit "/boot/config.txt"
    check "splash is disabled" grep -q "^disable_splash=1$" /boot/config.txt

    check_unit "/boot/cmdline.txt"
    check "quiet is specified" grep -q " quiet" /boot/cmdline.txt
    check "loglevel is specified right after quiet" grep -q " quiet loglevel=" /boot/cmdline.txt
    check "splash is removed" grep -v -q " splash" /boot/cmdline.txt
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
    done <<<"$(plymouth-set-default-theme --list)"
    printf "\n"

    check_summary
    result=$?

    return $result
}

+list() {
    plymouth-set-default-theme --list
}

+get() {
    plymouth-set-default-theme
}

+set() {
    local theme="${1:?theme missing}"
    printf "Setting theme to \e[3m%s\e[23m... " "$theme"
    if sudo plymouth-set-default-theme --rebuild-initrd "$theme"; then
        printf '\e[32m✔︎\e[0m\n'
    fi
}

# not working because of read command
#+test-all() {
#  with_themes +test
#}

+test() {
    printf "Testing theme... "
    if sudo plymouthd && sudo plymouth show-splash; then
        printf "Press enter to quit... "
        read -rsn1
    fi
    if sudo plymouth quit; then
        printf '\e[32m✔︎\e[0m\n'
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
            printf '\e[32m✔︎\e[0m\n'
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
        printf '\e[32m✔︎\e[0m\n'
        sleep 2
        printf "Testing updates mode... "
        if sudo plymouth change-mode --updates; then
            printf '\e[32m✔︎\e[0m\n'
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
        printf '\e[32m✔︎\e[0m\n'
    fi
    if sudo plymouth quit; then
        printf 'Done \e[32m✔︎\e[0m\n'
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
        printf "%s\nDone \e[32m✔︎\e[0m\n" "$line"
    fi
}

with_themes() {
    local backup theme
    backup="$(plymouth-set-default-theme)"
    while read -r theme; do
        printf "\e[1mWith theme \e[3m%s\e[23m\e[0m...\n" "$theme"
        if sudo plymouth-set-default-theme --rebuild-initrd "$theme"; then
            #      "$@" "$theme"
            sleep 1
            printf "\e[32m✔︎\e[0m\n"
        else
            printf "\e[31mFailed to set theme %s\e[0m\n" "$theme"
        fi
    done <<<"$(plymouth-set-default-theme --list)"
    sudo plymouth-set-default-theme --rebuild-initrd "$backup"
}

while read -r backing_file; do
    [ -f "$backing_file" ] || {
        printf 'Backing file %s does not exist. Skipping.\n' "$backing_file"
        continue
    }
    case "$backing_file" in
    *.service)
        printf 'Removing service file %s\n' "$backing_file"
        rm -f "$backing_file"
        ;;
    *)
        printf 'Ignoring non-service file %s\n' "$backing_file"
        ;;
    esac
done < <(systemctl cat 'splashscreen.service' | sed -n 's/^#\s*//p')

systemctl cat 'splashscreen.service' | sed -n 's/^#\s*//p' | while read -r backing_file; do
    [ -f "$backing_file" ] || {
        printf 'Backing file %s does not exist. Skipping.\n' "$backing_file"
        continue
    }
    printf 'Deleting file %s\n' "$backing_file"
done
