#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should print usage' {
    run usage
    assert_output 'Usage: '"$(basename "$0")"
    assert_success
}

@test 'should use specified command' {
    run usage --command foo
    assert_output 'Usage: foo'
    assert_success
}

@test 'should print arg' {
    run usage --command foo --arg bar
    assert_output 'Usage: foo bar'
    assert_success
}

@test 'should print arg values' {
    run usage --command foo --arg bar value1 value2
    assert_output 'Usage: foo <bar>

Bars:
  value1
  value2'
    assert_success
}

@test 'should print specified header' {
    run usage --header "Header" --command foo
    assert_output 'Usage: foo

Header'
    assert_success
}

@test 'should print specified header environment variable' {
    USAGE_HEADER='Header Env' run usage --command foo
    assert_output 'Usage: foo

Header Env'
    assert_success
}

@test 'should print specified header instead of environment variable' {
    USAGE_HEADER='Header Env' run usage --header "Header" --command foo
    assert_output 'Usage: foo

Header'
    assert_success
}
