# Purpose: Engine shared by the Pi Hero kaomoji scripts: painting styled graphemes, pacing an
#          animation on one line, the grid of all variants, and the command line. Sourced, never run.
# Usage:   . "$(dirname "${BASH_SOURCE[0]}")/kaomoji.bash"
#
# A kaomoji script defines a character <name> and ends with 'kaomoji_main <name> "$@"'. It provides:
#   <NAME>_MOODS       array of its moods, the first one is the default
#   <name>_frame       renders one frame into KAOMOJI_TEXT and its width in cells into KAOMOJI_WIDTH;
#                      options: --mood <mood>, --step <n> (static without it), --no-entrance,
#                      --exit <step>, --color (see hero_frame)
#   <name>_timeline    fills an array with the number of entrance steps, the steps of one hover
#                      cycle and the number of exit steps: <name>_timeline --mood <mood> <array>
# A frame paints exactly once with kaomoji_paint. Frames are deterministic and the hover frames
# repeat every cycle, so the engine renders each of them once and plays them from a cache.
# Needs bash 5.0+.

[ -z "${KAOMOJI_BASH:-}" ] || return 0
readonly KAOMOJI_BASH=1

# Bash slices strings by character only in a UTF-8 locale, and kaomoji are made of multibyte ones.
case ${LC_ALL:-${LC_CTYPE:-${LANG:-}}} in
*[Uu][Tt][Ff]-8* | *[Uu][Tt][Ff]8*) ;;
*) export LC_ALL=C.UTF-8 ;;
esac

# Every kaomoji script keeps its usage in the comment block after its shebang.
usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; }
die() { printf '%s: %s\nSee '\''%s --help'\''\n' "${0##*/}" "$1" "${0##*/}" >&2; exit 2; }

declare -A KAOMOJI_CAP=()    # capability with its arguments → sequence or count, see kaomoji_tput
declare -A KAOMOJI_SGR=()    # style → escape sequence, filled by kaomoji_sgr_fetch
declare -A KAOMOJI_WIDTHS=() # character → cells, filled by kaomoji_text_width

# Fills KAOMOJI_CAP with the given capabilities, in a single tput call for all missing ones:
# tput is a fork, 40 ms on a Raspberry Pi 1, and static plain output needs none at all. The
# batch output is split on sgr0, which is therefore fetched first.
#   <capability>...   a terminfo capability name with its arguments, e.g. "setaf 214"
kaomoji_tput() {
    if [ -z "${KAOMOJI_CAP[sgr0]+set}" ]; then KAOMOJI_CAP[sgr0]=$(tput sgr0 2>/dev/null || true); fi
    local cap list out sep=${KAOMOJI_CAP[sgr0]}
    local -a missing=()
    for cap; do [ -n "${KAOMOJI_CAP[$cap]+set}" ] || missing+=("$cap"); done
    ((${#missing[@]})) || return 0
    if [ -n "$sep" ]; then
        printf -v list '%s\nsgr0\n' "${missing[@]}"
        out=$(tput -S <<<"$list" 2>/dev/null || true)
        for cap in "${missing[@]}"; do
            KAOMOJI_CAP[$cap]=${out%%"$sep"*}
            KAOMOJI_CAP[$cap]=${KAOMOJI_CAP[$cap]%$'\n'} # a count like colors ends in a newline
            out=${out#*"$sep"}
        done
    else # a terminal without sgr0 has little else; ask for each
        for cap in "${missing[@]}"; do
            # shellcheck disable=SC2086 # a capability may carry arguments
            KAOMOJI_CAP[$cap]=$(tput $cap 2>/dev/null || true)
        done
    fi
}

# Sets REPLY to the number of terminal cells the given text occupies: two for East Asian wide
# characters, one for everything else (ambiguous ones included, as Western terminals render them).
kaomoji_text_width() {
    local text=$1 ch
    local -i i cp
    REPLY=0
    for ((i = 0; i < ${#text}; i++)); do
        ch=${text:i:1}
        if [ -z "${KAOMOJI_WIDTHS[$ch]+set}" ]; then
            printf -v cp '%d' "'$ch"
            if ((cp >= 0x1100 && (cp <= 0x115F ||
                (cp >= 0x2E80 && cp <= 0xA4CF && cp != 0x303F) || (cp >= 0xAC00 && cp <= 0xD7A3) ||
                (cp >= 0xF900 && cp <= 0xFAFF) || (cp >= 0xFE30 && cp <= 0xFE4F) ||
                (cp >= 0xFF00 && cp <= 0xFF60) || (cp >= 0xFFE0 && cp <= 0xFFE6) ||
                (cp >= 0x20000 && cp <= 0x3FFFD)))); then
                KAOMOJI_WIDTHS[$ch]=2
            else
                KAOMOJI_WIDTHS[$ch]=1
            fi
        fi
        REPLY=$((REPLY + KAOMOJI_WIDTHS[$ch]))
    done
}

# Appends the tput capabilities behind a style to an array. A style is "<fg>/<bg>" with color
# indices (either may be empty) or "dim". Colors are applied only if the terminal has all of
# the style's colors.
#   <style> <array>
kaomoji_style_caps() {
    local style=$1 fg bg
    local -n into=$2
    case $style in
    dim) into+=(dim) ;;
    */*)
        fg=${style%/*}
        bg=${style#*/}
        if ((${fg:-0} < ${KAOMOJI_CAP[colors]:-0} && ${bg:-0} < ${KAOMOJI_CAP[colors]:-0})); then
            [ -z "$fg" ] || into+=("setaf $fg")
            [ -z "$bg" ] || into+=("setab $bg")
        fi
        ;;
    *) die "${FUNCNAME[0]}: unknown style: $style" ;;
    esac
}

# Fills KAOMOJI_SGR for the given styles, fetching their capabilities in one go.
kaomoji_sgr_fetch() {
    kaomoji_tput colors
    local style cap
    local -a caps=() parts
    for style; do kaomoji_style_caps "$style" caps; done
    kaomoji_tput "${caps[@]}"
    for style; do
        parts=()
        kaomoji_style_caps "$style" parts
        KAOMOJI_SGR[$style]=''
        for cap in "${parts[@]}"; do KAOMOJI_SGR[$style]+=${KAOMOJI_CAP[$cap]}; done
    done
}

# Prints the graphemes of a sprite (no trailing newline) and sets REPLY to the display width printed.
# A sprite is an array of graphemes, each as "<style><TAB><text>", see kaomoji_style_caps for styles.
# Painting one leaves the text in KAOMOJI_TEXT and its display width in cells in KAOMOJI_WIDTH.
# A sprite is laid out once (kaomoji_layout), a painting is a substring of that layout: a frame
# then costs a handful of bash operations, which is what a Raspberry Pi 1 affords per frame.
#   --offset <n>   skip the first <n> graphemes; a negative <n> pads the left with spaces instead
#   --clip <n>     stop before the display width would exceed <n> (default: 0, no clipping)
#   --color        apply the styles
#   <array>        name of the sprite
KAOMOJI_TEXT=''
KAOMOJI_WIDTH=0
kaomoji_paint() {
    local -i offset=0 clip=0 color=0
    while [ $# -gt 0 ]; do
        case $1 in
        --offset) offset=${2?$1: missing value}; shift 2 ;;
        --offset=*) offset=${1#*=}; shift ;;
        --clip) clip=${2?$1: missing value}; shift 2 ;;
        --clip=*) clip=${1#*=}; shift ;;
        --color) color=1; shift ;;
        --) shift; break ;;
        -?*) die "${FUNCNAME[0]}: unknown option: $1" ;;
        *) break ;;
        esac
    done
    local -n graphemes=${1?${FUNCNAME[0]}: array name missing}

    local key="${#graphemes[@]}:${graphemes[*]}" # the count keeps an empty sprite's key non-empty
    if [ -z "${KAOMOJI_LAYOUTS[$key]+set}" ]; then kaomoji_layout "$1" "$key"; fi
    local id=${KAOMOJI_LAYOUTS[$key]}
    local -n cells=KAOMOJI_LAYOUT_${id}_CELLS
    if ((color)); then
        if [ -z "${KAOMOJI_COLORED[$id]+set}" ]; then kaomoji_layout_color "$1" "$id"; fi
        local -n text=KAOMOJI_LAYOUT_${id}_COLORED offsets=KAOMOJI_LAYOUT_${id}_COLORED_AT
    else
        local -n text=KAOMOJI_LAYOUT_${id}_PLAIN offsets=KAOMOJI_LAYOUT_${id}_PLAIN_AT
    fi

    local -i n=${#graphemes[@]} first=0 end pad=0
    if ((offset < 0)); then pad=-offset; elif ((offset < n)); then first=$offset; else first=$n; fi
    end=$n
    if ((clip > 0)); then
        for ((end = first; end < n && pad + cells[end + 1] - cells[first] <= clip; end++)); do :; done
    fi
    KAOMOJI_TEXT=${text:offsets[first]:offsets[end] - offsets[first]}
    if ((pad)); then printf -v KAOMOJI_TEXT '%*s%s' "$pad" '' "$KAOMOJI_TEXT"; fi
    KAOMOJI_WIDTH=$((pad + cells[end] - cells[first]))
}

# Lays out a sprite for kaomoji_paint: KAOMOJI_LAYOUT_<id>_PLAIN holds its text, _PLAIN_AT the
# offset in characters of every grapheme in it and of the end, _CELLS the display width up to
# every grapheme and up to the end. KAOMOJI_LAYOUTS maps the sprite's key to its <id>.
#   <array> <key>   name of the sprite and its key in KAOMOJI_LAYOUTS
declare -A KAOMOJI_LAYOUTS=()
kaomoji_layout() {
    local -n graphemes=$1
    local -i id=${#KAOMOJI_LAYOUTS[@]}
    declare -g "KAOMOJI_LAYOUT_${id}_PLAIN="
    declare -ga "KAOMOJI_LAYOUT_${id}_PLAIN_AT=(0)" "KAOMOJI_LAYOUT_${id}_CELLS=(0)"
    local -n plain=KAOMOJI_LAYOUT_${id}_PLAIN offsets=KAOMOJI_LAYOUT_${id}_PLAIN_AT cells=KAOMOJI_LAYOUT_${id}_CELLS
    local text
    local -i i chars=0 width=0
    for ((i = 0; i < ${#graphemes[@]}; i++)); do
        text=${graphemes[i]#*$'\t'}
        if [ -z "${KAOMOJI_WIDTHS[$text]+set}" ]; then
            kaomoji_text_width "$text"
            KAOMOJI_WIDTHS[$text]=$REPLY
        fi
        plain+=$text
        chars+=${#text}
        width+=${KAOMOJI_WIDTHS[$text]}
        offsets+=("$chars")
        cells+=("$width")
    done
    KAOMOJI_LAYOUTS[$2]=$id
}

# Adds the colored text to a layout: KAOMOJI_LAYOUT_<id>_COLORED and _COLORED_AT, like the plain
# ones, and notes it in KAOMOJI_COLORED. The styles of the sprite are fetched in one go first.
#   <array> <id>
declare -A KAOMOJI_COLORED=()
kaomoji_layout_color() {
    local -n graphemes=$1
    local id=$2
    local style text sgr0
    local -a missing=()
    local -i i chars=0
    for ((i = 0; i < ${#graphemes[@]}; i++)); do
        style=${graphemes[i]%%$'\t'*}
        [ -n "${KAOMOJI_SGR[$style]+set}" ] || missing+=("$style")
    done
    ((${#missing[@]} == 0)) || kaomoji_sgr_fetch "${missing[@]}"
    sgr0=${KAOMOJI_CAP[sgr0]}
    declare -g "KAOMOJI_LAYOUT_${id}_COLORED="
    declare -ga "KAOMOJI_LAYOUT_${id}_COLORED_AT=(0)"
    local -n colored=KAOMOJI_LAYOUT_${id}_COLORED offsets=KAOMOJI_LAYOUT_${id}_COLORED_AT
    for ((i = 0; i < ${#graphemes[@]}; i++)); do
        style=${graphemes[i]%%$'\t'*}
        text="${KAOMOJI_SGR[$style]}${graphemes[i]#*$'\t'}$sgr0"
        colored+=$text
        chars+=${#text}
        offsets+=("$chars")
    done
    KAOMOJI_COLORED[$id]=1
}

# Fills an array with a sprite, building it once: the builder runs with its arguments and the
# array on the first call, later calls with the same arguments copy the result.
#   <array> <builder> [<argument>...]
declare -A KAOMOJI_SPRITES=() # builder with its arguments → the array holding the sprite
kaomoji_sprite() {
    local -n result=$1
    local key=${*:2}
    if [ -n "${KAOMOJI_SPRITES[$key]+set}" ]; then
        local -n built=${KAOMOJI_SPRITES[$key]}
        result=("${built[@]}")
        return 0
    fi
    "${@:2}" "$1"
    local name=KAOMOJI_SPRITE_${#KAOMOJI_SPRITES[@]}
    declare -ga "$name"
    local -n store=$name
    store=("${result[@]}")
    KAOMOJI_SPRITES[$key]=$name
}

# Renders a frame through <name>_frame once: the same arguments give the same frame, so later
# calls come from the cache. Leaves KAOMOJI_TEXT and KAOMOJI_WIDTH like the frame does.
#   <name>   the character, followed by the arguments of <name>_frame
declare -A KAOMOJI_FRAME_TEXT=() KAOMOJI_FRAME_WIDTH=()
kaomoji_frame() {
    local key=$*
    if [ -n "${KAOMOJI_FRAME_TEXT[$key]+set}" ]; then
        KAOMOJI_TEXT=${KAOMOJI_FRAME_TEXT[$key]}
        KAOMOJI_WIDTH=${KAOMOJI_FRAME_WIDTH[$key]}
        return 0
    fi
    "${1}_frame" "${@:2}"
    KAOMOJI_FRAME_TEXT[$key]=$KAOMOJI_TEXT
    KAOMOJI_FRAME_WIDTH[$key]=$KAOMOJI_WIDTH
}

# Renders the frame of a step of an animation, from the cache where possible: hover steps map
# onto the first cycle, and the exit is passed on only once it has begun.
#   <name> <mood> <step> <entrance> <cycle> <exit>   entrance and cycle in steps, exit the step
#                                                    after which the exit begins, -1 for none
#   <flag>...                                        --color, --no-entrance
kaomoji_step_frame() {
    local name=$1 mood=$2
    local -i step=$3 entrance=$4 cycle=$5 exit_step=$6
    shift 6
    if ((exit_step >= 0 && step > exit_step)); then
        kaomoji_frame "$name" --mood "$mood" --step "$step" --exit "$exit_step" "$@"
    else
        if ((step > entrance)); then step=$((entrance + 1 + (step - entrance - 1) % cycle)); fi
        kaomoji_frame "$name" --mood "$mood" --step "$step" "$@"
    fi
}

# Paces an animation: sleeps until the current frame has been shown for <ms> milliseconds.
# Every frame but the last is followed by a call to this function, which is what kaomoji-gif
# hooks into.
#   <ms>      how long a frame stays
#   <since>   when it was shown, as ${EPOCHREALTIME/./} (microseconds)
kaomoji_sleep_ms() {
    local -i left=$(($2 + $1 * 1000 - ${EPOCHREALTIME/./}))
    ((left > 0)) || return 0
    local pause
    printf -v pause '%d.%06d' "$((left / 1000000))" "$((left % 1000000))"
    # A read timing out on a pipe of our own, as sleep is a fork: 35 ms on a Raspberry Pi 1.
    # Either may be cut short by a signal; the trap decides what happens then.
    if [ -n "${KAOMOJI_TICK:-}" ]; then read -rt "$pause" -u "$KAOMOJI_TICK" || :; else sleep "$pause" || :; fi
}

# What a signal does during an animation: quit at once, leaving the cursor on a fresh line.
readonly KAOMOJI_QUIT='printf "\n"; exit 130'

# Hides the cursor for an animation and brings it back when the script ends, also on Ctrl-C.
kaomoji_animation_begin() {
    kaomoji_tput civis cnorm el cuu1 colors
    trap 'printf "%s" "${KAOMOJI_CAP[cnorm]}"' EXIT
    trap "$KAOMOJI_QUIT" INT
    printf '%s' "${KAOMOJI_CAP[civis]}"
    # The pipe kaomoji_sleep_ms waits on: a FIFO opened for reading and writing never sees EOF.
    local fifo=${TMPDIR:-/tmp}/kaomoji.$$
    if mkfifo -m 600 "$fifo" 2>/dev/null; then
        exec {KAOMOJI_TICK}<>"$fifo"
        rm -f "$fifo"
    fi
}

kaomoji_animation_end() {
    printf '%s' "${KAOMOJI_CAP[cnorm]}"
    trap - EXIT INT
    if [ -n "${KAOMOJI_TICK:-}" ]; then
        exec {KAOMOJI_TICK}>&-
        unset KAOMOJI_TICK
    fi
}

# Animates a single kaomoji on the current line and ends it with a newline.
#   <name>            the character
#   --mood <mood>     one of its moods (default: its first)
#   --color           colored output
#   --no-entrance     skip the entrance and start hovering right away
#   --loops <n>       stop after <n> hover cycles (default: -1, endless)
#   --exit            play the exit after the last hover cycle; while endless, when the script is
#                     stopped by SIGINT or SIGTERM, a second signal quitting at once
#   --frame-ms <ms>   delay between frames (default: 50)
kaomoji_animate() {
    local name=${1?${FUNCNAME[0]}: character name missing}
    shift
    local -n moods=${name^^}_MOODS
    local mood=${moods[0]}
    local -a flags=() # passed on to the frame
    local -i entrance=1 exit=0 loops=-1 frame_ms=50
    while [ $# -gt 0 ]; do
        case $1 in
        --mood) mood=${2?$1: missing value}; shift 2 ;;
        --mood=*) mood=${1#*=}; shift ;;
        --color) flags+=(--color); shift ;;
        --no-entrance) entrance=0; flags+=(--no-entrance); shift ;;
        --exit) exit=1; shift ;;
        --loops) loops=${2?$1: missing value}; shift 2 ;;
        --loops=*) loops=${1#*=}; shift ;;
        --frame-ms) frame_ms=${2?$1: missing value}; shift 2 ;;
        --frame-ms=*) frame_ms=${1#*=}; shift ;;
        -?*) die "${FUNCNAME[0]}: unknown option: $1" ;;
        *) die "${FUNCNAME[0]}: unexpected argument: $1" ;;
        esac
    done

    local -a timeline
    "${name}_timeline" --mood "$mood" timeline
    local -i entrance_steps=${timeline[0]} cycle=${timeline[1]} exit_steps=${timeline[2]}
    local -i first=0 last=-1 exit_step=-1 step stop=0 shown
    if ((!entrance)); then first=$((entrance_steps + 1)); fi # the first hover step
    if ((loops >= 0)); then
        last=$((entrance_steps + loops * cycle))
        if ((exit)); then
            exit_step=$last
            last=$((last + exit_steps))
        fi
    fi
    kaomoji_animation_begin
    if ((exit && loops < 0)); then trap 'stop=1' INT TERM; fi # endless: leave when stopped
    kaomoji_step_frame "$name" "$mood" "$first" "$entrance_steps" "$cycle" "$exit_step" "${flags[@]}"
    for ((step = first; ; step++)); do
        shown=${EPOCHREALTIME/./}
        printf '\r%s%s' "$KAOMOJI_TEXT" "${KAOMOJI_CAP[el]}"
        if ((last >= 0 && step >= last)); then break; fi
        # the next frame renders while this one shows
        kaomoji_step_frame "$name" "$mood" "$((step + 1))" "$entrance_steps" "$cycle" "$exit_step" "${flags[@]}"
        kaomoji_sleep_ms "$frame_ms" "$shown"
        if ((stop)); then # leave from the current step
            stop=0
            trap "$KAOMOJI_QUIT" INT
            trap - TERM
            exit_step=$step
            last=$((step + exit_steps))
            kaomoji_step_frame "$name" "$mood" "$((step + 1))" "$entrance_steps" "$cycle" "$exit_step" "${flags[@]}"
        fi
    done
    printf '\n'
    kaomoji_animation_end
}

# Prints a grid of all variants: one row per mood, one column per style
# (static and animated, each plain and colored). The animated columns play in place.
#   <name>            the character
#   --mood <mood>     only this mood's row (default: all moods)
#   --no-entrance     skip the entrance and start hovering right away
#   --loops <n>       stop after <n> hover cycles (default: -1, endless)
#   --exit            play the exit after the last hover cycle
#   --frame-ms <ms>   delay between frames (default: 50)
kaomoji_grid() {
    local name=${1?${FUNCNAME[0]}: character name missing}
    shift
    local -n all_moods=${name^^}_MOODS
    local -a moods=("${all_moods[@]}")
    local -i entrance=1 exit=0 loops=-1 frame_ms=50
    local -a flags=() # passed on to the frame
    while [ $# -gt 0 ]; do
        case $1 in
        --mood) moods=("${2?$1: missing value}"); shift 2 ;;
        --mood=*) moods=("${1#*=}"); shift ;;
        --no-entrance) entrance=0; flags=(--no-entrance); shift ;;
        --exit) exit=1; shift ;;
        --loops) loops=${2?$1: missing value}; shift 2 ;;
        --loops=*) loops=${1#*=}; shift ;;
        --frame-ms) frame_ms=${2?$1: missing value}; shift 2 ;;
        --frame-ms=*) frame_ms=${1#*=}; shift ;;
        -?*) die "${FUNCNAME[0]}: unknown option: $1" ;;
        *) die "${FUNCNAME[0]}: unexpected argument: $1" ;;
        esac
    done

    local -a titles=('static plain' 'static color' 'animated plain' 'animated color')
    local dim sgr0
    kaomoji_sgr_fetch dim
    dim=${KAOMOJI_SGR[dim]}
    sgr0=${KAOMOJI_CAP[sgr0]}

    # The label column fits every mood, a cell fits its title and every frame of a hover cycle,
    # and each mood's animation runs from its own first to its own last step.
    local -i label=4 cell=0 i s last=0
    local -a timeline entrances=() cycles=() first_steps=() exit_steps=() last_steps=()
    local mood title
    for title in "${titles[@]}"; do
        if ((${#title} > cell)); then cell=${#title}; fi
    done
    for i in "${!moods[@]}"; do
        mood=${moods[i]}
        if ((${#mood} > label)); then label=${#mood}; fi
        "${name}_timeline" --mood "$mood" timeline
        entrances[i]=${timeline[0]}
        cycles[i]=${timeline[1]}
        for ((s = timeline[0]; s <= timeline[0] + timeline[1]; s++)); do
            kaomoji_step_frame "$name" "$mood" "$s" "${entrances[i]}" "${cycles[i]}" -1 "${flags[@]}"
            if ((KAOMOJI_WIDTH > cell)); then cell=$KAOMOJI_WIDTH; fi
        done
        first_steps[i]=$((entrance ? 0 : timeline[0] + 1))
        exit_steps[i]=$((exit && loops >= 0 ? timeline[0] + loops * timeline[1] : -1))
        last_steps[i]=$((timeline[0] + loops * timeline[1] + (exit ? timeline[2] : 0))) # meaningless while endless
        if ((last_steps[i] - first_steps[i] > last)); then last=$((last_steps[i] - first_steps[i])); fi
    done

    # The header and the rows are separated by empty lines; all of them are redrawn per step.
    local -i rows=$((1 + 2 * ${#moods[@]})) step shown
    printf '\n'
    kaomoji_animation_begin
    for ((step = 0; ; step++)); do
        shown=${EPOCHREALTIME/./}
        if ((step > 0)); then
            for ((i = 0; i < rows; i++)); do printf '%s' "${KAOMOJI_CAP[cuu1]}"; done
        fi
        printf '%s%-*s' "$dim" "$label" mood
        for title in "${titles[@]}"; do printf ' %-*s' "$cell" "$title"; done
        printf '%s%s\n' "$sgr0" "${KAOMOJI_CAP[el]}"
        for i in "${!moods[@]}"; do
            printf '%s\n' "${KAOMOJI_CAP[el]}"
            mood=${moods[i]}
            s=$((first_steps[i] + step))
            if ((loops >= 0 && s > last_steps[i])); then s=${last_steps[i]}; fi
            printf '%s%-*s%s' "$dim" "$label" "$mood" "$sgr0"
            kaomoji_frame "$name" --mood "$mood"
            printf ' %s%*s' "$KAOMOJI_TEXT" "$((cell - KAOMOJI_WIDTH))" ''
            kaomoji_frame "$name" --mood "$mood" --color
            printf ' %s%*s' "$KAOMOJI_TEXT" "$((cell - KAOMOJI_WIDTH))" ''
            kaomoji_step_frame "$name" "$mood" "$s" "${entrances[i]}" "${cycles[i]}" "${exit_steps[i]}" "${flags[@]}"
            printf ' %s%*s' "$KAOMOJI_TEXT" "$((cell - KAOMOJI_WIDTH))" ''
            kaomoji_step_frame "$name" "$mood" "$s" "${entrances[i]}" "${cycles[i]}" "${exit_steps[i]}" "${flags[@]}" --color
            printf ' %s%*s' "$KAOMOJI_TEXT" "$((cell - KAOMOJI_WIDTH))" ''
            printf '%s\n' "${KAOMOJI_CAP[el]}"
        done
        if ((loops >= 0 && step >= last)); then break; fi
        kaomoji_sleep_ms "$frame_ms" "$shown"
    done
    printf '\n'
    kaomoji_animation_end
}

# The command line every kaomoji script shares, see the usage of hero. Every call prints one
# kaomoji, static unless animated; only --help and --preview print something else.
#   <name>   the character, followed by the script's arguments
kaomoji_main() {
    local name=${1?${FUNCNAME[0]}: character name missing}
    shift
    local -n moods=${name^^}_MOODS
    local use_color=''
    local -a mood_flag=() flags=() # passed on to the grid or the animation
    local -i animate=0 preview=0 loops=-1 frame_ms=50
    while [ $# -gt 0 ]; do
        case $1 in
        -h | --help) usage; exit 0 ;;
        --mood) mood_flag=(--mood "${2?--mood: missing value}"); shift 2 ;;
        --mood=*) mood_flag=(--mood "${1#*=}"); shift ;;
        --preview) preview=1; shift ;;
        --animate) animate=1; shift ;;
        --no-entrance) animate=1; flags+=(--no-entrance); shift ;;
        --exit) animate=1; flags+=(--exit); shift ;;
        --color) use_color=1; shift ;;
        --no-color) use_color=0; shift ;;
        --loops) animate=1; loops=${2?--loops: missing value}; shift 2 ;;
        --loops=*) animate=1; loops=${1#*=}; shift ;;
        --frame-ms) animate=1; frame_ms=${2?--frame-ms: missing value}; shift 2 ;;
        --frame-ms=*) animate=1; frame_ms=${1#*=}; shift ;;
        -?*) die "unknown option: $1" ;;
        *) die "unexpected argument: $1" ;;
        esac
    done

    if [ "${#mood_flag[@]}" -gt 0 ]; then
        case " ${moods[*]} " in
        *" ${mood_flag[1]} "*) ;;
        *) die "unknown mood: ${mood_flag[1]}" ;;
        esac
    fi

    if ((preview)); then
        kaomoji_grid "$name" "${mood_flag[@]}" "${flags[@]}" --loops "$loops" --frame-ms "$frame_ms"
        return 0
    fi

    if [ -z "$use_color" ]; then
        if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then use_color=1; else use_color=0; fi
    fi
    local -a color_flag=()
    if ((use_color)); then color_flag=(--color); fi

    if ((animate)); then
        kaomoji_animate "$name" "${mood_flag[@]}" "${color_flag[@]}" "${flags[@]}" --loops "$loops" --frame-ms "$frame_ms"
    else
        kaomoji_frame "$name" "${mood_flag[@]}" "${color_flag[@]}"
        printf '%s\n' "$KAOMOJI_TEXT"
    fi
}
