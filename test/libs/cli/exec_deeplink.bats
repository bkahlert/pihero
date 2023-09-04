#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should do nothing if no deeplink is specified' {
    run exec_deeplink foo
    assert_output ''
    assert_success
}

@test 'should exit if specified deeplink not exists' {
    run -127 exec_deeplink "@deep" foo
    assert_output --partial 'error: deep: deeplink not found'
    assert_failure 127
}

@test 'should run existing deeplink and exit' {
    @deep() {
        # shellcheck disable=SC2317
        echo "args: $*"
    }
    run exec_deeplink "@deep" foo
    assert_output 'args: foo'
    assert_success
}

@test 'should run existing deeplink and exit with @deeplink code' {
    @deep() {
        return 42
    }
    run exec_deeplink "@deep" foo
    assert_failure 42
}
