#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should read given options' {
    {
        echo 'foo=bar'
    } >ini_file

    local foo bar
    read_ini foo bar <ini_file
    assert_equal "$foo" 'bar'
    assert_equal "$bar" ''
}

@test 'should set last read value' {
    {
        echo 'foo=bar'
        echo 'foo=baz'
    } >ini_file

    local foo
    read_ini foo <ini_file
    assert_equal "$foo" 'baz'
}

@test 'should read array if declared as one' {
    {
        echo 'foo=bar'
        echo 'foo=baz'
    } >ini_file

    local -a foo
    read_ini foo <ini_file
    assert_equal "${#foo[@]}" '2'
    assert_equal "${foo[*]}" 'bar baz'
}

@test 'should exclude not specified section' {
    {
        echo '[section1]'
        echo 'foo=bar'
        echo '[section2]'
        echo 'foo=baz'
    } >ini_file

    local foo
    read_ini --section=section1 foo <ini_file
    assert_equal "$foo" 'bar'
}

@test 'should not exclude undefined section' {
    {
        echo 'foo=bar'
        echo '[section2]'
        echo 'foo=baz'
    } >ini_file

    local foo
    read_ini --section=section1 foo <ini_file
    assert_equal "$foo" 'bar'
}
