#!/usr/bin/env bats

setup() {
  bats_load_library bats-support
  bats_load_library bats-assert
  bats_load_library bats-file

  cd "$BATS_TEST_TMPDIR" || exit 1
}

@test 'Fails on missing function' {
  run usb-gadget-setup-custom
  assert_output --partial 'function missing'
  assert_failure
}

@test 'Fails on unknown function' {
  run usb-gadget-setup-custom unknown
  assert_output --partial 'No function with name'
  assert_failure
}
