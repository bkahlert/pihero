# A minimal framework for writing lazily loadable extensions.
#
# - find_extensions: finds extensions at the specified locations
# - run_extension: runs the given extension with the parameters

# Prints the all found extensions files found in the given directories, their provided commands, and name in the format:
# file1:command1_a command1_b:name1
# file2:command2_a command2_b:name2
#
# Globals:
#   None
# Arguments:
#   $@ (directory ...): directories in which to search for extensions
# Outputs:
#   1: New line separated name:file entries
# Returns:
#   0: Extensions printed.
#   1: An error occurred.
find_extensions() {
    while [ $# -gt 0 ]; do
        case $1 in
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done

    local directory real_directory extension_file extension_commands extension_name
    while [ $# -gt 0 ]; do
        directory=$1 && shift
        [ -d "$directory" ] || continue
        real_directory=$(realpath "$directory") || continue
        for extension_file in "$real_directory"/*.bash; do
            [ -f "$extension_file" ] || continue
            # shellcheck disable=SC2312
            readarray -t extension_commands < <(sed -n -E 's/^\+([a-zA-Z0-9_-]+)\(\).*/\1/p' "$extension_file")
            extension_name=$(basename "${extension_file%.bash}")
            printf '%s:%s:%s\n' "$extension_file" "${extension_commands[*]}" "$extension_name"
        done
    done
}

# Runs the given command of the given extension.
# - If no command is given, but a "main" command exists, "main" is used.
# - Otherwise, the user is prompted to choose a command.
#
# If no command is given, no "main" command exists, and the STDIN is found not to be a terminal;
# this function exits with 125.
#
# If unknown parameters are provided or required parameters aren't,
# this function exits with 1.
#
# Globals:
#   None
# Arguments:
#   --interactive (boolean, default: 1 if STDIN is terminal): whether to prompt the user to choose a command, if no command is given and no "main" command exists
#   --extensions (string): extension descriptions returned by find_extensions
#   --extension (string): name of the extension to run
#   $1 (string, default: main): command to run
#   $@ (string ...): arguments to pass to the command
# Outputs:
#   Same as the executed extension command.
# Returns:
#   126: extension failed to load
#   127: extension command not found
#   130: user cancelled command prompt
#     *: Exit code of the executed extension.
run_extension() {
    local interactive=0 extensions extension
    [ ! -t 0 ] || interactive=1
    while [ $# -gt 0 ]; do
        case $1 in
        --interactive) interactive=1 && shift ;;
        --interactive=*) interactive=${1#*=} && shift ;;
        --extensions) extensions=${2?$1: parameter value not set} && shift 2 ;;
        --extensions=*) extensions=${1#*=} && shift ;;
        --extension) extension=${2?$1: parameter value not set} && shift 2 ;;
        --extension=*) extension=${1#*=} && shift ;;
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done

    [ -n "$extensions" ] || die --code 2 'extensions missing'
    [ -n "$extension" ] || die --code 2 'extension missing'

    local extension_file has_main
    local -a extension_commands=()
    local loop_extension_file loop_extension_commands loop_extension_command loop_extension_name
    while IFS=: read -r loop_extension_file loop_extension_commands loop_extension_name; do
        if [ "$loop_extension_name" = "$extension" ]; then
            extension_file=$loop_extension_file
            for loop_extension_command in $loop_extension_commands; do
                if [ "$loop_extension_command" = "main" ]; then
                    has_main=1
                else
                    extension_commands+=("$loop_extension_command")
                fi
            done
            break
        fi
    done <<<"$extensions"

    [ -n "$extension_file" ] || return 127

    local cmd
    if [ $# -gt 0 ]; then
        cmd=$1 && shift
    elif [ "$has_main" = 1 ]; then
        cmd=main
    elif [ ! "${interactive:-0}" = 0 ]; then
        local cursor_length=2 default_header
        if [ -n "$GUM_CHOOSE_CURSOR" ]; then
            local stripped
            if stripped=$(remove_ansi_escapes <<<"$GUM_CHOOSE_CURSOR"); then
                cursor_length=${#stripped}
            fi
            printf -v default_header '%*s(%d %s)' "$cursor_length" '' "${#extension_commands[@]}" "commands"
            if [ "${#extension_commands[@]}" -eq 1 ]; then
                default_header="${default_header%s}"
            fi
        fi

        cmd=$(
            GUM_CHOOSE_HEADER=${GUM_CHOOSE_HEADER-$default_header} \
                gum choose --selected="${extension_commands[0]}" "${extension_commands[@]}"
        ) || return 130
    else
        die --code 125 '%s: command missing' "$extension"
    fi

    # subshell to avoid polluting the environment due to sourcing
    (
        # shellcheck disable=SC1090
        . "$extension_file" || die --code 126 '%s: loading extension failed' "$extension_file"
        declare -F -- "+$cmd" >/dev/null || die --code 127 '%s: %s: command not found' "$extension" "$cmd"
        export EXTENSION="$extension"
        "+$cmd" "$@"
    )
}
