#!/usr/bin/env bats
# shellcheck disable=SC2312

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    PATH="$PROJECT_DIR/roles/pihero/files/bin:$PATH"

    USAGE='Usage: pihero <command>

Ansible setup companion tool

Commands:
  diag
  share
  system'

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should print help on -h' {
    run pihero -h

    assert_output "$USAGE"
    assert_success
}

@test 'should fail on missing command and no terminal' {
    run pihero </dev/null
    assert_output "$USAGE"'

 ─=≡▰▩▩[ ༶◕︿◕ ]⊐ command missing'
    assert_failure 2
}

@test 'should fail on invalid command' {
    run pihero unknown
    assert_output "$USAGE"'

 ─=≡▰▩▩[ ༶◕︿◕ ]⊐ unknown: invalid command'
    assert_failure 2
}

@test 'should fail on missing extension command' {
    run pihero system </dev/null
    assert_output '
 ─=≡▰▩▩[ ༶◕︿◕ ]⊐ system: command missing'
    assert_failure 125
}

@test 'should fail on unknown extension command' {
    run -127 pihero system unknown
    assert_output '
 ─=≡▰▩▩[ ༶◕︿◕ ]⊐ system: unknown: command not found'
    assert_failure 127
}
