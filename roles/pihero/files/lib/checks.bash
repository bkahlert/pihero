# Tiny library for running checks / runtime assertions / diagnostics and printing the results.
# Usage:
# - Call `check_start` at the beginning of the checks.
# - Call `check` for each check.
# - Call `check_summary` at the end of the checks.
# - Optional:
#   - `check_unit` helps to group checks logically.
#   - `check_further` adds useful information (code, links, etc.) for next steps.
#   - `check_further_unit` helps to group next steps logically.

declare -a __check_report=()
declare -a __check_results=()
declare -i __checks_total=0 __checks_failed=0
declare -a __check_further_units=('-')
declare ___check_further_steps_delimiter=$'\x03'
declare -A __check_further_steps=()

# Prints an announcement about the start of a checks, for example,
#   - check_start "Docker" → "Docker" (bold) and a line of dashes
# Arguments:
#   $1 (string, optional): Name of unit being checked
# Outputs:
#   Unit name (bold) and a line of dashes
# Returns:
#   0: Success
check_start() {
    __check_report=()
    __check_results=()
    __checks_total=0
    __checks_failed=0
    __check_further_units=('-')
    __check_further_steps=()
    if [ -n "$1" ]; then
        __check_report+=("# $1")
    else
        __check_report+=("# Checks")
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
    local name
    if [ $# -gt 0 ]; then
        name=$1 && shift
    else
        die --code 2 'check: message missing'
    fi

    if [ $# -gt 0 ]; then
        local __eval_condition_exit_code
        __eval_condition "$@" || die --code 2 'check: %s: invalid condition' "$*"
        if [ "$__eval_condition_exit_code" -eq 0 ]; then
            __check_results+=("$(printf '### %s...' "$name")")
        else
            __check_results+=("$(printf '### ~~%s~~' "$name")")
            __check_results+=("$(printf '—')")
            return 1
        fi
    else
        __check_results+=("$(printf '### %s...' "$name")")
    fi
}

# Checks a condition and prints the result, for example,
#   - check "foo contains bar" grep -q "bar" foo → "Checking if foo contains bar... ✔︎"
#   - check "foo contains baz" grep -q "baz" foo → "Checking if foo contains bar... ERROR: grep -q baz foo failed."
# Arguments:
#   --brief: If specified, a failed check only prints a "".
#   $1 (string): Condition being checked
#   $@ (string ...): Command-line to run
# Outputs:
#   The condition being checked and the result
# Returns:
#   0: Check passed
#   1: Check failed
check() {
    local brief=0
    while [ $# -gt 0 ]; do
        case $1 in
        --brief) brief=1 && shift ;;
        --brief=*) brief=${1#*=} && shift ;;
        *) break ;;
        esac
    done

    local message
    if [ $# -gt 0 ]; then
        message=$1 && shift
    else
        die --code 2 'check: message missing'
    fi

    local __eval_condition_exit_code __eval_condition_error_output
    __eval_condition "$@" || die --code 2 'check: %s: invalid condition' "$*"

    if [ "$__eval_condition_exit_code" -eq 0 ]; then
        __check_results+=("$(printf -- '- [x] %s' "$message")")
        __checks_total=$((__checks_total + 1))
        return 0
    else
        local details
        if [ ! "$brief" = 1 ]; then
            # shellcheck disable=SC2016
            if [ "$1" = "!" ]; then
                printf -v details -- '`%s` didn'"'"'t fail' "${*:2}"
            else
                printf -v details -- '`%s` failed' "${*}"
            fi

            if [ -n "$__eval_condition_error_output" ]; then
                details+=$'\n'
                details+=$(printf '%s' "$__eval_condition_error_output" | sed -e 's/^$/ /' -e 's/^/> /')
            fi
        fi
        #        __check_results+=("$(printf -- '- [ ] %s%s' "$message" "${details:+$'\n'"  ${details//$'\n'/$'\n'  }"}")")
        __check_results+=("$(printf -- '- [ ] %s%s' "$message" "${details:+$'\n'"  $details"}")")
        __checks_total=$((__checks_total + 1))
        __checks_failed=$((__checks_failed + 1))
        return 1
    fi
}

# Runs the given command with the given arguments, and saves
# the exit code in `__eval_condition_exit_code`, and
# the error output in `__eval_condition_error_output`.
#
# If the first argument is the exclamation mark (!),
# the exit code is negated, and
# the standard output is used as the error output.
__eval_condition() {
    local negate trim=1
    if [ $# -gt 0 ] && [ "$1" = '!' ]; then negate=1 && shift; fi

    if [ -n "$negate" ]; then
        # bashsupport disable=BP2001
        __eval_condition_error_output=$("$@" 2>/dev/null)
        # bashsupport disable=BP2001
        __eval_condition_exit_code=$((!$?))
    else
        __eval_condition_error_output=$("$@" 2>&1 >/dev/null)
        __eval_condition_exit_code=$?
    fi

    if [ -n "$trim" ]; then
        __eval_condition_error_output=${__eval_condition_error_output%%$'\n'}
        __eval_condition_error_output=${__eval_condition_error_output##$'\n'}
    fi
}

# Adds the provided text to the report.
# *Use at your own risk.*
check_raw() {
    local entry
    # shellcheck disable=SC2059
    printf -v entry -- "$@" || die --code 2 'printf failed'
    __check_results+=("$entry")
}

check_further_unit() {
    local unit
    # shellcheck disable=SC2059
    printf -v unit -- "$@"
    __check_further_units+=("$unit")
    __check_further_steps[$unit]=''
}

check_further() {
    local item
    # shellcheck disable=SC2059
    printf -v item -- "$@"

    local unit="${__check_further_units[*]: -1:1}"
    __check_further_steps[$unit]+="$item""$___check_further_steps_delimiter"
}

# Prints the combined result of previous checks.
#   - check_summary → "All checks passed."
#   - check_summary → "1 check failed."
# Global:
#   CHECKS_OUTPUT_FORMAT: The output is formatted using ANSI escape sequences by default.
#     markdown: the output is formatted as Markdown
#     none: the output is suppressed
# Arguments:
#   None
# Outputs:
#   Prints if all checks passed or if the number of failed checks.
# Returns:
#   0: No check failed
#   1: At least one check failed
check_summary() {
    if [ "${#__check_results[@]}" -gt 0 ]; then
        __check_report+=('## Results')
        __check_report+=("${__check_results[@]}")
        __check_report+=("---")
    fi

    local text foreground icon exit_code
    if [ "$__checks_total" -eq 0 ]; then
        text='No checks performed'
        foreground=3
        icon=warning
        exit_code=0
    elif [ "$__checks_failed" -eq 0 ]; then
        text='All checks passed'
        foreground=2
        icon=success
        exit_code=0
    else
        text="$__checks_failed $(pluralize --number "$__checks_failed" check) failed"
        foreground=1
        icon=error
        exit_code=1
    fi

    __check_report+=("$(format "$(icon_template "$icon" || true)"' {{ Bold (Foreground "'"$foreground"'" "'"${text^^}"'") }}')")

    if [ ${#__check_further_steps[@]} -gt 0 ]; then
        local unit step
        for unit in "${__check_further_units[@]}"; do
            case $unit in
            '-') __check_report+=("$(printf -- '## %s' "Further steps")") ;;
            *) __check_report+=("$(printf -- '### %s' "$unit")") ;;
            esac

            while read -r -d "$___check_further_steps_delimiter" step; do
                __check_report+=("$step")
            done <<<"${__check_further_steps[$unit]}"
        done
    fi

    case ${CHECKS_OUTPUT_FORMAT:-ansi} in
    none) : ;;
    markdown) printf '%s\n\n' "${__check_report[@]}" ;;
    *) printf '%s\n\n' "${__check_report[@]}" | gum format --type markdown --theme <(checks_theme || true) ;;
    esac

    return "$exit_code"
}

# Prints a theme that can be used by `gum format` to
# format the Markdown output of `check_summary`.
# Globals:
#   CHECKS_HEADER_FOREGROUND: Foreground color for headers
#   CHECKS_HORIZONTAL_LINE_FOREGROUND: Foreground color for horizontal lines
#   CHECKS_LINK_FOREGROUND (default: 4): Foreground color for links
#   CHECKS_CODE_FOREGROUND: Foreground color for links
checks_theme() {
    local success_icon error_icon link_icon
    success_icon=$(icon_template success | format | unicode_encode || true)
    error_icon=$(icon_template error | format | unicode_encode || true)
    link_icon=$(icon_template link | format | unicode_encode || true)

    local block_quote_indent_token
    block_quote_indent_token="$(gum style --foreground="$HERO_RED" --faint=1 '┃' | unicode_encode || true)"

    if [ "${NO_COLOR:-0}" = 0 ]; then
        # language=json
        cat <<EOF
{
  "document": { "margin": 0 },
  "block_quote": { "indent": 1, "indent_token": "$block_quote_indent_token " },
  "paragraph": {},
  "list": { "level_indent": 2 },
  "heading": { "color": "${CHECKS_HEADER_FOREGROUND-}", "bold": true },
  "h1": { "prefix": "  ", "upper": true , "suffix": "  ", "inverse": true },
  "h2": { "block_suffix": "\n", "block_prefix": "\n", "prefix": "▉ ", "upper": true },
  "h3": {  },
  "h4": { "color": "${CHECKS_HEADER_FOREGROUND-}" },
  "h5": { "color": "" },
  "h6": { "color": "", "italic": true },
  "text": {},
  "strikethrough": { "crossed_out": true },
  "emph": { "italic": true },
  "strong": { "bold": true },
  "hr": { "color": "${CHECKS_HORIZONTAL_LINE_FOREGROUND-}", "format": "\n──────" },
  "item": { "block_prefix": "• " },
  "enumeration": { "block_prefix": ". " },
  "task": { "ticked": "$success_icon ", "unticked": "$error_icon " },
  "link": { "color": "${CHECKS_LINK_FOREGROUND-4}", "underline": true },
  "link_text": { "suffix": "$link_icon", "bold": true },
  "image": { "underline": true },
  "image_text": { "format": "Image: {{.text}}" },
  "code": { "color": "${CHECKS_CODE_FOREGROUND-}", "bold": true },
  "code_block": { "margin": 2 },
  "table": { "center_separator": "┼", "column_separator": "│", "row_separator": "─" },
  "definition_list": {},
  "definition_term": {},
  "definition_description": { "block_prefix": "\n: " },
  "html_block": {},
  "html_span": {}
}
EOF
    else
        local backtick='`'
        # language=json
        cat <<EOF
{
  "document": { "margin": 0 },
  "block_quote": { "indent": 1, "indent_token": "$block_quote_indent_token " },
  "paragraph": {},
  "list": { "level_indent": 2 },
  "heading": { "bold": true },
  "h1": { "prefix": "  ", "upper": true , "suffix": "  ", "inverse": true },
  "h2": { "block_suffix": "\n", "block_prefix": "\n", "prefix": "▉ ", "upper": true },
  "h3": {},
  "h4": {},
  "h5": {},
  "h6": { "italic": true },
  "text": {},
  "strikethrough": { "crossed_out": true },
  "emph": { "italic": true },
  "strong": { "bold": true },
  "hr": { "format": "\n──────" },
  "item": { "block_prefix": "• " },
  "enumeration": { "block_prefix": ". " },
  "task": { "ticked": "$success_icon ", "unticked": "$error_icon " },
  "link": { "color": "4", "underline": true },
  "link_text": { "suffix": "$link_icon", "bold": true },
  "image": { "underline": true },
  "image_text": { "format": "Image: {{.text}}" },
  "code": { "block_prefix": "$backtick", "block_suffix": "$backtick" },
  "code_block": { "margin": 2 },
  "table": { "center_separator": "┼", "column_separator": "│", "row_separator": "─" },
  "definition_list": {},
  "definition_term": {},
  "definition_description": { "block_prefix": "\n: " },
  "html_block": {},
  "html_span": {}
}
EOF
    fi
}
