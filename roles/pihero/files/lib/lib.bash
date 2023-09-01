SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

declare mark_enabled=1
declare -ig mark_start mark_last mark_index
# Prints a mark to stderr, with the time passed since the last mark.
mark() {
    [ "$mark_enabled" = 1 ] || return 0
    if [ -z "$mark_start" ]; then
        mark_index=0
        mark_start=$((${EPOCHREALTIME/./} / 1000))
        mark_last=$mark_start
        printf '%-10s %10d\n' 'Start' "" >&2
    else
        local mark_current=$((${EPOCHREALTIME/./} / 1000))
        mark_index=$((mark_index + 1))
        local lineno=${BASH_LINENO[0]}
        printf '%-10s %+10.f ms\n' "line $lineno" "+$((mark_current - mark_last))" >&2
        mark_last=$mark_current
    fi
}

# shellcheck source=./cache.bash
. "$SCRIPT_DIR/cache.bash"

# shellcheck source=./cli.bash
. "$SCRIPT_DIR/cli.bash"

# shellcheck source=./hero.bash
. "$SCRIPT_DIR/hero.bash"

# shellcheck source=./extensions.bash
. "$SCRIPT_DIR/extensions.bash"

# shellcheck source=./checks.bash
. "$SCRIPT_DIR/checks.bash"

# shellcheck source=./services.bash
. "$SCRIPT_DIR/services.bash"
