#!/bin/bash

invoke() {
  local -r working_dir=${1?:working directory missing} && shift
  local -ar cmdline=("$@")
  local exit_code
  printf "Invoking \033[3m%s\033[23m in \033[3m%s\033[23m...\n" "${cmdline[*]}" "$working_dir" >&2
  (
    cd "$working_dir" || { printf "\033[31mERROR: Failed to change directory to \033[3m%s\033[23m.\033[0m\n" "$working_dir" >&2 && exit 1; }
    "${cmdline[@]}"
  )
  exit_code=$?
  if [ $exit_code -eq 0 ]; then
    printf "Invocation terminated successfully.\n" >&2
  else
    printf "\033[31mERROR: Invocation terminated with exit code \033[3m%d\033[23m.\033[0m\n" "$exit_code" >&2
  fi
  return $exit_code
}

create_custom_function() {
  local -r function_name=${1?:function name missing}
  local -r instance_name=${2?:instance name missing}
  local -r function="$function_name.$instance_name"
  local -r script=${3?:script missing}
  local exit_code

  case "$script" in
  \#!*)
    printf "\033[1mCreating custom function \033[3m%s\033[23m using inline script...\033[0m\n" "$function" >&2
    local -r script_file=$(mktemp)
    printf '%s\n' "$script" >"$script_file"
    chmod +x "$script_file"
    invoke "functions/$function" "$script_file" "$function_name" "$instance_name"
    exit_code=$?
    if [ $exit_code -eq 0 ]; then
      rm "$script_file"
    fi
    ;;
  *)
    if [ -x "$script" ]; then
      printf "\033[1mCreating custom function \033[3m%s\033[23m using script...\033[0m\n" "$function" >&2
      local -r script_file=$(realpath "$script")
      invoke "functions/$function" "$script_file" "$function_name" "$instance_name"
      exit_code=$?
    else
      local truncated="${script%%$'\n'*}" && [ "$truncated" != "$script" ] && truncated+="..."
      printf "\033[31mERROR: Script \033[3m%s\033[23m is neither executable nor starts it with \033[3m%s\033[23m.\033[0m\n" "$truncated" '#!' >&2
      exit 1
    fi
    ;;
  esac
  if [ $exit_code -ne 0 ]; then
    printf "\033[31mERROR: Failed to execute script \033[3m%s\033[23m for function \033[3m%s\033[23m.\033[0m\n" "$script_file" "$function" >&2
  fi
  return $exit_code
}

main() {
  local -r function=${1?:function missing} && shift
  if declare -F "$function" >/dev/null; then
    "$function" "$@"
  else
    printf "\033[31mERROR: No function with name \033[3m%s\033[23m exists.\033[0m\n" "$function" >&2
    exit 1
  fi
}

main "$@"
