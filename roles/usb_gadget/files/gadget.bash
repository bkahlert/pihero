#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=./../../pihero/files/lib/lib.bash
source "$SCRIPT_DIR/lib/lib.bash"

+diag() {
  /opt/pihero/usb-gadget diag "$@"
}

+start() {
  /opt/pihero/usb-gadget start "$@"
}

+stop() {
  /opt/pihero/usb-gadget stop "$@"
}
