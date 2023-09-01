#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
. "$SCRIPT_DIR/lib/lib.bash"

# Diagnostics consisting of the diagnostics of all discovered extensions
+main() {
    trap 'tput cnorm || true' EXIT
    tput civis || true

    local extension_dirs=("$SCRIPT_DIR/..") extensions
    extensions=$(caching -- get_extensions "${extension_dirs[@]}") || die "Failed to load the extensions at %p." "${extension_dirs[*]}"

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

    local columns && columns=$(tput cols) || columns=80
    local extension
    for extension in "${extensions_with_diag_command[@]}"; do
        local result
        printf '\n'
        run_diag "$extension" "$columns"
        result=$?
        tput civis || true
        [ "$result" -le "$exit_code" ] || exit_code=$result

        summary+=(
            "  {{ Bold \"$extension\" }} $(case "$result" in
                0) icon --format template success || true ;;
                1) icon --format template error || true ;;
                2) icon --format template failure || true ;;
                *) printf '?' ;;
                esac)"
        )
    done

    CLICOLOR_FORCE=${CLICOLOR_FORCE-1} gum format --type template \
        '' " $(hero --mood="$exit_code" --format template || true) ${summary[*]}" '' ''

    exit "$exit_code"
}

run_diag() {
    local extension=${1:?} && shift
    local -i width=${1:?} && shift
    local -i mx=4 px=1
    local -i left_offset=$((mx + 1 + px)) right_offset=$((mx + 1 + px))
    local -i inner_width=$((width - left_offset - right_offset))
    local title="${extension^} diagnostics..."
    local exit_code outfile errfile
    outfile=$(mktemp) || die "Failed to create output file."
    errfile=$(mktemp) || die "Failed to create error file."
    gum spin --title="$title" --spinner.align=right --spinner.width="$left_offset" -- \
        bash -c "COLUMNS=$((inner_width)) $0 '$extension' diag 2>'$errfile' >'$outfile'"
    exit_code=$?
    tput civis >&2 || true

    local style_args=(
        --border rounded
        --margin "0 $mx"
        --padding "0 $px"
        --width "$((inner_width))"
    )

    if [ "$exit_code" -eq 0 ]; then
        gum style "${style_args[@]}" --border-foreground 2 "$(<"$outfile")"
        exit_code=0
    else
        local err_output
        err_output=$(<"$errfile")
        if [ -z "$err_output" ]; then
            gum style "${style_args[@]}" --border-foreground 1 "$(<"$outfile")"
            exit_code=1
        else
            CLICOLOR_FORCE=${CLICOLOR_FORCE-1} gum format --type template \
                "$(printf '%*s' "$mx" '') $(icon --format template failure || true) {{ Bold \"$extension diagnostics failed\" }} " ''
            gum style "${style_args[@]}" --border-foreground 1 "${err_output/#$'\n'/}"
            exit_code=2
        fi
    fi
    rm "$outfile" "$errfile" 2>/dev/null || true
    return "$exit_code"
}
