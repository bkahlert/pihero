#!/usr/bin/env bats

setup() {
    bats_load_library bats-support
    bats_load_library bats-assert
    bats_load_library bats-file

    # shellcheck source=./../../../roles/pihero/files/lib/cache.bash
    . "$PROJECT_DIR/roles/pihero/files/lib/cache.bash"

    cd "$BATS_TEST_TMPDIR" || exit 1
    export CACHE_DIR="$BATS_TEST_TMPDIR/cache"
    mkdir "$CACHE_DIR" || exit 1
}

@test 'should run command and return output' {
    script='echo "EPOCHREALTIME=$EPOCHREALTIME"'
    run run_caching bash -c "$script"
    assert_output --partial 'EPOCHREALTIME='
    assert_success
}

@test 'should output cached result and exit with 0 instead of running command' {
    script='echo "EPOCHREALTIME=$EPOCHREALTIME"'
    run run_caching bash -c "$script"
    local initial_output="$output"
    run run_caching bash -c "$script"
    assert_equal "$output" "$initial_output"
    assert_success
}

@test 'should cache only successful executions' {
    script='echo "EPOCHREALTIME=$EPOCHREALTIME"; exit 42'
    run run_caching bash -c "$script"
    local initial_output="$output"
    run run_caching bash -c "$script"
    assert_not_equal "$output" "$initial_output"
}

@test 'should propagate exit code' {
    script='exit 42'
    run run_caching bash -c "$script"
    assert_failure 42
}

@test 'should not cache on inexistent CACHE_DIR' {
    rm -d "$CACHE_DIR"
    script='echo "EPOCHREALTIME=$EPOCHREALTIME"'
    run run_caching bash -c "$script"
    local initial_output="$output"
    run run_caching bash -c "$script"
    assert_not_equal "$output" "$initial_output"
    assert_success
}

@test 'should support extra keys' {
    script='echo "EPOCHREALTIME=$EPOCHREALTIME"'
    run run_caching --key x bash -c "$script"
    local initial_output="$output"

    run run_caching --key=x bash -c "$script"
    assert_equal "$output" "$initial_output"

    run run_caching --key y bash -c "$script"
    assert_not_equal "$output" "$initial_output"
}

@test 'should add modification time of file args to hash key' {
    script='echo "EPOCHREALTIME=$EPOCHREALTIME"'

    touch x

    run run_caching --key x bash -c "$script"
    local initial_output="$output"

    sleep 1 # ensure modification time changes even if resolution is 1 s

    run run_caching --key=x bash -c "$script"
    assert_equal "$output" "$initial_output"

    touch x

    run run_caching --key x bash -c "$script"
    assert_not_equal "$output" "$initial_output"
}
