setup_suite() {
  local project_dir=$BATS_CWD
  while [ ! -d "$project_dir/test" ]; do
    project_dir=${project_dir%/*}
    if [ "$project_dir" = '' ]; then
      echo "Couldn't find project directory" >&3
      exit 1
    fi
  done
  create_wrapper "$project_dir"
}

create_wrapper() {
  local project_dir=${1?:}
  local wrapper_dir="$BATS_SUITE_TMPDIR"/wrapper
  mkdir -p "$wrapper_dir"
  cp "$project_dir"/roles/usb_gadget/templates/usb-gadget-setup-custom.sh "$wrapper_dir"/usb-gadget-setup-custom
  chmod +x "$wrapper_dir"/usb-gadget-setup-custom
  export PATH="$wrapper_dir:$PATH"
}
