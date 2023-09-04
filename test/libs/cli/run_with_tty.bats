#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should run with tty on stdout' {
    script='if [ -t 1 ]; then printf "FD1:tty"; else printf "FD1:no-tty"; fi'
    run bash -c "$script"
    assert_output "FD1:no-tty"
    assert_success

    run run_with_tty bash -c "$script"
    assert_output "FD1:tty"
    assert_success
}

@test 'should run with tty on stderr' {
    script='if [ -t 2 ]; then printf "FD2:tty"; else printf "FD2:no-tty"; fi'

    run bash -c "$script"
    assert_output "FD2:no-tty"
    assert_success

    run run_with_tty bash -c "$script"
    assert_output "FD2:tty"
    assert_success
}

@test 'should return commands exit code' {
    script='exit 42'
    run bash -c "$script"
    assert_failure 42

    run run_with_tty bash -c "$script"
    assert_failure 42
}

@test 'should print raw output' {
    script='echo line1; echo line2'
    run bash -c "$script"
    assert_output "line1"$'\n'"line2"

    run run_with_tty bash -c "$script"
    assert_output "line1"$'\r'$'\n'"line2"$'\r'

    # carriage returns can be removed with sed
    # sed 's/\r$//'
}
