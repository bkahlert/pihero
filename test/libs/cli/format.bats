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

@test 'should format template' {
    run format '--{{ Bold "foo" }}--'
    assert_output "$(printf -- '--\e[1m%s\e[0m--' foo)"
    assert_success
}

@test 'should format templates' {
    run format '--{{ Bold "foo" }}--' '--{{ Foreground "2" "Bar" }}--'
    assert_output "$(printf -- '--\e[1m%s\e[0m--' foo)"$'\n'"$(printf -- '--\e[32m%s\e[0m--' Bar)"
    assert_success
}

@test 'should format stdin' {
    printf %s '--{{ Bold "foo" }}--' >input
    run format <input
    assert_output "$(printf -- '--\e[1m%s\e[0m--' foo)"
    assert_success
}
