#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should print error message on missing icon' {
    run icon_template
    assert_output --partial 'error: name missing'
    assert_failure 2
}

@test 'should space on unknown icon' {
    run icon_template unknown
    assert_output ' '
    assert_failure 1
}

@test 'should print template' {
    run icon_template success
    assert_output '{{ Bold (Foreground "2" "✔") }}'
    assert_success
}
