# Runs the given command line only if there is no cached
# output for the given cache keys and command line.
# If there is, the cached output is returned instead.
# If the command line does not complete with exit code 0, the output is not cached.
#
# Globals:
#   None
# Arguments:
#   --debug (boolean, default: 0): if set to non-zero, prints debug information to STDERR.
#   $@ (string ...): keys that define the validity of the cache file.
#   -- (string): The arguments that follow the first "--" make up the command line.
# Outputs:
#   1: Output of the command line, if there is no cached output. Otherwise, the cached output.
#   2: Debug information, if --debug is set to non-zero.
# Returns:
#   The exit code of the command line, if it ran. Otherwise, 0.
caching() {
    local debug=0 start_time=$((${EPOCHREALTIME/./} / 1000))
    local -a keys=()

    # add explicit cache keys
    while [ $# -gt 0 ]; do
        case "$1" in
        --debug=*)
            debug="${1#*=}" && shift
            ;;
        --debug)
            shift && debug=${1?debug: parameter value not set} && shift
            ;;
        --)
            shift
            break
            ;;
        *)
            keys+=("$1")
            shift
            ;;
        esac
    done

    [ $# -gt 0 ] || die "The command line to run is missing. At least a command must be provided."

    [ "$debug" = 0 ] || printf 'caching: command: %s\n' "$*" >&2

    # add command line as cache key
    keys+=("$@")

    local cache_file exit_code
    if cache_file=$(_cache_file "${keys[@]}"); then
        [ "$debug" = 0 ] || printf 'caching: cache file: %s\n' "$cache_file" >&2
        if [ -e "$cache_file" ]; then
            [ "$debug" = 0 ] || printf 'caching: cache hit\n' >&2
            cat "$cache_file"
            exit_code=0
        else
            [ "$debug" = 0 ] || printf 'caching: cache miss\n' >&2
            local output exit_code
            output=$("$@")
            exit_code=$?
            if [ "$exit_code" -eq 0 ]; then
                [ "$debug" = 0 ] || printf 'caching: cache update\n' >&2
                printf '%s\n' "$output" | tee "$cache_file"
            else
                [ "$debug" = 0 ] || printf 'caching: output dismissal\n' >&2
                printf '%s\n' "$output"
            fi
        fi
    else
        [ "$debug" = 0 ] || printf 'caching: caching impossible\n' >&2
        "$@"
    fi
    if [ ! "$debug" = 0 ]; then
        local end_time=$((${EPOCHREALTIME/./} / 1000))
        printf 'caching: summary\n - command: %s\n - exit code: %d\n - runtime: %s ms\n' \
            "$*" "$exit_code" "$((end_time - start_time))" >&2
    fi
    return "$exit_code"
}

# Prints the path to a cache file for the given keys.
# If the cache file doesn't exist, it can be used to the result of the computation.
# If the cache file exists, it can be read to get the result of the last computation.
#
# Globals:
#   None
# Arguments:
#   $@ (string ...): keys that define the validity of the cache file.
# Outputs:
#   1: Path to the cache file.
# Returns:
#   0: The printed file can be used for caching.
#   1: Caching is impossible.
_cache_file() {
    local hash cache_dir cache_file
    if ! hash=$(_cache_hash "$@"); then
        printf 'Failed to hash cache keys\n' >&2
        return 1
    fi
    if ! cache_dir=$(cd "${TEMPDIR:-/tmp}" && pwd); then
        printf 'Failed to find cache directory\n' >&2
        return 1
    fi
    cache_file="${cache_dir}/${0##*/}.${hash}"
    if [ -e "$cache_file" ]; then
        if [ -r "$cache_file" ] && [ -w "$cache_file" ]; then
            printf '%s\n' "$cache_file"
            return 0
        else
            printf 'Cache file %s is not readable and writable\n' "$cache_file" >&2
            return 1
        fi
    else
        if ! touch "$cache_file"; then
            printf 'Failed to create cache file %s\n' "$cache_file" >&2
            return 1
        fi
        if [ ! -r "$cache_file" ]; then
            printf 'Created cache file %s is not readable\n' "$cache_file" >&2
            return 1
        fi
        if [ ! -w "$cache_file" ]; then
            printf 'Created cache file %s is not writable\n' "$cache_file" >&2
            return 1
        fi
        if ! rm "$cache_file"; then
            printf 'Failed to remove cache file %s\n' "$cache_file" >&2
            return 1
        fi
        printf '%s\n' "$cache_file"
        return 0
    fi
}

# Prints the given cache keys as a hash.
# Each given key that is a file or a directory is hashed with its name
# and if retrievable its modification time.
#
# Globals:
#   None
# Arguments:
#   $@ (string ...): keys that define the validity of the cache file.
# Outputs:
#   1: Path to the cache file.
# Returns:
#   0: Hash printed.
#   1: An error occurred, most likely because no cache key was given.
_cache_hash() {
    [ $# -gt 0 ] || die "At least one cache key must be provided."
    local hash
    if hash=$(
        local key last_modified
        for key in "$@"; do
            printf '%s\n' "$key"
            # shellcheck disable=SC2312
            if [ -f "$key" ] || [ -d "$key" ]; then
                [ -r "$key" ] || continue
                if last_modified=$(_mtime "$key" 2>/dev/null); then
                    printf '%s\n' "$last_modified"
                else
                    printf 'Ignoring unreadable modification time of %s\n' "$key" >&2
                fi
            fi
        done | md5sum -
    ); then
        printf '%s\n' "${hash%% *}"
        return 0
    else
        printf 'Failed to hash cache keys\n' >&2
        return 1
    fi
}

_mtime() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        stat -f '%m' "$@"
    else
        stat -c '%Y' "$@"
    fi
}
