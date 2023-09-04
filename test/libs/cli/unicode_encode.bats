#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

# Prints the contents of the output variable escaped.
debug_output() {
    printf %s "$output" | od -c >&3
}

@test 'should format file' {
    printf 'a \e' >file
    run unicode_encode file
    assert_output '\u0061\u0020\u001b'
    assert_success
}

@test 'should format files' {
    printf 'a \e' >file1
    printf 'x\n' >file2
    run unicode_encode file1 file2
    assert_output '\u0061\u0020\u001b\u0078\u0000'
    assert_success
}

@test 'should format stdin' {
    printf 'a \e' >input
    run unicode_encode <input
    assert_output '\u0061\u0020\u001b'
    assert_success
}
