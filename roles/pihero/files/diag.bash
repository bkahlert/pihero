#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}" || true)")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

# Diagnostics consisting of the diagnostics of all discovered extensions
+main() {
    if [ -t 2 ]; then
        trap 'tput cnorm >&2 || true' EXIT
        tput civis >&2 || true
    fi

    local extension_dirs=("$SCRIPT_DIR/..") extensions
    extensions=$(run_caching find_extensions "${extension_dirs[@]}") || die '%s: loading extensions failed' "${extension_dirs[*]}"

    local -a extensions_with_diag_command=()
    local curr_ext_file curr_ext_commands curr_ext_command curr_ext_name
    while IFS=: read -r curr_ext_file curr_ext_commands curr_ext_name; do
        [ ! "$curr_ext_name" = "diag" ] || continue
        for curr_ext_command in $curr_ext_commands; do
            if [ "$curr_ext_command" = "diag" ]; then
                extensions_with_diag_command+=("$curr_ext_name")
                continue 2
            fi
        done
    done <<<"$extensions"

    local exit_code=0 summary=()
    local -i columns && columns=$(tput cols) || columns=80
    local extension
    for extension in "${extensions_with_diag_command[@]}"; do
        local result
        COLUMNS=$columns run_command_line "$0" "$extension" diag
        result=$?
        if [ -t 2 ]; then
            tput civis >&2 || true
        fi
        [ "$result" -le "$exit_code" ] || exit_code=$result
        summary+=("$(summary_component "$result" "$extension")")
    done

    case ${CHECKS_OUTPUT_FORMAT:-ansi} in
    none) : ;;
    markdown) gum format --type template '' " $(hero_template --mood="$exit_code" || true) ${summary[*]}" '' '' ;;
    *) gum format --type template '' " $(hero_template --mood="$exit_code" || true) ${summary[*]}" '' '' ;;
    esac

    exit "$exit_code"
}
summary_component() {
    local result=${1?}
    local title=${2?}
    local icon
    case "$result" in
    0) icon=$(icon_template success || true) ;;
    1) icon=$(icon_template error || true) ;;
    2) icon=$(icon_template failure || true) ;;
    *) icon='?' ;;
    esac
    printf '  {{ Bold "%s" }} %s\n' "$title" "$icon"
}

run_command_line() {
    local -i width=${COLUMNS:-80}
    local -i mx=4 px=1
    local -i left_offset=$((mx + 1 + px))
    local -i outer_width=$((width - (mx + px + mx + px)))
    local -i inner_width=$((width - (mx + 1 + px + mx + 1 + px)))
    local title="${*##*/}..."
    local exit_code outfile errfile
    outfile=$(mktemp) || die "Failed to create output file."
    errfile=$(mktemp) || die "Failed to create error file."

    if [ -t 2 ]; then
        printf '\n' >&2
        gum spin --title="$title" --spinner.align=right --spinner.width="$left_offset" -- \
            env COLUMNS=$((inner_width)) bash -c "$(printf "%q " "$@") 2>'$errfile' >'$outfile'"
        exit_code=$?
        tput cuu1 >&2 || true
        tput civis >&2 || true
    else
        env COLUMNS=$((inner_width)) "$@" 2>"$errfile" >"$outfile"
        exit_code=$?
    fi

    local style_args=(
        --border rounded
        --margin "0 $mx"
        --padding "0 $px"
        --width "$((outer_width))"
    )

    if [ "$exit_code" -eq 0 ]; then
        local formatted
        [ ! -f "$outfile" ] || formatted=$(format <"$outfile")
        if [ -n "$formatted" ]; then
            printf '\n'
            gum style "${style_args[@]}" --border-foreground 2 "$formatted"
        fi
        exit_code=0
    else
        local err_output
        err_output=$(<"$errfile")
        if [ -z "$err_output" ]; then
            local formatted
            [ ! -f "$outfile" ] || formatted=$(format <"$outfile")
            if [ -n "$formatted" ]; then
                printf '\n'
                gum style "${style_args[@]}" --border-foreground 1 "$formatted"
            fi
            exit_code=1
        else
            printf '\n'
            gum format --type template \
                "$(printf '%*s' "$mx" '') $(icon_template failure || true) {{ Bold \"${*##*/} failed\" }} " ''
            gum style "${style_args[@]}" --border-foreground 1 "${err_output/#$'\n'/}"
            exit_code=2
        fi
    fi
    rm "$outfile" "$errfile" 2>/dev/null || true
    return "$exit_code"
}
