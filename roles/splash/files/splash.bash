#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" || true)")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

+diag() {
    check_start "Splash diagnostics"

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
    local available_themes=()
    readarray -t available_themes < <(plymouth-set-default-theme --list)
    check_raw '%s\n' '```' 'AVAILABLE PLYMOUTH THEMES:' "${available_themes[*]}" '```'

    # shellcheck disable=SC2016
    {
        check_further '- add `%s` to `%s` to enable debug logs' 'plymouth.debug' '/boot/cmdline.txt'
        check_further '- debug logs are located at `%s`' '/var/log/plymouth-debug.log'
        check_further '- for tips and tricks, see [%s](%s)' 'archlinux.org' 'https://wiki.archlinux.org/title/plymouth#Tips_and_tricks'
    }
    check_summary
}

+enable() {
    if gum spin --title='Enabling Plymouth... ' -- \
        sudo sed -i 's/\bplymouth.enable=0\b/plymouth.enable=1/' /boot/cmdline.txt &&
        gum spin --title='Suppressing successful systemd messages... ' -- \
            sudo sed -i 's/\bsystemd.show_status=true\b/systemd.show_status=auto/' /boot/cmdline.txt; then
        :
    else
        (die '%s: failed to enable Plymouth' "$EXTENSION")
    fi
}

+disable() {
    if gum spin --title='Disabling Plymouth... ' -- \
        sudo sed -i 's/\bplymouth.enable=1\b/plymouth.enable=0/' /boot/cmdline.txt &&
        gum spin --title='Printing successful systemd messages... ' -- \
            sudo sed -i 's/\bsystemd.show_status=auto\b/systemd.show_status=true/' /boot/cmdline.txt; then
        :
    else
        (die '%s: failed to disable Plymouth' "$EXTENSION")
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
    if [ $# -gt 0 ]; then
        theme="$1"
        shift
    elif is_interactive; then
        local themes=() && readarray -t themes < <(+list)
        theme=$(
            gum choose --header="$(printf "\n%$((${GUM_CHOOSE_CURSOR_LENGTH:-2} - 1))s %s" '' "Select theme:")" \
                --selected="${themes[0]}" "${themes[@]}"
        ) || return 130
    else
        (die --code 2 'theme missing')
    fi

    gum spin --title="Setting theme to $theme... " -- \
        sudo plymouth-set-default-theme --rebuild-initrd "$theme" ||
        (die '%s: %s: failed to set theme' "$EXTENSION" "$theme")
}

+test-all() {
    with_themes +test
}

+test() {
    if gum spin --title="Starting Plymouth..." -- sudo plymouthd; then
        local theme
        theme="$(+get)"
        if gum spin --title="Showing splash theme $theme..." -- sudo plymouth show-splash; then
            if is_interactive; then
                local actions=(
                    'display-message --text=""'
                    'display-message --text="Hello World!"'
                    'system-update --progress=0'
                    'system-update --progress=10'
                    'system-update --progress=30'
                    'system-update --progress=60'
                    'system-update --progress=95'
                    'system-update --progress=100'
                    'change-mode --updates'
                    'change-mode --shutdown'
                )
                local action=${actions[0]}
                while action=$(
                    gum choose --header="$(printf "\n%$((${GUM_CHOOSE_CURSOR_LENGTH:-2} - 1))s %s" '' "Choose action:")" \
                        --selected="$action" "${actions[@]}"
                ); do
                    eval "action=($action)"
                    if ! gum spin --title="Applying ${action[*]}..." -- sudo plymouth "${action[@]}"; then
                        (die '%s: %s: %s: failed' "$EXTENSION" "$theme" "$action")
                    fi
                done
            else
                local pc
                for pc in 0 10 30 60 95 100; do
                    sudo plymouth display-message --text="$pc%"
                    sudo plymouth system-update --progress="$pc"
                    sleep 0.5
                done
                sudo plymouth display-message --text="Updating..."
                sudo plymouth change-mode --updates
                sleep 1
                sudo plymouth display-message --text="Shutting down..."
                sudo plymouth change-mode --shutdown
                sleep 1
            fi
            gum spin --title="Quitting..." -- sudo plymouth quit
        fi
    else
        (die '%s: failed to start Plymouth' "$EXTENSION")
    fi
}

+debug() {
    local line events=10 debug_file=/tmp/plymouth-debug-out
    printf -v line "\e[1m%*s\e[0m" "$(tput cols || true)" '' && line="${line// /─}"
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
    backup="$(+get)"
    while read -r theme; do
        +set "$theme"
        "$@"
    done <<<"$(+list || true)"
    +set "$backup"
}
