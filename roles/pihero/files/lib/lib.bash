SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./ansi.bash
source "$SCRIPT_DIR/ansi.bash"

# shellcheck source=./checks.bash
source "$SCRIPT_DIR/checks.bash"

# shellcheck source=./runs.bash
source "$SCRIPT_DIR/runs.bash"

# shellcheck source=./services.bash
source "$SCRIPT_DIR/services.bash"
