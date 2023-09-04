setup_suite() {
    bats_require_minimum_version 1.5.0
    export PROJECT_DIR=$BATS_CWD
    while [ ! -d "$PROJECT_DIR/test" ]; do
        PROJECT_DIR=${PROJECT_DIR%/*}
        if [ "$PROJECT_DIR" = '' ]; then
            echo "Couldn't find project directory" >&3
            exit 1
        fi
    done
}

create_usb_gadget_custom_wrapper() {
    local PROJECT_DIR=${1?:}
    local wrapper_dir="$BATS_SUITE_TMPDIR"/wrapper
    mkdir -p "$wrapper_dir"
    cp "$PROJECT_DIR"/roles/usb_gadget/templates/usb-gadget-custom.sh "$wrapper_dir"/usb-gadget-custom
    chmod +x "$wrapper_dir"/usb-gadget-custom
    export PATH="$wrapper_dir:$PATH"
}

export -f create_usb_gadget_custom_wrapper
