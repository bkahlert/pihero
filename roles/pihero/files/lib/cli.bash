# Prints the given error message to STDERR and exits with the given code.
# Globals:
#   DIE_TEMPLATE (string, default: "$(basename $0): error: %s"): The template used to format the error message, see `gum format --help` for more information.
# Arguments:
#   --code (int, default: 1): exit code
#   $@ (string ...): printf format and arguments; the result represents the error message used for the DIE_TEMPLATE
# Outputs:
#   STDERR: error message
# Returns:
#   Exits with the given code, if specified, or 1.
die() {
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

    local code=1
    while [ $# -gt 0 ]; do
        case $1 in
        --code) code=${2?$1: parameter value not set} && shift 2 ;;
        --code=*) code=${1#*=} && shift ;;
        *) break ;;
        esac
    done

    local error_message
    if [ $# = 0 ]; then
        error_message='unknown error in '"$executable$source:$lineno"
    else
        local format=$1 && shift
        # shellcheck disable=SC2059
        printf -v error_message -- "$format" "$@"
    fi
    {
        gum format --type template "${template//%s/$error_message}"
        printf '\n'
    } >&2
    exit "$code"
}

# Prints usage information in the format:
# Usage: command --foo bar baz
# Bars: value1 value2
# Bars: value1 value2
#
# Globals:
#   USAGE_HEADER: If set, the value is formatted with `gum format --type template` and printed before the usage information.
# Arguments:
#   --header (string, optional): If set, the value is formatted with `gum format --type template` and printed before the usage information.
#   --command (string, default: basename $0): The name of the command.
#   FLAGS... : The flags to be displayed right next to the command.
#   --arg name [VALUES...]: The name of the argument.
usage() {
    local header=${USAGE_HEADER-} command
    command=$(basename "$0") || command=${0##*/}
    while [ $# -gt 0 ]; do
        case $1 in
        --header) header=${2?$1: parameter value not set} && shift 2 ;;
        --header=*) header=${1#*=} && shift ;;
        --command) command=${2?$1: parameter value not set} && shift 2 ;;
        --command=*) command=${1#*=} && shift ;;
        *) break ;;
        esac
    done

    local arg
    local -a flags=() args=()
    local -A values=()
    while [ $# -gt 0 ]; do
        case $1 in
        --arg) arg=${2?$1: parameter value not set} && args+=("$arg") && shift 2 ;;
        --arg=*) arg=${1#*=} && args+=("$arg") && shift ;;
        *) if [ -z "$arg" ]; then flags+=("$1") && shift; else values[$arg]+="  $1"$'\n' && shift; fi ;;
        esac
    done

    {
        printf 'Usage: %s' "$command"
        [ "${#flags[@]}" -eq 0 ] || printf ' %s' "${flags[@]}"
        for arg in "${args[@]}"; do
            if [ -n "${values[$arg]}" ]; then
                printf ' <%s>' "$arg"
            else
                printf ' %s' "$arg"
            fi
        done
        printf '\n'
        [ -z "$header" ] || printf '\n%s\n' "$header"
        for arg in "${args[@]}"; do
            [ -n "${values[$arg]}" ] || continue

            printf '\n'
            printf '%s:\n' "$(pluralize "${arg^}" || true)"
            printf '%s' "${values[$arg]}"
        done
    } | gum format --type template
}

# Formats a string using a template using `gum format --type template` the
# same way `gum style` does.
# That is, there's no check for a TTY on STDOUT, and the result can be captured
# and composed just as it's the case with `gum style`.
#
# Globals:
#   None
# Arguments:
#   $@ (mixed ...): The templates to format. If not template is given, STDIN is used.
# Outputs:
#   1: Formatted template. If more than one template is given, the formatted templates are separated by a newline.
# Returns:
#   See gum format --type template
format() {
    local sed_args=(
        -e '1s/^\^\D\x08\{0,2\}//' # removes EOF and up to two backspaces that showed up on macOS + script when it's part of a pipe
        -e 's/\r$//'               # remove carriage returns the terminal adds when it encounters a line feed
    )

    local output exit_code
    output=$(mktemp) || die 'Failed to create temporary file'
    if [ $# -gt 0 ]; then
        run_with_tty gum format --type=template -- "$@" >"$output"
        exit_code=$?
    else
        local input
        input=$(mktemp) || die 'Failed to create temporary file'
        cat >"$input" || die 'Failed to read from STDIN'
        run_with_tty bash -c "gum format --type=template <'$input'" >"$output"
        exit_code=$?
        rm "$input" || die 'Failed to remove temporary file'
    fi

    sed "${sed_args[@]}" <"$output"
    rm "$output" || die 'Failed to remove temporary file'
    return "$exit_code"
}

# Runs the given command with the given arguments
# using a "script"-based pseudo teletype (TTY).
#
# Globals:
#   SHELL: The shell used by the script to run the command line.
# Arguments:
#   $1 (string): The command to run.
#   $@ (mixed ...): The arguments to pass to the command.
# Outputs:
#   1: Output of the emulated terminal, which can differ from the output of the command.
#      For example, line feeds (\n) might be converted to carriage return + line feed (\r\n).
# Returns:
#   0: Successful start of the script command and successful execution.
#   1: Failed start of the script command or failed execution.
#   2-128: Successful start of the script command and failed execution.
#   129-255: 128 + signal number that interrupted the execution.
run_with_tty() {
    case $OSTYPE in
    linux*)
        local command
        if printf -v command '%q ' "$@"; then
            script --command "${command% }" --return --quiet /dev/null
        else
            (die 'Failed to format command')
        fi
        ;;
    darwin* | *bsd*)
        script -q /dev/null "$@"
        ;;
    *) (die '%s: operating system unsupported' "$OSTYPE") ;;
    esac
}

# Prints the given English nouns in their plural form according to
# a set of simple rules.
#
# Globals:
#   None
# Arguments:
#   --number (int, default: 2): if set to 1, the nouns are printed unmodified
# Outputs:
#   None
# Returns:
#   0: Interaction with the user is possible.
#   1: Interaction with the user is impossible.
pluralize() {
    local number=2
    while [ $# -gt 0 ]; do
        case $1 in
        --number) number=${2?$1: parameter value not set} && shift 2 ;;
        --number=*) number=${1#*=} && shift ;;
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done

    local noun
    for noun in "$@"; do
        if [ "$number" -eq 1 ]; then
            printf '%s\n' "$noun"
        else
            case $noun in
            *s | *x | *z | *ch | *sh) printf '%ses\n' "$noun" ;;
            *ay | *ey | *iy | *oy | *uy) printf '%ss\n' "$noun" ;;
            *y) printf '%sies\n' "${noun%y}" ;;
            '') ;;
            *) printf '%ss\n' "$noun" ;;
            esac
        fi
    done
}

# Returns whether the given variable is declared with the optional attributes.
# Globals:
#   None
# Arguments:
#   $1 (string): The name of the variable to check.
#   $@ (string ...): The optional attributes to check for.
# Outputs:
#   2: Error message
# Returns:
#   0: The variable is declared.
#   1: The variable is not declared.
#   2: Illegal usage
is_declared() {
    local variable
    while [ $# -gt 0 ]; do
        case $1 in
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done

    if [ $# -gt 0 ]; then
        variable=$1 && shift
    else
        die --code 2 '%s: variable name missing' "${FUNCNAME[0]}"
    fi

    local declaration
    if declaration=$(declare -p "$variable" 2>/dev/null); then
        local attributes=${declaration#declare -} && attributes=${attributes%% *}
        while [ $# -gt 0 ]; do
            local -i i=0
            while true; do
                [ ! "${attributes:$i:1}" = "$1" ] || break
                i=$((i + 1))
                [ "$i" -lt "${#attributes}" ] || return 1
            done
            shift
        done
        return 0
    else
        return 1
    fi
}

# Returns whether each of the given variables is declared as an array.
# Globals:
#   None
# Arguments:
#   $@ (string ...): The names of the variables to check.
# Outputs:
#   2: Error message
# Returns:
#   0: All variables are declared as arrays.
#   1: At least one variable is not declared as an array.
#   2: Illegal usage
is_array() {
    while [ $# -gt 0 ]; do
        is_declared "$1" a || return 1
        shift
    done
    return 0
}

# Returns whether the given variable contains all given values.
# Globals:
#   None
# Arguments:
#   $1 (string): The name of the variable to check.
#   $@ (string ...): The values to check for.
# Outputs:
#   2: Error message
# Returns:
#   0: The variable contains all given values.
#   1: The variable doesn't contain all given values.
#   2: Illegal usage
array_contains() {
    [ $# -gt 0 ] || die --code 2 '%s: array name missing' "${FUNCNAME[0]}"
    local -n array=$1 && shift
    while [ $# -gt 0 ]; do
        local item
        for item in "${array[@]}"; do
            if [ "$item" = "$1" ]; then
                shift && continue 2
            fi
        done
        return 1
    done
    return 0
}

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

# Checks if the first of the given arguments starts with the @ character.
# - If there is a function with that name, it's called with the remaining arguments, and
#   the script exits with the return code of that function.
# - If there is no such function, the script exits with the return code 127.
# - If there is no first argument or the first argument doesn't start with the @ character,
#   the function returns 0.
# Globals:
#   None
# Arguments:
#   $@ (string ...): The arguments the program was called with.
# Outputs:
#   None
# Returns:
#   0: The first argument doesn't start with the @ character.
#   Otherwise, exits with either 127 or the return code of the function called with the remaining arguments.
exec_deeplink() {
    if [ $# -gt 0 ] && [ "${1:0:1}" = '@' ]; then
        declare -fp "$1" &>/dev/null || die --code 127 '%s: deeplink not found' "${1:1}"
        local exit_code
        ("$@")
        exit_code=$?
        #        if [ "$exit_code" -ne 0 ]; then
        #            {
        #                printf 'Failed deeplink declared as: '
        #                declare -fp "$1"
        #            } >&2
        #        fi
        exit "$exit_code"
    fi
    return 0
}

# Prints a `gum format --type template`-processable icon with the given name.
# Globals:
#   None
# Arguments:
#   $1: The name of the icon to print.
# Outputs:
#   The named icon in the given format.
# Returns:
#   0: The named icon was printed.
#   2: Bad usage
icon_template() {
    while [ $# -gt 0 ]; do
        case $1 in
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done

    local -l name
    if [ $# -gt 0 ]; then
        name=$1 && shift
    else
        die --code 2 'name missing'
    fi

    local foreground text
    case $name in
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

    printf '{{ Bold (Foreground "%d" "%s") }}' "$foreground" "$text"
}

# Reads the given files using cat and converts each character
# to its Unicode escape sequence,
# for example: foo → \u0066\u006f\u006f.
unicode_encode() {
    local char
    while IFS= read -r -n1 char; do
        [ -n "$char" ] || continue
        printf '\\u%04x' "'$char"
    done < <(cat "$@" || true)
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
        # OSC escape sequences not supported as they require greedy matching
        '\x1b[@-Z\\-_]'           # Fe escape sequences
        '\x1b[ -/][@-~]'          # 2-byte sequences
        '\x1b\[[0-?]*[ -/]*[@-~]' # CSI escape sequences
    )
    printf -v pattern 's|%s||g;' "${patterns[@]}"
    LC_ALL=C sed "$pattern"
}

# Reads the STDIN as an INI file,
# and for each given option, for which a value is encountered,
# a variable with the name of the option is set to that value.
#
# If a variable with the name of a given option is declared
# as an array, values are appended to that array.
# Otherwise, the variable is set to the last value encountered.
#
# Globals:
#   None
# Arguments:
#   --section (string, optional): The name of the section the given options belong to.
#   $@ (string...): The options to read.
# Inputs:
#   0: The contents of the INI file.
# Outputs:
#   2: Error message, if the given option was not found.
# Returns:
#   0: If the INI file was read successfully.
#   1: Unknown error
#   2: Illegal usage
read_ini() {
    local __section __in_section=1
    while [ $# -gt 0 ]; do
        case $1 in
        --section) __section=${2?$1: parameter value not set} && shift 2 ;;
        --section=*) __section=${1#*=} && shift ;;
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done
    local __line
    while read -r __line; do
        case "$__line" in
        *=*)
            [ -n "$__in_section" ] || continue
            local __o=${__line%%=*}
            local __v=${__line#*=}
            local __option
            for __option in "$@"; do
                if [ "$__option" = "$__o" ]; then
                    if is_declared "$__option" a; then
                        local -n __var=$__option
                        __var+=("$__v")
                    else
                        printf -v "$__option" '%s' "$__v"
                    fi
                    break
                fi
            done
            ;;
        \[*\]*)
            [ -n "$__section" ] || continue
            local __s=${__line#*[} && __s=${__s%]*}
            if [ "$__s" = "$__section" ]; then
                __in_section=1
            else
                __in_section=''
            fi
            ;;
        *) ;;
        esac
    done
}
