#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cli.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cli.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
}

@test "should use working pattern" {
    assert_replacement() {
        assert_equal "$(echo -e "$1" | remove_ansi_escapes)" "$2"
    }

    # Fe escape sequences
    assert_replacement '\eB foo\eBbar' ' foobar'

    # 2-byte escape sequences
    assert_replacement '\e(B foo\e(Bbar' ' foobar'

    # CSI escape sequences
    assert_replacement '\e[1;2m foo\e[1;2mbar' ' foobar'
    assert_replacement '\e[1m foo\e[1mbar' ' foobar'
    assert_replacement '\e[m foo\e[mbar' ' foobar'

    # OSC escape sequences not supported
    # assert_replacement '\e]8;;''https://example.com''\e\\''example''\e]8;;\e\' 'example'
}
