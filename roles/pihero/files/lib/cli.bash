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

# Checks if the first of the given arguments starts with the @ character.
# - If there is a function with that name, it's called with the remaining arguments, and
#   the script exits with the return code of that function.
# - If there is no such function, the script exits with the return code 127.
# - If there is no first argument or the first argument doesn't start with the @ character,
#   the function returns 0.
# Globals:
#   None
# Arguments:
#   $@: The arguments the program was called with.
# Outputs:
#   None
# Returns:
#   0: The first argument doesn't start with the @ character.
#   Otherwise, exits with either 127 or the return code of the function called with the remaining arguments.
exec_deeplink() {
    if [ "$#" -gt 0 ] && [ "${1:0:1}" = '@' ]; then
        declare -fp "$1" &>/dev/null || die --code 127 'Failed to find the deeplink %p' "${1:1}"
        local exit_code
        ("$@")
        exit_code=$?
        if [ "$exit_code" -ne 0 ]; then
            {
                printf 'Failed deeplink declared as: '
                declare -fp "$1"
            } >&2
        fi
        exit "$exit_code"
    fi
    return 0
}

# Prints the named icon in the given format.
# Globals:
#   None
# Arguments:
#   --format (enum ansi|template, default: ansi): The format used to print the icon.
#   $1: The name of the icon to print.
# Outputs:
#   The named icon in the given format.
# Returns:
#   0: The named icon was printed.
#   1: Unknown format, prints a space.
icon() {
    local format=ansi
    local -l name
    while [ $# -gt 0 ]; do
        case "$1" in
        --format=*)
            format="${1#*=}" && shift
            ;;
        --format)
            shift && format=${1?format: parameter value not set} && shift
            ;;
        --)
            shift && break
            ;;
        *)
            break
            ;;
        esac
    done

    local -l name=${*: -1}

    local foreground text
    case "$name" in
    create | created | creation) text='✱' foreground=3 ;;
    add | added | adding | addition) text='✚' foreground=2 ;;
    item) text='▪' foreground=8 ;;
    link) text='↗' foreground=4 ;;
    task | work) text='⚙' foreground=3 ;;
    return | exit) text='↩' foreground=1 ;;
    success | successful | succeeded) text='✔' foreground=2 ;;
    info | information) text='ℹ' foreground=7 ;;
    warning | warn) text='!' foreground=3 ;;
    error | err) text='✘' foreground=1 ;;
    failure | fail | failed) text='ϟ' foreground=1 ;;
    *) printf ' ' && return 1 ;;
    esac

    local template
    printf -v template '{{ Bold (Foreground "%d" "%s") }}' "$foreground" "$text"

    case "$format" in
    ansi) CLICOLOR_FORCE=${CLICOLOR_FORCE-1} caching -- gum format --type template "$template" ;;
    template) printf %s "$template" ;;
    *) printf ' ' && return 1 ;;
    esac
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

    local executable
    executable=$(basename "$0") || executable=${0##*/}

    local source
    source=$(basename "${BASH_SOURCE[1]}") || source=${BASH_SOURCE[1]##*/}

    local lineno=${BASH_LINENO[0]}
    if [ "$executable" = "$source" ]; then
        executable=''
    else
        executable="$executable/"
    fi

    local template=${DIE_TEMPLATE-"$(printf '%s: %s: ' "$executable$source:$lineno" "error")%s"}
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
