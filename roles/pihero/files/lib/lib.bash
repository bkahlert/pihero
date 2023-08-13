# Shared functions

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./netshare.bash
source "$SCRIPT_DIR/netshare.bash"
