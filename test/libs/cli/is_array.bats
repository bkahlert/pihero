#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should return 0 if all variables are arrays' {
    declare -a foo bar
    run is_array foo bar
    assert_output ''
    assert_success

    run is_array foo
    assert_output ''
    assert_success

    run is_array
    assert_output ''
    assert_success
}

@test 'should return 1 if at least one variable is no array' {
    declare -a foo
    declare bar
    run is_array foo bar
    assert_output ''
    assert_failure 1

    run is_array bar
    assert_output ''
    assert_failure 1

    run is_array baz
    assert_output ''
    assert_failure 1
}
