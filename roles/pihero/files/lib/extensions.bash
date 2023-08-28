# A minimal framework for writing bash extensions.
#
# - list_extensions: prints all found extensions
#
# - list_extension_commands: prints all commands of the given extension
#   - Commands specify the public interface of an extension.
#   - A commands is a function with a name starting with +.
#
# - locate_extension: prints the path of the given extension
#
# - run_extension_command: runs the given command of the given extension

# Prints the names of all extensions found in the given directories.
# Globals:
#   None
# Arguments:
#   $@ (directory ...): directories in which to search for extensions
# Outputs:
#   1: New line separated list of extension names.
# Returns:
#   0: At least one extension was found.
#   1: No extensions were found.
list_extensions() {
    local file found=0
    while [ $# -gt 0 ]; do
        [ -d "$1" ] || continue
        for file in "$1"/*.bash; do
            [ -f "$file" ] || continue
            found=$((found + 1))
            basename "${file%.bash}"
        done
        shift
    done
    [ "$found" -gt 0 ]
}

# Prints the path of the given extension located in one of the given directories.
# Globals:
#   None
# Arguments:
#   $1 (string): name of the extension
#   $@ (directory ...): directories in which to search for the extension
# Outputs:
#   1: Path of the extension.
# Returns:
#   0: The extension was found.
#   1: The extension wasn't found.
locate_extension() {
    local file extension=${1?extension missing} && shift
    while [ $# -gt 0 ]; do
        [ -d "$1" ] || continue
        for file in "$1"/*.bash; do
            [ -f "$file" ] || continue
            if [ "$(basename "${file%.bash}")" = "$extension" ]; then
                printf '%s\n' "$file"
                return 0
            fi
        done
        shift
    done
    return 1
}

# Prints the commands provided by the given extension located in one of the given directories.
# Globals:
#   None
# Arguments:
#   $1 (string): name of the extension
#   $@ (directory ...): directories in which to search for the extension
# Outputs:
#   1: New line separated list of extension names.
# Returns:
#   0: At least one command was found.
#   1: No commands were found.
#   128: The extension wasn't found.
list_extension_commands() {
    local file extension=${1?extension missing} && shift
    file=$(locate_extension "$extension" "$@") || die --code 128 "extension $extension not found"

    (
        # shellcheck disable=SC1090
        source "$file"

        local found=0
        while read -r function_declaration; do
            local function_with_flags="${function_declaration#declare -f}"
            local function_name="${function_with_flags#* }"
            [ "${function_name:0:1}" = '+' ] || continue
            found=$((found + 1))
            printf '%s\n' "${function_name:1}"
        done < <(declare -F)
        [ "$found" -gt 0 ]
    )
}

# Runs the given command of the given extension located in one of the given directories.
# Globals:
#   None
# Arguments:
#   $1 (string): name of the extension
#   $2 (string): name of the command
#   $@ (directory ...): directories in which to search for extensions
#   -- (string): The arguments that follow the first "--" are passed to the extension command.
# Outputs:
#   Same as the executed extension command.
# Returns:
#   Exit code of the executed extension.
#   127: The extension command wasn't found.
#   128: The extension wasn't found.
run_extension_command() {
    local extension=${1?extension missing} && shift
    local command=${1?command missing} && shift
    local args=() dirs=()
    while [ $# -gt 0 ]; do
        case "$1" in
        --)
            shift && break
            ;;
        *)
            dirs+=("$1") && shift
            ;;
        esac
    done
    args=("$@")

    file=$(locate_extension "$extension" "${dirs[@]}") || die --code 128 "extension $extension not found"

    (
        # shellcheck disable=SC1090
        source "$file"
        declare -F -- "+$command" >/dev/null || die --code 127 "command $command not found"
        "+$command" "${args[@]}"
        exit $?
    )
}
