#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    create_usb_gadget_custom_wrapper "$PROJECT_DIR"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should fail on missing function' {
    run usb-gadget-custom
    assert_output --partial 'function missing'
    assert_failure
}

@test 'should fail on unknown function' {
    run usb-gadget-custom unknown
    assert_output --partial 'No function with name'
    assert_failure
}
