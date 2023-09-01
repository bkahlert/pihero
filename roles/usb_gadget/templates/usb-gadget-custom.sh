#!/usr/bin/env bash

invoke() {
    local -r working_dir=${1:?working directory missing} && shift
    local -ar cmdline=("$@")
    local exit_code
    printf "Invoking \e[3m%s\e[23m in \e[3m%s\e[23m...\n" "${cmdline[*]}" "$working_dir"
    (
        cd "$working_dir" || { printf "\e[31mERROR: Failed to change directory to \e[3m%s\e[23m.\e[0m\n" "$working_dir" && exit 1; }
        "${cmdline[@]}"
    )
    exit_code=$?
    if [ "$exit_code" -eq 0 ]; then
        printf "Invocation terminated successfully.\n"
    else
        printf "\e[31mERROR: Invocation terminated with exit code \e[3m%d\e[23m.\e[0m\n" "$exit_code" >&2
    fi
    return "$exit_code"
}

create_custom_function() {
    local -r function_name=${1:?function name missing}
    local -r instance_name=${2:?instance name missing}
    local -r function="$function_name.$instance_name"
    local -r script=${3:?script missing}
    local exit_code

    case "$script" in
    \#!*)
        printf "\e[1mCreating custom function \e[3m%s\e[23m using inline script...\e[0m\n" "$function"
        local script_file
        script_file=$(mktemp) || { printf "\e[31mERROR: Failed to create temporary file.\e[0m\n" >&2 && exit 1; }
        printf '%s\n' "$script" >"$script_file"
        chmod +x "$script_file"
        invoke "functions/$function" "$script_file" "$function_name" "$instance_name"
        exit_code=$?
        if [ "$exit_code" -eq 0 ]; then
            rm "$script_file"
        fi
        ;;
    *)
        if [ -x "$script" ]; then
            printf "\e[1mCreating custom function \e[3m%s\e[23m using script...\e[0m\n" "$function"
            local script_file
            script_file=$(realpath "$script") || { printf "\e[31mERROR: Failed to resolve path of script \e[3m%s\e[23m.\e[0m\n" "$script" >&2 && exit 1; }
            invoke "functions/$function" "$script_file" "$function_name" "$instance_name"
            exit_code=$?
        else
            local truncated="${script%%$'\n'*}" && [ "$truncated" != "$script" ] && truncated+="..."
            printf "\e[31mERROR: Script \e[3m%s\e[23m is neither executable nor starts it with \e[3m%s\e[23m.\e[0m\n" "$truncated" '#!' >&2
            exit 1
        fi
        ;;
    esac
    if [ "$exit_code" -ne 0 ]; then
        printf "\e[31mERROR: Failed to execute script \e[3m%s\e[23m for function \e[3m%s\e[23m.\e[0m\n" "$script_file" "$function" >&2
    fi
    return "$exit_code"
}

main() {
    local function=${1:?function missing} && shift
    if declare -F "$function" >/dev/null; then
        "$function" "$@"
    else
        printf "\e[31mERROR: No function with name \e[3m%s\e[23m exists.\e[0m\n" "$function" >&2
        exit 1
    fi
}

main "$@"
