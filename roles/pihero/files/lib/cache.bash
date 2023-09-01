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

    local cache_key
    if cache_key=$(_cache_key "${keys[@]}"); then
        [ "$debug" = 0 ] || printf 'caching: cache key: %s\n' "$cache_key" >&2
    else
        [ "$debug" = 0 ] || printf 'caching: cache key: failed\n' >&2
    fi

    local exit_code
    declare -p _cache_mem &>/dev/null || declare -gA _cache_mem=()
    if [ -n "${_cache_mem[$cache_key]}" ]; then
        [ "$debug" = 0 ] || printf 'caching: mem-cache hit\n' >&2
        printf '%s' "${_cache_mem[$cache_key]}"
        exit_code=0
    else
        [ "$debug" = 0 ] || printf 'caching: mem-cache miss\n' >&2
        local cache_file output
        if cache_file=$(_cache_file "${keys[@]}"); then
            [ "$debug" = 0 ] || printf 'caching: cache file: %s\n' "$cache_file" >&2
            if [ -e "$cache_file" ]; then
                [ "$debug" = 0 ] || printf 'caching: file-cache hit\n' >&2
                output=$(<"$cache_file")
                exit_code=0
                _cache_mem[$cache_key]="$output"
                [ "$debug" = 0 ] || printf 'caching: mem-cache update\n' >&2
                printf '%s' "$output"
            else
                [ "$debug" = 0 ] || printf 'caching: file-cache miss\n' >&2
                output=$("$@")
                exit_code=$?
                if [ "$exit_code" -eq 0 ]; then
                    [ "$debug" = 0 ] || printf 'caching: mem-cache update\n' >&2
                    _cache_mem[$cache_key]="$output"
                    [ "$debug" = 0 ] || printf 'caching: file-cache update\n' >&2
                    printf '%s' "$output" | tee "$cache_file"
                else
                    [ "$debug" = 0 ] || printf 'caching: output dismissal\n' >&2
                    printf '%s' "$output"
                fi
            fi
        else
            [ "$debug" = 0 ] || printf 'caching: file-caching impossible\n' >&2
            output=$("$@")
            exit_code=$?
            if [ "$exit_code" -eq 0 ]; then
                [ "$debug" = 0 ] || printf 'caching: mem-cache update\n' >&2
                _cache_mem[$cache_key]="$output"
            else
                [ "$debug" = 0 ] || printf 'caching: output dismissal\n' >&2
            fi
            printf '%s' "$output"
        fi
    fi

    if [ ! "$debug" = 0 ]; then
        local end_time=$((${EPOCHREALTIME/./} / 1000))
        printf 'caching: summary\n - command: %s\n - exit code: %d\n - runtime: %s ms\n' \
            "$*" "$exit_code" "$((end_time - start_time))" >&2
    fi
    return "$exit_code"
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
#   0: Success, hash printed
#   1: Failure
_cache_key() {
    local hash
    hash=$(
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
    ) || return 1
    printf '%s\n' "${hash%% *}"
}

# Prints the path to a cache file for the given cache key.
# If the cache file doesn't exist, it can be used to the result of the computation.
# If the cache file exists, it can be read to get the result of the last computation.
#
# Globals:
#   None
# Arguments:
#   $1: cache key returned by _cache_key
# Outputs:
#   1: Path to the cache file.
# Returns:
#   0: The printed file can be used for caching.
#   1: Failure, caching impossible
_cache_file() {
    local hash cache_file
    hash=$(_cache_key "$@") || return
    cache_file="$(_cache_file_prefix)${hash}" || return
    if [ -e "$cache_file" ]; then
        [ -r "$cache_file" ] || return
        [ -w "$cache_file" ] || return
        printf '%s\n' "$cache_file"
    else
        touch "$cache_file" || return
        [ -r "$cache_file" ] || return
        [ -w "$cache_file" ] || return
        rm "$cache_file" || return
        printf '%s\n' "$cache_file"
    fi
}

# Deeplink for managing the cache, invocable with $0 @cache
@cache() {
    local op=list
    while [ $# -gt 0 ]; do
        case "$1" in
        --list) op=list && shift ;;
        --clear) op=clear && shift ;;
        *) die "The provided option %p is unknown." "$1" ;;
        esac
    done

    local prefix
    prefix=$(_cache_file_prefix) || return
    (
        shopt -s nullglob
        for cache_file in "$prefix"*; do
            case "$op" in
            clear) rm "$cache_file" ;;
            *) printf '%s\n' "$cache_file" ;;
            esac
        done
    )
}

_cache_file_prefix() {
    local cache_dir
    cache_dir=$(cd "${TEMPDIR:-/tmp}" && pwd) || return 1
    printf '%s/%s.' "$cache_dir" "${0##*/}"
}

_mtime() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        stat -f '%m' "$@"
    else
        stat -c '%Y' "$@"
    fi
}
