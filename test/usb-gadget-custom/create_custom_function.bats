#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    create_usb_gadget_custom_wrapper "$PROJECT_DIR"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

fake_function_dir() {
    local function=${1?:}
    [ "$PWD" = "$BATS_TEST_TMPDIR" ] || exit 2
    mkdir -p "functions/$function"
}

@test 'should fail on missing function name' {
    run usb-gadget-custom create_custom_function

    assert_output --partial 'function name missing'
    assert_failure
}

@test 'should fail on missing instance name' {
    run usb-gadget-custom create_custom_function mass_storage

    assert_output --partial 'instance name missing'
    assert_failure
}

@test 'should fail on missing script' {
    run usb-gadget-custom create_custom_function mass_storage usb0

    assert_output --partial 'script missing'
    assert_failure
}

@test 'should fail on invalid script' {
    run usb-gadget-custom create_custom_function mass_storage usb0 invalid

    assert_output --partial 'Script'
    assert_output --partial 'invalid'
    assert_output --partial 'executable'
    assert_output --partial '#!'
    assert_failure
}

@test 'should fail on non-executable script in function directory' {
    echo '#!/bin/bash
echo $PWD >stall
' >no-executable
    run usb-gadget-custom create_custom_function mass_storage usb0 no-executable

    assert_output --partial 'Script'
    assert_output --partial 'no-executable'
    assert_output --partial 'executable'
    assert_output --partial '#!'
    assert_failure
}

@test 'should only print first line of script' {
    run usb-gadget-custom create_custom_function mass_storage usb0 'foo
bar'

    assert_output --partial 'Script'
    assert_output --partial 'foo...'
    refute_output --partial 'bar'
    assert_output --partial 'executable'
    assert_output --partial '#!'
    assert_failure
}

@test 'should execute inline script in function directory' {
    fake_function_dir mass_storage.usb0
    run usb-gadget-custom create_custom_function mass_storage usb0 '#!/bin/bash
echo $PWD >stall
'

    assert_success
    assert_file_exist functions/mass_storage.usb0/stall
    assert_equal "$BATS_TEST_TMPDIR/functions/mass_storage.usb0" "$(<functions/mass_storage.usb0/stall)"
}

@test 'should execute script in function directory' {
    echo '#!/bin/bash
echo $PWD >stall
' >script
    chmod +x script
    fake_function_dir mass_storage.usb0
    run usb-gadget-custom create_custom_function mass_storage usb0 script

    assert_success
    assert_file_exist functions/mass_storage.usb0/stall
    assert_equal "$BATS_TEST_TMPDIR/functions/mass_storage.usb0" "$(<functions/mass_storage.usb0/stall)"
}

@test 'should pass through STDOUT' {
    cat <<'EOF' >script
echo 42 >port_num

port_num_file="$PWD/port_num"
echo 'if [ -f "'$port_num_file'" ]; then
    N="$(<"'$port_num_file'")"
    echo "serial-getty@ttyGS${N}.service" || true
fi'
EOF
    chmod +x script
    fake_function_dir acm.usb0
    run --separate-stderr usb-gadget-custom create_custom_function acm usb0 script

    assert_success
    assert_output 'if [ -f "'"$BATS_TEST_TMPDIR"'/functions/acm.usb0/port_num" ]; then
    N="$(<"'"$BATS_TEST_TMPDIR"'/functions/acm.usb0/port_num")"
    echo "serial-getty@ttyGS${N}.service" || true
fi'

    # off-topic: test if the output is actually executable
    run bash -c "$output"
    assert_output 'serial-getty@ttyGS42.service'
}

@test 'should escalate script errors' {
    fake_function_dir mass_storage.usb0
    inline_script='#!/bin/bash
echo "doing something"
echo "unexpected error"
exit 42
'
    run usb-gadget-custom create_custom_function mass_storage usb0 "$inline_script"

    assert_output --partial 'terminated with exit code'
    assert_output --partial '42'
    assert_output --partial 'Failed to execute script'
    [[ $output =~ (/[^ ]*) ]] || fail "No temp script path found in output"
    temp_script=${BASH_REMATCH[1]}
    assert_file_exist "$temp_script"
    assert_equal "$(<"$temp_script")" "${inline_script%$'\n'}"
    assert_failure 42
}
