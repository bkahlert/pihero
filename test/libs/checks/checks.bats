#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    # shellcheck source=./../../../roles/pihero/files/lib/checks.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/checks.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

# Prints the contents of the output variable escaped.
debug_output() {
    printf %s "$output" | od -c >&3
}

@test 'should perform no checks' {
    NO_COLOR=1 CHECKS_OUTPUT_FORMAT=markdown run no_checks
    assert_success

    #debug_output
    local expected='# No checks''

! NO CHECKS PERFORMED'
    assert_output "$expected"
}

@test 'should output ansi by default' {
    NO_COLOR=1 run no_checks
    assert_success

    run remove_ansi_escapes <<<"$output"
    #debug_output
    local expected='  NO CHECKS  ''
! NO CHECKS PERFORMED'
    assert_output "$expected"
}

@test 'should suppress output if specified' {
    CHECKS_OUTPUT_FORMAT=none run no_checks
    assert_success
    assert_output ''
}

@test 'should perform succeeding checks' {
    NO_COLOR=1 CHECKS_OUTPUT_FORMAT=markdown run succeeding_checks
    assert_success

    #debug_output
    local expected='# Succeeding checks

## Results

- [x] true is true

- [x] true is true *(--brief)*

### cat...

- [x] command exists

- [x] command exists *(--brief)*

---

✔ ALL CHECKS PASSED'
    assert_output "$expected"
}

@test 'should perform failing checks' {
    # This associative array has to be declared here, otherwise it's treated
    # as a regular array, and the test fails.
    # ChatGPT gave me the tip.
    declare -A __check_further_steps=()

    NO_COLOR=1 CHECKS_OUTPUT_FORMAT=markdown run failing_checks
    assert_failure 1

    #    debug_output
    # shellcheck disable=SC2016
    local expected='# Failing checks

## Results

- [x] true is true

- [x] true is true *(--brief)*

- [ ] true is not true
  `true` didn'"'"'t fail

- [ ] true is not true *(--brief)*

### cat...

- [x] command exists

- [x] command exists *(--brief)*

- [ ] command not exists
  `command -v cat` didn'"'"'t fail
> /bin/cat

- [ ] command not exists *(--brief)*

### foo...

- [ ] command exists
  `command -v foo` failed

- [ ] command exists *(--brief)*

- [x] command not exists

- [x] command not exists *(--brief)*

---

✘ 6 CHECKS FAILED

## Further steps

### cat command

### foo command'
    #    output="$expected" && debug_output

    assert_output -- "$expected"
}

no_checks() {
    check_start "No checks"
    check_summary
}

succeeding_checks() {
    check_start "Succeeding checks"
    check 'true is true' true
    check --brief 'true is true *(--brief)*' true
    check_unit cat
    check 'command exists' command -v cat
    check --brief 'command exists *(--brief)*' command -v cat
    check_summary
}

failing_checks() {
    check_start "Failing checks"
    check 'true is true' true
    check --brief 'true is true *(--brief)*' true
    check 'true is not true' ! true
    check --brief 'true is not true *(--brief)*' ! true
    check_unit cat
    check 'command exists' command -v cat
    check --brief 'command exists *(--brief)*' command -v cat
    check 'command not exists' ! command -v cat
    check --brief 'command not exists *(--brief)*' ! command -v cat
    check_unit foo
    check 'command exists' command -v foo
    check --brief 'command exists *(--brief)*' command -v foo
    check 'command not exists' ! command -v foo
    check --brief 'command not exists *(--brief)*' ! command -v foo

    check_further '- [%s](%s)' 'Bash manual' 'https://www.gnu.org/software/bash/manual'
    local command
    # shellcheck disable=SC2016
    for command in cat foo; do
        check_further_unit '%s command' "$command"
        check_further '- man page:\n  `%s`' "man $command"
        check_further '- builtin help:\n  `%s`' "bash -c 'help $command'"
    done
    check_summary
}
