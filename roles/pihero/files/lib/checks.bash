declare -i FAILURE_COUNT=0

# Prints an announcement about the start of a checks, for example,
#   - checks_start "Docker" → "Docker" (bold) and a line of dashes
# Globals:
#   FAILURE_COUNT: set to 0, incremented by check() if a check fails
# Arguments:
#   $1 (string, optional): Name of unit being checked
# Outputs:
#   Unit name (bold) and a line of dashes
# Returns:
#   0: Success
checks_start() {
    FAILURE_COUNT=0
    if [ -n "$1" ]; then
        local columns=${COLUMNS:-}
        [ -n "$colums" ] || columns="$(tput cols)" || columns=80
        printf -v line '%*s' "$columns" ''
        printf '\e[1m%s\e[0m\n\e[1m%s\e[0m\n' "$1" "${line//?/—}"
    fi
}

# Prints an announcement about the checked (sub) unit, for example,
#   - check_unit "network" → Checking network... (bold)
# Globals:
#   None
# Arguments:
#   $1 (string): Name of (sub) unit about to be checked
# Outputs:
#   Unit name (bold)
# Returns:
#   0: If the unit name is specified
#   1: If the unit name is missing or empty
check_unit() {
    printf "\e[1mChecking \e[3m%s\e[23m...\e[0m\n" "${1:?subject name missing}"
}

# Checks a condition and prints the result, for example,
#   - check "foo contains bar" grep -q "bar" foo → "Checking if foo contains bar... ✔︎"
#   - check "foo contains baz" grep -q "baz" foo → "Checking if foo contains bar... ERROR: grep -q baz foo failed."
# Globals:
#   FAILURE_COUNT: incremented if a check fails
# Arguments:
#   --brief: If specified, a failed check only prints a "".
#   $1 (string): Condition being checked
#   $@ (mixed): Command-line to run
# Outputs:
#   The condition being checked and the result
# Returns:
#   0: Check passed
#   1: Check failed
check() {
    local brief=0 message success=0
    while (($#)); do
        case "$1" in
        --brief)
            brief=1 && shift
            ;;
        *)
            message=$1 && shift
            break
            ;;
        esac
    done

    printf "Checking if \e[3m%s\e[23m... " "$message"
    if [ "$1" = "!" ]; then
        "${@:2}" || success=1
    else
        "${@}" && success=1
    fi

    if [ "$success" -eq 1 ]; then
        printf "\e[32;1m✔\e[0m\n"
        return 0
    else
        if [ "$brief" = 1 ]; then
            printf "\e[31m✘\e[0m\n"
        else
            printf "\e[31mERROR: \e[3m%s\e[23m failed.\e[0m\n" "$*"
        fi
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        return 1
    fi
}

# Prints the combined result of previous checks.
#   - check_summary → "All checks passed."
#   - check_summary → "1 check failed."
# Globals:
#   FAILURE_COUNT: incremented if a check fails
# Arguments:
#   None
# Outputs:
#   Prints if all checks passed or if the number of failed checks.
# Returns:
#   0: All checks passed
#   1: At least one check failed
check_summary() {
    case $FAILURE_COUNT in
    0)
        printf "\e[32mAll checks passed.\e[0m\n"
        return 0
        ;;
    1)
        printf "\e[31m1 check failed.\e[0m\n"
        return 1
        ;;
    *)
        printf "\e[31m%d checks failed.\e[0m\n" "$FAILURE_COUNT"
        return 1
        ;;
    esac
}
