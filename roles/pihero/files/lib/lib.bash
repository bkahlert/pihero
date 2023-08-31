SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

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

# shellcheck source=./runs.bash
. "$SCRIPT_DIR/runs.bash"

# shellcheck source=./services.bash
. "$SCRIPT_DIR/services.bash"
