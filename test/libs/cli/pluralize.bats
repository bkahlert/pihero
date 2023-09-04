#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'should pluralize' {
    while IFS=: read -r singular plural; do
        run pluralize "$singular"
        assert_output "$plural"
        assert_success
    done <<EOF
bus:buses
tax:taxes
blitz:blitzes
lunch:lunches
marsh:marshes
city:cities
ray:rays
word:words
EOF
}

@test 'should not pluralize if number=1 specified' {
    run pluralize --number 1 "bus"
    assert_output "bus"
    assert_success
}

@test 'should ignore empty strings' {
    run pluralize bus '' tax
    assert_output buses$'\n'taxes
    assert_success
}
