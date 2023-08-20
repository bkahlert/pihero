# Executes a given command with the specified arguments, for example,
#   - run_optional nmap -sn 10.10.10.11-14
#   - run_optional sudo apt-get install -y git
# Globals:
#   None
# Arguments:
#   $1 (string): Command to be executed
#   $@ (mixed): Arguments to be passed to the command
# Outputs:
#   Command output
# Returns:
#   Command exit status
run_optional() {
  local cmd
  if [ "${1?command missing}" = "sudo" ]; then
    cmd=${2?command missing}
  else
    cmd=$1
  fi
  if command -v "$cmd" >/dev/null; then
    "$@"
  else
    printf "\e[2mSkipping disabled \e[3m%s\e[23m... \e[32m✔︎\e[0m\n" "$cmd" >&2
  fi
}

# Executes a given command with the specified arguments and its output indented, for example,
# ⁤run_indented bash <<'EOF'
# ⁤    echo "foo" >&2
# ⁤    echo "bar"
# ⁤    run_indented bash -c '
# ⁤      echo "foo2" >&2
# ⁤      echo "bar2"
# ⁤    '
# ⁤EOF
# prints:
# ⁤    foo
# ⁤    bar
# ⁤        foo
# ⁤        bar
#
# Globals:
#   INDENT (string, default: "    "): Indentation string
# Arguments:
#   $1 (string): Command to be executed
#   $@ (mixed): Arguments to be passed to the command
# Outputs:
#   Command output indented by $INDENT
# Returns:
#   Command exit status
run_indented() {
  local indent=${INDENT:-"    "}
  local indent_cmdline=(awk '{print "'"$indent"'" $0}')

  if ! declare -F "$1" >/dev/null && [ -t 1 ] && command -v unbuffer >/dev/null 2>&1; then
    { unbuffer "$@" 2> >("${indent_cmdline[@]}" >&2); } | "${indent_cmdline[@]}"
  else
    { "$@" 2> >("${indent_cmdline[@]}" >&2); } | "${indent_cmdline[@]}"
  fi
}

export -f run_indented
