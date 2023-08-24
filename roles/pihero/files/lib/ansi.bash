# Prints the content of the given files with ANSI escape sequences removed.
# Globals:
#   None
# Arguments:
#   $@ (file ...): files to read
# Outputs:
#   File contents with ANSI escape sequences removed
# Returns:
#   0: The files contents were stripped of ANSI escape sequences.
#   1: An error occurred.
remove_ansi_escapes() {
    local pattern
    local patterns=(
        '\x1b][[:digit:]]*\;[^\x1b]*\x1b\\' # OSC escape sequences
        '\x1b[@-Z\\-_]'                     # Fe escape sequences
        '\x1b[ -/][@-~]'                    # 2-byte sequences
        '\x1b[[0-?]*[ -/]*[@-~]'            # CSI escape sequences
    )
    printf -v pattern 's|%s||g;' "${patterns[@]}"
    LC_ALL=C sed "$pattern"
}
