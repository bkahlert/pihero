# Returns whether interaction with the user is possible.
# Globals:
#   None
# Arguments:
#   None
# Outputs:
#   None
# Returns:
#   0: Interaction with the user is possible.
#   1: Interaction with the user is impossible.
is_interactive() {
    test -t 0
}

# Returns whether the outputs are connected to a terminal.
# Globals:
#   None
# Arguments:
#   None
# Outputs:
#   None
# Returns:
#   0: Both outputs are connected to a terminal.
#   1: At least one output is redirected.
is_tty() {
    test -t 1 && test -t 2
}

# Prints the given text—if connected to a terminal—styled with `gum style`, or
# as is otherwise.
# Globals:
#   None
# Arguments:
#   Same as `gum style`, run `gum style --help` for more information.
# Outputs:
#   If connected to a terminal, the given text styled with `gum style`.
#   Otherwise, the given text as is.
# Returns:
#   If connected to a terminal, same as `gum style`.
#   Otherwise, 0.
style() {
    local text
    if is_tty; then
        gum style "$@"
    else
        while [ $# -gt 0 ]; do
            case "$1" in
            --)
                shift && break
                ;;
            --*)
                shift
                ;;
            *)
                break
                ;;
            esac
        done
        for text in "$@"; do
            printf '%s\n' "$text"
        done
    fi
}

# Prints the given error message to STDERR and exits with the given code.
# Globals:
#   DIE_TEMPLATE (string, default: "$(basename $0): error: %s"): The template used to format the error message, see `gum format --help` for more information.
# Arguments:
#   code (int, default: 1): exit code
#   $@: printf format and arguments; the result represents the error message used for the DIE_TEMPLATE
#       In addition to the usual printf format specifiers, the following extensions are supported:
#       - %p: same as %s, but semantically highlighted to denote a parameter
# Outputs:
#   STDERR: error message
# Returns:
#   Exits with the given code, if specified, or 1.
die() {
    local code=1
    local template=${DIE_TEMPLATE-"$(printf '%s: %s: ' "$(basename "$0")" "error")%s"}
    while [ $# -gt 0 ]; do
        case "$1" in
        --)
            shift && break
            ;;
        --code)
            shift && code=${1?code: parameter value not set} && shift
            ;;
        *)
            break
            ;;
        esac
    done

    local error_message
    if [ $# = 0 ]; then
        error_message='An error occurred in .'
    else
        local format=$1 && shift
        # transform %p to %s
        format=$(sed -E 's|%([^%p]*)p|\\e[3m%\1s\\e[23m|g' <<<"$format")
        # shellcheck disable=SC2059
        printf -v error_message -- "$format" "$@"
    fi
    {
        gum format --type template "${template//%s/$error_message}"
        printf '\n'
    } >&2
    exit "$code"
}

# Prints the content of the given files with ANSI escape sequences removed.
# Globals:
#   None
# Arguments:
#   $@ (file ...): files to read
# Outputs:
#   File contents with ANSI escape sequences removed
# Returns:
#   0: The files contents were stripped of ANSI escape sequences.
#   1: An error occurred.
remove_ansi_escapes() {
    local pattern
    local patterns=(
        '\x1b][[:digit:]]*\;[^\x1b]*\x1b\\' # OSC escape sequences
        '\x1b[@-Z\\-_]'                     # Fe escape sequences
        '\x1b[ -/][@-~]'                    # 2-byte sequences
        '\x1b[[0-?]*[ -/]*[@-~]'            # CSI escape sequences
    )
    printf -v pattern 's|%s||g;' "${patterns[@]}"
    LC_ALL=C sed "$pattern"
}

export GUM_CHOOSE_ITEM_FOREGROUND=''

usage() {
    local name="argument" args=() options=()
    while [ $# -gt 0 ]; do
        case "$1" in
        --name)
            shift && name=${1?name: parameter value not set} && shift
            ;;
        --)
            shift && break
            ;;
        *)
            options+=("$1") && shift
            ;;
        esac
    done
    args=("$@")

    {
        printf '{{ Bold "Usage: %s" }}' "$(basename "$0")"
        [ "${#args[@]}" = 0 ] || printf ' {{ Bold "%s" }}' "${args[@]}"
        printf ' {{ Bold (Italic "%s") }}\n' "$name"
        printf '\n'
        printf '{{ Bold "%s:" }}\n' "${name^}s"
        [ "${#options[@]}" = 0 ] || printf '  %s\n' "${options[@]}"
    } | gum format --type template
}
