SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./cli.bash
source "$SCRIPT_DIR/cli.bash"

# shellcheck source=./hero.bash
source "$SCRIPT_DIR/hero.bash"

# shellcheck source=./extensions.bash
source "$SCRIPT_DIR/extensions.bash"

# shellcheck source=./checks.bash
source "$SCRIPT_DIR/checks.bash"

# shellcheck source=./runs.bash
source "$SCRIPT_DIR/runs.bash"

# shellcheck source=./services.bash
source "$SCRIPT_DIR/services.bash"
