# Prints the Pi Hero kaomoji in the given mood.
# Globals:
#   None
# Arguments:
#   moods (flag, optional): If specified, print one kaomoji for each mood.
#   mood (string, default: neutral): The mood to use.
#   frame (int, default: -1): The frame index of the animation to use.
#   offset (int, default: 0): The number of characters to drop from the left. Negative values pad the left side with spaces.
# Outputs:
#   1: The kaomoji in the given mood.
# Returns:
#   0: Always
hero() {
    local mood=neutral face
    local -i frame=-1 offset=0

    if [ $# -gt 0 ] && [ "$1" = --moods ]; then
        shift
        local rows=()
        for mood in neutral happy sad unknown; do
            m=$(gum style --faint "$mood")
            k=$(CLICOLOR_FORCE=${CLICOLOR_FORCE-1} hero --mood "$mood" "$@")
            row=$(gum join --vertical --align center "$k" '' "$m")
            rows+=("$(gum style --padding "1 2" "$row")")
        done
        gum join --vertical "${rows[@]}"
        exit
    fi

    while [ $# -gt 0 ]; do
        case "$1" in
        --mood=*)
            mood="${1#*=}" && shift
            ;;
        --mood)
            shift && mood=${1?mood: parameter value not set} && shift
            ;;
        --frame=*)
            frame="${1#*=}" && shift
            ;;
        --frame)
            shift && frame=${1?frame: parameter value not set} && shift
            ;;
        --offset=*)
            offset="${1#*=}" && shift
            ;;
        --offset)
            shift && offset=${1?offset: parameter value not set} && shift
            ;;
        *)
            break
            ;;
        esac
    done

    local graphemes=()
    {
        # add tail graphemes
        local tails=("─=-" "──=" "──-" "──≡" "─=≡") tail_char
        while IFS='' read -r tail_char; do
            graphemes+=('{{ Foreground "3" "'"$tail_char"'" }}')
        done < <(echo "${tails[$((frame % ${#tails[@]}))]}" | grep -o .)

        # add cape graphemes
        graphemes+=(
            '{{ Foreground "9" "Σ" }}'
            '{{ Color "8" "9" "(" }}'
            '{{ Color "8" "9" "(" }}'
        )

        # add face graphemes
        case "$mood" in
        neutral)
            face=(' ' '蓬' '•' 'ｏ' '•' '')
            ;;
        0 | happy)
            face=('' '✿' '＾' 'ｖ' '＾' '')
            ;;
        1 | 2 | sad)
            face=(' ' '༶' '◕' '︿' '◕' ' ')
            ;;
        *)
            face=('' '༶' '´⊙' '﹏' '⊙`' '')
            ;;
        esac
        graphemes+=(
            '{{ Color "0" "3" "[" }}'
            ${face[0]:+'{{ Color "0" "3" "'"${face[0]}"'" }}'} # drop if empty
            ${face[1]:+'{{ Color "1" "3" "'"${face[1]}"'" }}'} # drop if empty
            ${face[2]:+'{{ Color "0" "3" "'"${face[2]}"'" }}'} # drop if empty
            ${face[3]:+'{{ Color "9" "3" "'"${face[3]}"'" }}'} # drop if empty
            ${face[4]:+'{{ Color "0" "3" "'"${face[4]}"'" }}'} # drop if empty
            ${face[5]:+'{{ Color "1" "3" "'"${face[5]}"'" }}'} # drop if empty
            '{{ Color "0" "3" "]" }}'
        )

        # add hand graphemes
        local hands=("⫎" "⊐") hand_char
        while IFS='' read -r hand_char; do
            graphemes+=('{{ Foreground "11" "'"$hand_char"'" }}')
        done < <(echo "${hands[$((frame % ${#hands[@]}))]}" | grep -o .)
    }

    # apply offset
    {
        if [ "$offset" -lt 0 ]; then
            # pad the left side with spaces
            for (( ; offset < 0; offset++)); do
                graphemes=(' ' "${graphemes[@]}")
            done
        else
            # truncate the left side
            graphemes=("${graphemes[@]:$offset}")
        fi
    }

    gum format --type template "$(printf '%s' "${graphemes[@]}")"
}

# Prints all frames line by line that create the animation of
# the Pi Hero kaomoji flying-in from the left.
# Globals:
#   CLICOLOR_FORCE: If set and not 0, the output is colored.
#   NO_COLORS: If set and not 0, the colors are suppressed.
# Arguments:
#   None
# Outputs:
#   1: Frames of the animation separated by newlines.
# Returns:
#   0: Frames successfully printed.
#   1: An error occurred.
hero_frames() {
    local frame offset length raw_hero
    raw_hero=$(CLICOLOR_FORCE=0 NO_COLORS=1 hero)
    length=${#raw_hero}
    # fly-in
    local last
    for frame in $(seq -1 "$((length))"); do
        offset=$((length - 1 - frame))
        last=$(hero "$@" --frame "$frame" --offset "$offset")
        printf '%s\n' "$last"
    done
    # loop until animation repeats itself
    local curr
    while true; do
        frame=$((frame + 1))
        curr=$(hero "$@" --frame "$frame" --offset "$offset")
        [ ! "$curr" = "$last" ] || break
        printf '%s\n' "$curr"
    done
}

#restore_terminal_state() {
#		p.renderer.showCursor()
#		p.renderer.disableMouseCellMotion()
#		p.renderer.disableMouseAllMotion()
#
#		if p.renderer.altScreen() {
#			p.renderer.exitAltScreen()
#
#			// give the terminal a moment to catch up
#			time.Sleep(time.Millisecond * 10) //nolint:gomnd
#		}
#
#		err := p.console.Reset()
#		if err != nil {
#			return fmt.Errorf("error restoring terminal state: %w", err)
#		}
#
#	 p.restoreInput()
#}

# Runs tput -S with each argument appearing on a separate line.
tputs() {
    printf '%s\n' "$@" | tput -S
}

# Prints all frames line by line that create the animation of
# the Pi Hero kaomoji flying-in from the left.
# Globals:
#   None
# Arguments:
#   margin (int, default: 0): Number of empty lines to print before and after the animation.
#   loops (int, default: 0): Number of loops to play, for unlimited use -1.
#   $@: file ...: files containing the frames of the animation; use - for stdin
# Outputs:
#   1: TODO
# Returns:
#   0: Frames successfully printed.
#   1: An error occurred.
hero_animate() {
    local margin=0
    local -i loops=0
    local -i loop_frames=10
    while [ $# -gt 0 ]; do
        case "$1" in
        --margin=*)
            margin="${1#*=}" && shift
            ;;
        --margin)
            shift && margin=${1?margin: parameter value not set} && shift
            ;;
        --loops=*)
            loops="${1#*=}" && shift
            ;;
        --loops)
            shift && loops=${1?loops: parameter value not set} && shift
            ;;
        *)
            break
            ;;
        esac
    done

    local prefix='' postfix=''
    for (( ; margin > 0; margin--)); do
        prefix="$prefix"$'\n'
        postfix="$postfix"$'\n'
    done
    postfix="${postfix%$'\n'}"
    prefix=''
    postfix=''

    local loop_buffer && loop_buffer=$(mktemp)
    #    trap "printf '\n\e8\e[?25h'" EXIT # restore cursor position and show cursor
    trap 'tput cub "$(tput cols)"
          tput el
          tput cnorm
         ' EXIT # restore cursor position and show cursor
    {
        # store cursor \e8
        tput civis # hide cursor
    }

    while read -r frame; do
        tputs "cub $(tput cols)" "el" # move the cursor to the start of the line and clear the line
        printf '%s%s%s' "$prefix" "$frame" "$postfix"
        sleep 0.04
    done < <(
        if [ "$loops" -eq 0 ]; then
            # no loops: just print the frames once
            cat "$@"
        else
            # looping: save the last frames of the read frames in a buffer
            cat "$@" | tee >(tail -"$loop_frames" >"$loop_buffer")
            # print the buffer until loops are reached or the buffer no longer exists
            while [ "$loops" -ne 0 ] && [ -f "$loop_buffer" ]; do
                cat "$loop_buffer" || exit # if anything goes wrong, reading from the buffer, exit
                [ "$loops" -lt 0 ] || loops=$((loops - 1))
            done
        fi
    )
}
# "q", "esc", "ctrl+c"
# \n\n   %s Loading forever...press q to quit\n\n
hero_animate_static() {

    hero_animate <(printf '%s' '
[93m⫎[0m
[30;43m][0m[93m⊐[0m
[30;43m•[0m[30;43m][0m[93m⫎[0m
[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⊐[0m
[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⫎[0m
[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⊐[0m
[30;43m [0m[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⫎[0m
[30;43m[[0m[30;43m [0m[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⊐[0m
[90;101m([0m[30;43m[[0m[30;43m [0m[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⫎[0m
[90;101m([0m[90;101m([0m[30;43m[[0m[30;43m [0m[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⊐[0m
[91mΣ[0m[90;101m([0m[90;101m([0m[30;43m[[0m[30;43m [0m[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⫎[0m
[33m=[0m[91mΣ[0m[90;101m([0m[90;101m([0m[30;43m[[0m[30;43m [0m[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⊐[0m
[33m─[0m[33m-[0m[91mΣ[0m[90;101m([0m[90;101m([0m[30;43m[[0m[30;43m [0m[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⫎[0m
[33m─[0m[33m─[0m[33m≡[0m[91mΣ[0m[90;101m([0m[90;101m([0m[30;43m[[0m[30;43m [0m[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⊐[0m
 [33m─[0m[33m=[0m[33m≡[0m[91mΣ[0m[90;101m([0m[90;101m([0m[30;43m[[0m[30;43m [0m[31;43m蓬[0m[30;43m•[0m[91;43mｏ[0m[30;43m•[0m[30;43m][0m[93m⫎[0m
')
}
