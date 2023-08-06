#!/usr/bin/env bats

setup() {
  bats_load_library bats-support
  bats_load_library bats-assert
  bats_load_library bats-file

  cd "$BATS_TEST_TMPDIR" || exit 1
}

fake_function_dir() {
  local function=${1?:}
  [ "$PWD" = "$BATS_TEST_TMPDIR" ] || exit 2
  mkdir -p "functions/$function"
}

@test 'Fails on missing function name' {
  run usb-gadget-setup-custom create_custom_function

  assert_output --partial 'function name missing'
  assert_failure
}

@test 'Fails on missing instance name' {
  run usb-gadget-setup-custom create_custom_function mass_storage

  assert_output --partial 'instance name missing'
  assert_failure
}

@test 'Fails on missing script' {
  run usb-gadget-setup-custom create_custom_function mass_storage usb0

  assert_output --partial 'script missing'
  assert_failure
}

@test 'Fails on invalid script' {
  run usb-gadget-setup-custom create_custom_function mass_storage usb0 invalid

  assert_output --partial 'Script'
  assert_output --partial 'invalid'
  assert_output --partial 'executable'
  assert_output --partial '#!'
  assert_failure
}

@test 'Fails on non-executable script in function directory' {
  echo '#!/bin/bash
echo $PWD >stall
' >no-executable
  run usb-gadget-setup-custom create_custom_function mass_storage usb0 no-executable

  assert_output --partial 'Script'
  assert_output --partial 'no-executable'
  assert_output --partial 'executable'
  assert_output --partial '#!'
  assert_failure
}

@test 'Only prints first line of script' {
  run usb-gadget-setup-custom create_custom_function mass_storage usb0 'foo
bar'

  assert_output --partial 'Script'
  assert_output --partial 'foo...'
  refute_output --partial 'bar'
  assert_output --partial 'executable'
  assert_output --partial '#!'
  assert_failure
}

@test 'Executes inline script in function directory' {
  fake_function_dir mass_storage.usb0
  run usb-gadget-setup-custom create_custom_function mass_storage usb0 '#!/bin/bash
echo $PWD >stall
'

  assert_success
  assert_file_exist functions/mass_storage.usb0/stall
  assert_equal "$BATS_TEST_TMPDIR/functions/mass_storage.usb0" "$(cat functions/mass_storage.usb0/stall)"
}

@test 'Executes script in function directory' {
  echo '#!/bin/bash
echo $PWD >stall
' >script
  chmod +x script
  fake_function_dir mass_storage.usb0
  run usb-gadget-setup-custom create_custom_function mass_storage usb0 script

  assert_success
  assert_file_exist functions/mass_storage.usb0/stall
  assert_equal "$BATS_TEST_TMPDIR/functions/mass_storage.usb0" "$(cat functions/mass_storage.usb0/stall)"
}

@test 'Escalates script errors' {
  fake_function_dir mass_storage.usb0
  inline_script='#!/bin/bash
echo "doing something"
echo "unexpected error"
exit 42
'
  run usb-gadget-setup-custom create_custom_function mass_storage usb0 "$inline_script"

  assert_output --partial 'terminated with exit code'
  assert_output --partial '42'
  assert_output --partial 'Failed to execute script'
  [[ $output =~ (/[^ ]*) ]] || fail "No temp script path found in output"
  temp_script=${BASH_REMATCH[1]}
  assert_file_exist "$temp_script"
  assert_equal "$(cat "$temp_script")" "${inline_script%$'\n'}"
  assert_failure 42
}
