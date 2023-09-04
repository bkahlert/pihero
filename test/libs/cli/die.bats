#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should print default error message' {
    run die
    assert_output --partial 'error: unknown error in '
    assert_failure
}

@test 'should print specified error message' {
    run die "specified error message"
    assert_output --partial 'error: specified error message'
    assert_failure
}

@test 'should exit with code 1 by default' {
    run die
    assert_failure 1
}

@test 'should exit with specified code' {
    run die --code 42
    assert_failure 42
}
