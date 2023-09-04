# Specifies the environment variables added to the cache key if run_caching is used with the --tty flag.
: "${TERM_ENV_VARS:=TERM:COLORTERM:TERM_PROGRAM:NO_COLOR:CLICOLOR:CLICOLOR_FORCE}"

# Specifies the directory used for caching.
# If not set, the system's temporary directory (or /tmp) is used.
# If the effective path does not exist or is not writable, caching is disabled.
: "${CACHE_DIR:=${TEMPDIR:-/tmp}}"

# Runs the given command with the given arguments
# **only** if there is no cached output for the command and its arguments.
# If there is, the cached output is returned instead.
# If the command does not complete with exit code 0, the output is not cached.
#
# Globals:
#   None
# Arguments:
#   --debug (boolean, default: 0): If set to non-zero, additionally print debug information to STDERR.
#   --key (string, optional): The hashed key used for caching is based on the command and its arguments.
#                             Using this option, adds more parameters to that set of data.
#                             A use case is if the command's output not only depends on its arguments
#                             but also the environment variable FOO.
#                             In such a case `--key FOO=$FOO` can be provided.
#                             The option can be used multiple times.
#   --tty (flag): If set, the command is run with a pseudo teletype (TTY), if the standard output or error is a TTY.
#                 Also, the environment variables, declared in TERM_ENV_VARS are added to the cache key, to invalidate
#                 the cached value if any of the variable values change (for example, NO_COLOR).
#   $1 (string): The command to run.
#   $@ (mixed ...): The arguments to pass to the command.
# Outputs:
#   1: Output of the command, if there is no cached output. Otherwise, the cached output.
#   2: Debug information, if --debug is set to non-zero.
# Returns:
#   The exit code of the command, if it ran. Otherwise, 0.
run_caching() {
    local debug=0 start_time=$((${EPOCHREALTIME/./} / 1000))
    local -a keys=()
    local tty=0
    while [ $# -gt 0 ]; do
        case $1 in
        --debug) debug=1 && shift ;;
        --debug=*) debug=${1#*=} && shift ;;
        --key) keys+=("${2?$1: parameter value not set}") && shift 2 ;;
        --key=*) keys+=("${1#*=}") && shift ;;
        --tty) tty=1 && shift ;;
        --tty=*) tty=${1#*=} && shift ;;
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done

    local command
    if [ $# -gt 0 ]; then
        command=$1 && shift
    else
        die --code 2 'command missing'
    fi

    if [ ! "${tty:-0}" = 0 ] && [ -t 2 ]; then
        # add TERM_ENV_VARS to the cache key
        local var
        while read -d: -r var; do
            keys+=("$var=${!var}")
        done <<<"$TERM_ENV_VARS"

        # change the command to run with a pseudo teletype
        set -- "$command" "$@"
        command=_run_with_tty
    fi

    # add the command and its arguments to the cache key
    keys+=("$command" "$@")

    [ "${debug:-0}" = 0 ] || printf 'run_caching: command: %s\n' "$command $*" >&2
    [ "${debug:-0}" = 0 ] || printf 'run_caching: keys: %s\n' "${keys[*]}" >&2

    local cache_key exit_code
    if cache_key=$(_cache_key --debug="$debug" -- "${keys[@]}"); then
        [ "${debug:-0}" = 0 ] || printf 'run_caching: cache key: %s\n' "$cache_key" >&2
        declare -p _cache_mem &>/dev/null || declare -gA _cache_mem=()
        if [ -n "${_cache_mem[$cache_key]}" ]; then
            [ "${debug:-0}" = 0 ] || printf 'run_caching: mem-cache hit\n' >&2
            printf '%s' "${_cache_mem[$cache_key]}"
            exit_code=0
        else
            [ "${debug:-0}" = 0 ] || printf 'run_caching: mem-cache miss\n' >&2
            local cache_file output
            if cache_file=$(_cache_file --debug="$debug" -- "$cache_key"); then
                [ "${debug:-0}" = 0 ] || printf 'run_caching: cache file: %s\n' "$cache_file" >&2
                if [ -e "$cache_file" ]; then
                    [ "${debug:-0}" = 0 ] || printf 'run_caching: file-cache hit\n' >&2
                    output=$(<"$cache_file")
                    exit_code=0
                    _cache_mem[$cache_key]="$output"
                    [ "${debug:-0}" = 0 ] || printf 'run_caching: mem-cache update\n' >&2
                    printf '%s' "$output"
                else
                    [ "${debug:-0}" = 0 ] || printf 'run_caching: file-cache miss\n' >&2
                    output=$("$command" "$@")
                    exit_code=$?
                    if [ "$exit_code" -eq 0 ]; then
                        [ "${debug:-0}" = 0 ] || printf 'run_caching: mem-cache update\n' >&2
                        _cache_mem[$cache_key]="$output"
                        [ "${debug:-0}" = 0 ] || printf 'run_caching: file-cache update\n' >&2
                        printf '%s' "$output" | tee "$cache_file"
                    else
                        [ "${debug:-0}" = 0 ] || printf 'run_caching: output dismissal\n' >&2
                        printf '%s' "$output"
                    fi
                fi
            else
                [ "${debug:-0}" = 0 ] || printf 'run_caching: file-caching impossible\n' >&2
                output=$("$command" "$@")
                exit_code=$?
                if [ "$exit_code" -eq 0 ]; then
                    [ "${debug:-0}" = 0 ] || printf 'run_caching: mem-cache update\n' >&2
                    _cache_mem[$cache_key]="$output"
                else
                    [ "${debug:-0}" = 0 ] || printf 'run_caching: output dismissal\n' >&2
                fi
                printf '%s' "$output"
            fi
        fi
    else
        [ "${debug:-0}" = 0 ] || printf 'run_caching: cache key: failed\n' >&2
        output=$("$command" "$@")
        exit_code=$?
        printf '%s' "$output"
    fi

    if [ ! "${debug:-0}" = 0 ]; then
        local end_time=$((${EPOCHREALTIME/./} / 1000))
        printf 'run_caching: summary\n - command: %s\n - args: %s\n - exit code: %d\n - runtime: %s ms\n' \
            "$command" "$*" "$exit_code" "$((end_time - start_time))" >&2
    fi
    return "$exit_code"
}

_run_with_tty() {
    run_with_tty "$@" | sed 's/\r$//'
}

# Prints the given cache keys as a hash.
# Each given key that is a file or a directory is hashed with its name
# and if retrievable its modification time.
#
# Globals:
#   None
# Arguments:
#   --debug (boolean, default: 0): If set to non-zero, additionally print debug information to STDERR.
#   $@ (string ...): keys that define the validity of the cache file.
# Outputs:
#   1: Path to the cache file.
# Returns:
#   0: Success, hash printed
#   1: Failure
_cache_key() {
    local debug=0
    while [ $# -gt 0 ]; do
        case $1 in
        --debug) debug=1 && shift ;;
        --debug=*) debug=${1#*=} && shift ;;
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done

    local hash
    hash=$(
        local key last_modified
        for key in "$@"; do
            [ "${debug:-0}" = 0 ] || printf '_cache_key: %s: add\n' "$key" >&2
            printf '%s\n' "$key"
            # shellcheck disable=SC2312
            if [ -f "$key" ] || [ -d "$key" ]; then
                if [ ! -r "$key" ]; then
                    [ "${debug:-0}" = 0 ] || printf '_cache_key: %s: not readable\n' "$key" >&2
                    continue
                fi
                if last_modified=$(_mtime "$key" 2>/dev/null); then
                    [ "${debug:-0}" = 0 ] || printf '_cache_key: %s: last_modified: %s\n' "$key" "$last_modified" >&2
                    printf '%s\n' "$last_modified"
                else
                    [ "${debug:-0}" = 0 ] || printf '_cache_key: %s: last_modified: failed to read\n' "$key" >&2
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
#   --debug (boolean, default: 0): If set to non-zero, additionally print debug information to STDERR.
#   $1: cache key returned by _cache_key
# Outputs:
#   1: Path to the cache file.
# Returns:
#   0: The printed file can be used for caching.
#   1: Failure, caching impossible
_cache_file() {
    local debug=0
    while [ $# -gt 0 ]; do
        case $1 in
        --debug) debug=1 && shift ;;
        --debug=*) debug=${1#*=} && shift ;;
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done

    local cache_key
    if [ $# -gt 0 ]; then
        cache_key=$1 && shift
    else
        die --code 2 'cache key missing'
    fi

    local cache_file
    cache_file="$(_cache_file_prefix)$cache_key" || return
    if [ -e "$cache_file" ]; then
        [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: exists\n' "$cache_file" >&2
        if [ ! -r "$cache_file" ]; then
            [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: not readable\n' "$cache_file" >&2
            return 1
        fi
        if [ ! -w "$cache_file" ]; then
            [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: not writable\n' "$cache_file" >&2
            return 1
        fi
        [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: readable and writable\n' "$cache_file" >&2
        printf '%s\n' "$cache_file"
    else
        [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: not exists\n' "$cache_file" >&2
        if ! touch "$cache_file"; then
            [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: not creatable\n' "$cache_file" >&2
            return 1
        fi
        if [ ! -r "$cache_file" ]; then
            [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: not readable\n' "$cache_file" >&2
            return 1
        fi
        if [ ! -w "$cache_file" ]; then
            [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: not writable\n' "$cache_file" >&2
            return 1
        fi
        if ! rm "$cache_file"; then
            [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: not removable\n' "$cache_file" >&2
            return 1
        fi
        [ "${debug:-0}" = 0 ] || printf '_cache_file: %s: readable and writable\n' "$cache_file" >&2
        printf '%s\n' "$cache_file"
    fi
}

# Deeplink for managing the cache, invocable with $0 @cache
@cache() {
    while [ $# -gt 0 ]; do
        case $1 in
        --help | -h)
            usage --header "Cache management" \
                --arg="${FUNCNAME[0]}" --arg=command list clear
            return 0
            ;;
        *) break ;;
        esac
    done

    while [ $# -gt 0 ]; do
        case $1 in
        --) shift && break ;;
        --*) die --code 2 "%s: invalid option" "$1" ;;
        -*) die --code 2 "%s: invalid flag" "$1" ;;
        *) break ;;
        esac
    done

    local command
    if [ $# -gt 0 ]; then
        command=$1 && shift
    else
        "${FUNCNAME[0]}" --help
        die --code 2 'command missing'
    fi

    case $command in
    list | clear)
        local prefix
        prefix=$(_cache_file_prefix) || return
        (
            shopt -s nullglob
            for cache_file in "$prefix"*; do
                case "$command" in
                clear) rm "$cache_file" ;;
                *) printf '%s\n' "$cache_file" ;;
                esac
            done
        )
        ;;
    *)
        "${FUNCNAME[0]}" --help
        die --code 2 '%s: invalid command' "$command"
        ;;
    esac
}

_cache_file_prefix() {
    [ -n "$CACHE_DIR" ] || return 1
    local cache_dir
    cache_dir=$(cd "$CACHE_DIR" && pwd) || return 1
    printf '%s/%s.' "$cache_dir" "${0##*/}"
}

_mtime() {
    case $OSTYPE in
    darwin*) stat -f '%m' "$@" ;;
    *) stat -c '%Y' "$@" ;;
    esac
}
