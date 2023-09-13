#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should return 0 if array contains value' {
    declare -a arr=("foo" "bar")
    array_contains arr "foo"
}

@test 'should return 0 if array contains values' {
    declare -a arr=("foo" "bar")
    array_contains arr "foo" "bar"
}

@test 'should return 0 if no values are given' {
    declare -a arr=("foo" "bar")
    array_contains arr
}

@test 'should return 1 if array does not contain given value' {
    declare -a arr=("foo" "bar")
    set +e
    array_contains arr "baz"
    assert_equal "$?" 1
}

@test 'should return 1 if array does not contain any given value' {
    declare -a arr=("foo" "bar")
    set +e
    array_contains arr "foo" "baz"
    assert_equal "$?" 1
}

@test 'should return 2 if no array is given' {
    run array_contains
    set +e
    assert_failure 2
    assert_output --partial 'error: array_contains: array name missing'
}

@test 'should treat non-array as one-element array' {
    declare arr="foo bar"
    array_contains arr "foo bar"
}
