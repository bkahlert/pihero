#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" || true)")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

+diag() {
    check_start "HDMI diagnostics"

    if check_unit "VideoCore GPU" vcgencmd version; then
        local hdmi_group hdmi_mode hdmi_cvt dtoverlay=()
        read_ini --section=all hdmi_group hdmi_mode hdmi_cvt dtoverlay </boot/config.txt

        if check_unit "manual HDMI settings" test -n "$hdmi_group" -a -n "$hdmi_mode"; then
            check "hdmi_group '$hdmi_group' is valid" test "$hdmi_group" -ge 0 -a "$hdmi_group" -le 2
            check "hdmi_mode '$hdmi_mode' is valid" test "$hdmi_mode" -ge 0 -a "$hdmi_mode" -le 87

            if ! check --brief "vc4-fkms-v3d is configured" array_contains dtoverlay 'vc4-fkms-v3d'; then
                # shellcheck disable=SC2016
                check_raw '%s\n' '```' \
                    'Manual HDMI settings are only supported by the legacy FKMS, and:' \
                    'the firmware-based graphics driver.' \
                    '— raspberrypi.com/documentation/computers/config_txt.html#raspberry-pi-4-hdmi-pipeline' \
                    'The settings should be either removed from, or' \
                    '`dtoverlay=vc4-fkms-v3d` should be added to /boot/config.txt' \
                    '```'
            fi

            if check_unit "custom CVT mode" test "$hdmi_group" = 2 -a "$hdmi_mode" = 87; then
                check "custom CVT mode '$hdmi_cvt' is set" test -n "$hdmi_cvt"
            fi
        fi
    fi

    if check_unit "display-manager" systemctl -q is-enabled "display-manager.service"; then
        check "is running" systemctl -q is-active "display-manager.service"
        if ! check "X log contains no errors" ! grep -q '] (EE)' /var/log/Xorg.0.log; then
            local error_lines=()
            readarray -t error_lines < <(grep '] (EE)' /var/log/Xorg.0.log || true)
            check_raw '%s\n' '```' 'ERRORS:' "${error_lines[@]}" '```'
        fi
    fi

    # shellcheck disable=SC2016
    {
        check_further '- hdmi_group / hdmi_mode are explained at\n  [%s](%s)' 'raspberrypi.com' 'https://www.raspberrypi.com/documentation/computers/config_txt.html#custom-mode'
        check_further '- check the hdmi_* options in %s\n' /boot/config.txt
        check_further_unit 'vcgencmd command'
        check_further '- list commands: `%s`' 'vcgencmd commands'
        check_further '- list integer config options: `%s`' 'vcgencmd get_config int'
        check_further '- list string config options: `%s`' 'vcgencmd get_config str'
        check_further '- get config by name: `%s`' 'vcgencmd get_config name'
        check_further_unit 'find modes'
        check_further '- `%s`' 'raspinfo'
        check_further '- dump EDID data:\n```\n%s\n```' 'sudo apt-get install -y edid-decode'$'\n''tvservice -d edit.dat'$'\n''edid-decode edit.dat'
    }
    check_summary
}

# Prints the content of the X11 conf file if it exists.
# Globals:
#   None
# Arguments:
#   None
# Outputs:
#   1: The contents of the X11 conf file if it exists.
# Returns:
#   0: If the X11 conf file exists.
#   1: If the X11 conf file does not exist.
+read-x11-conf() {
    local x11_conf_file=/etc/X11/xorg.conf.d/10-monitor.conf
    if [ -f "$x11_conf_file" ]; then
        cat "$x11_conf_file"
    else
        return 1
    fi
}

# Saves the mode corresponding to
# the `hdmi_cvt` value from the given config file to an X11 conf file if
# a custom mode is set, that is `hdmi_group=2` and `hdmi_mode=87` are set.
# Otherwise, the X11 conf file is removed.
+sync-x11-conf() {
    local config_file=${1:-/boot/config.txt}
    local x11_conf_file=/etc/X11/xorg.conf.d/10-monitor.conf
    local custom_modeline
    if custom_modeline=$(+get-custom-modeline "$config_file"); then
        if printf '%s\n' "$custom_modeline" | save-custom-x11-config; then
            printf 'Saved custom mode to %s\n' "$x11_conf_file"
            if gum confirm --default "Reboot?"; then
                sudo reboot
            fi
        fi
    else
        if [ -f "$x11_conf_file" ]; then
            if ! gum confirm --default "Remove $x11_conf_file?"; then
                return 130
            fi
            if sudo rm "$x11_conf_file" || die 'failed to remove %s' "$x11_conf_file"; then
                printf 'Removed %s\n' "$x11_conf_file"
                if gum confirm --default "Reboot?"; then
                    sudo reboot
                fi
            fi
        fi
    fi
}

# Prints the `hdmi_cvt` value from the given config file if
# a custom mode is set, that is `hdmi_group=2` and `hdmi_mode=87` are set.
# Globals:
#   None
# Arguments:
#   $1 (file, default: /boot/config.txt): The config file to read from.
# Outputs:
#   1: The `hdmi_cvt` value.
#   2: Error message, if no custom mode was found.
# Returns:
#   0: If a custom mode was found.
#   1: If no custom mode was found.
#   2: Illegal usage
+get-custom-mode() {
    local config_file=${1:-/boot/config.txt}
    [ -f "$config_file" ] || die --code 2 '%s: file not found' "$config_file"
    local hdmi_group hdmi_mode hdmi_cvt
    read_ini --section=all hdmi_group hdmi_mode hdmi_cvt <"$config_file"
    if [ "$hdmi_group" = 2 ] && [ "$hdmi_mode" = 87 ]; then
        printf '%s\n' "$hdmi_cvt"
    else
        return 1
    fi
}

# Prints the modeline corresponding to
# the `hdmi_cvt` value from the given config file if
# a custom mode is set, that is `hdmi_group=2` and `hdmi_mode=87` are set.
# Globals:
#   None
# Arguments:
#   $1 (file, default: /boot/config.txt): The config file to read from.
# Outputs:
#   1: The modeline corresponding to the `hdmi_cvt` value.
#   2: Error message, if no custom mode was found.
# Returns:
#   0: If a custom mode was found.
#   1: If no custom mode was found.
#   2: Illegal usage
+get-custom-modeline() {
    local config_file=${1:-/boot/config.txt}
    local cvt
    if cvt=$(+get-custom-mode "$config_file"); then
        local x y refresh
        read -r x y refresh <<<"$cvt"
        if [ -z "$x" ] || [ "$x" -le 0 ]; then
            die --code 1 '%s: invalid x value' "$x"
        fi
        if [ -z "$y" ] || [ "$y" -le 0 ]; then
            die --code 1 '%s: invalid y value' "$y"
        fi
        if [ -n "$refresh" ] || [ ! "$refresh" = 0 ]; then
            cvt "$x" "$y" "$refresh"
        else
            cvt "$x" "$y"
        fi
    else
        return 1
    fi
}

# Saves a custom X11 conf file based on the modeline
# provided via STDIN.
# Globals:
#   None
# Arguments:
#   None
# Inputs:
#   0: The modeline to save.
# Outputs:
#   1: The X11 conf file.
# Returns:
#   0: If the X11 conf file was saved.
#   1: An error occurred.
#   2: Illegal usage
# Example:
# # 800x480 32.01 Hz (CVT) hsync: 15.88 kHz; pclk: 15.75 MHz
# Modeline "800x480_32.50" 15.75 800 824 896 992 480 483 493 496 -hsync +vsync
save-custom-x11-config() {
    local quoted_name_and_mode quoted_name
    local line
    while read -r line; do
        case "$line" in
        Modeline*)
            quoted_name_and_mode=${line#Modeline }
            quoted_name=${quoted_name_and_mode%% *}
            break
            ;;
        *) continue ;;
        esac
    done

    local conf_dir=/etc/X11/xorg.conf.d
    local conf_file="$conf_dir/10-monitor.conf"
    local conf='Section "Monitor"
    Identifier "HDMI-1"
    Modeline '"$quoted_name_and_mode"'
EndSection

Section "Screen"
    Identifier "Screen0"
    Monitor "HDMI-1"
    DefaultDepth 24
    SubSection "Display"
        Modes '"$quoted_name"'
    EndSubSection
EndSection

Section "Device"
    Identifier "Device0"
    Driver "modesetting"
EndSection'

    if ! gum confirm --default "Save to $conf_file?"$'\n'$'\n'"$conf"; then
        return 130
    fi

    sudo mkdir -p "$conf_dir" || die 'failed to create directory %s' "$conf_dir"
    if ! printf '%s\n' "$conf" | sudo tee "$conf_file" >/dev/null; then
        die 'failed to save configuration to %s' "$conf_file"
    fi
}

declare default_modelines=(
    '"1920x1080_60.00" 148.50 1920 2008 2052 2200 1080 1084 1089 1125 +hsync +vsync'
    '"1360x768_60.00"   85.75  1366 1436 1579 1792  768 771 774 798 +hsync +vsync'
    '"1280x720_60.00" 74.25 1280 1390 1430 1650 720 725 730 750 +hsync +vsync'
)
