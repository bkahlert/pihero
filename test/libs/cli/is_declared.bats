#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should return 0 if variable is declared' {
    declare foo
    run is_declared foo
    assert_output ''
    assert_success
}

@test 'should return 0 if variable is declared with given attributes' {
    declare -ra foo
    run is_declared foo a
    assert_output ''
    assert_success

    run is_declared foo r
    assert_output ''
    assert_success

    run is_declared foo a r
    assert_output ''
    assert_success

    run is_declared foo r a
    assert_output ''
    assert_success
}

@test 'should return 1 if variable is not declared' {
    run is_declared foo
    assert_output ''
    assert_failure 1
}

@test 'should return 1 if variable is declared but not with given attributes' {
    declare -ra foo
    run is_declared foo i r
    assert_output ''
    assert_failure 1
}

@test 'should return 2 if variable is missing' {
    run is_declared
    assert_output --partial 'error: is_declared: variable name missing'
    assert_failure 2
}
