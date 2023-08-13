declare -i FAILURE_COUNT=0

# Prints an announcement about the start of a checks.
# $1: Name of unit being checked; optional.
checks_start() {
  FAILURE_COUNT=0
  if [ "${1:-}" = "" ]; then
    printf "\n" >&2
  else
    printf -v line "\033[1m%0.s—\033[0m" $(seq 1 "$(tput cols)")
    printf "\n" >&2
    printf "\033[1m%s\033[0m\n%s\n" "$1" "$line" >&2
  fi
}

# Checks a condition and prints the result.
# $1: Message to print.
# $@: Command to run.
#     If the first argument is '!', the command is expected to fail.
# FAILURE_COUNT is incremented if the command fails.
check() {
  local success=0
  local -r message=$1
  shift

  printf "Checking if \033[3m%s\033[23m... " "$message" >&2
  if [ "$1" = "!" ]; then
    "${@:2}" || success=1
  else
    "${@}" && success=1
  fi

  if [ "$success" -eq 1 ]; then
    printf "\033[32m✔︎\033[0m\n" >&2
  else
    printf "\033[31mERROR: \033[3m%s\033[23m failed.\033[0m\n" "$*" >&2
    FAILURE_COUNT=$((FAILURE_COUNT + 1))
  fi
}

# Prints the result of previous checks.
# Sets FAILURE_COUNT to 0.
check_summary() {
  case $FAILURE_COUNT in
  0)
    printf "\033[32mAll checks passed.\033[0m\n" >&2
    ;;
  1)
    printf "\033[31m1 check failed.\033[0m\n" >&2
    ;;
  *)
    printf "\033[31m%d checks failed.\033[0m\n" $FAILURE_COUNT >&2
    ;;
  esac
}
