# Purpose: Engine shared by the Pi Hero kaomoji scripts: painting styled graphemes, pacing an
#          animation on one line, the grid of all variants, and the command line. Sourced, never run.
# Usage:   . "$(dirname "${BASH_SOURCE[0]}")/kaomoji.bash"
#
# A kaomoji script defines a character <name> and ends with 'kaomoji_main <name> "$@"'. It provides:
#   <NAME>_MOODS       array of its moods, the first one is the default
#   <name>_frame       prints one frame; options: --mood <mood>, --step <n> (static without it),
#                      --no-entrance, --exit <step>, --width <n>, --color (see hero_frame)
#   <name>_timeline    fills an array with the number of entrance steps, the steps of one hover
#                      cycle and the number of exit steps: <name>_timeline --mood <mood> <array>
# A frame paints exactly once with kaomoji_paint, which leaves its display width in REPLY.
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

# Terminal capabilities, resolved once: tput is slow enough to make animations stutter.
KAOMOJI_COLORS=$(tput colors 2>/dev/null || echo 0)
KAOMOJI_SGR0=$(tput sgr0 2>/dev/null || true)
KAOMOJI_CIVIS=$(tput civis 2>/dev/null || true)
KAOMOJI_CNORM=$(tput cnorm 2>/dev/null || true)
KAOMOJI_CUU1=$(tput cuu1 2>/dev/null || true)
KAOMOJI_EL=$(tput el 2>/dev/null || true)
readonly KAOMOJI_COLORS KAOMOJI_SGR0 KAOMOJI_CIVIS KAOMOJI_CNORM KAOMOJI_CUU1 KAOMOJI_EL
declare -A KAOMOJI_SGR=()    # style → escape sequence, filled by kaomoji_sgr_cache
declare -A KAOMOJI_WIDTHS=() # character → cells, filled by kaomoji_text_width

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

# Makes sure KAOMOJI_SGR[<style>] holds the escape sequence that starts the style.
# A style is "<fg>/<bg>" with color indices (either may be empty) or "dim". Colors are applied
# only if the terminal has all of the style's colors.
kaomoji_sgr_cache() {
    local style=$1
    [ -z "${KAOMOJI_SGR[$style]+set}" ] || return 0
    local seq='' fg bg
    case $style in
    dim) seq=$(tput dim 2>/dev/null || true) ;;
    */*)
        fg=${style%/*}
        bg=${style#*/}
        if ((${fg:-0} < KAOMOJI_COLORS && ${bg:-0} < KAOMOJI_COLORS)); then
            [ -z "$fg" ] || seq+=$(tput setaf "$fg" 2>/dev/null || true)
            [ -z "$bg" ] || seq+=$(tput setab "$bg" 2>/dev/null || true)
        fi
        ;;
    *) die "${FUNCNAME[0]}: unknown style: $style" ;;
    esac
    KAOMOJI_SGR[$style]=$seq
}

# Prints the graphemes of a sprite (no trailing newline) and sets REPLY to the display width printed.
# A sprite is an array of graphemes, each as "<style><TAB><text>", see kaomoji_sgr_cache for styles.
#   --offset <n>   drop <n> graphemes from the left, or pad the left with -<n> spaces if negative (default: 0)
#   --width <n>    pad the right with spaces up to a display width of <n> (default: 0)
#   --clip <n>     drop the graphemes that don't fit into a display width of <n> (default: 0, keep all)
#   --color        apply the styles
#   <array>        name of the sprite array
kaomoji_paint() {
    local -i offset=0 width=0 clip=0 color=0
    while [ $# -gt 0 ]; do
        case $1 in
        --offset) offset=${2?$1: missing value}; shift 2 ;;
        --offset=*) offset=${1#*=}; shift ;;
        --width) width=${2?$1: missing value}; shift 2 ;;
        --width=*) width=${1#*=}; shift ;;
        --clip) clip=${2?$1: missing value}; shift 2 ;;
        --clip=*) clip=${1#*=}; shift ;;
        --color) color=1; shift ;;
        --) shift; break ;;
        -?*) die "${FUNCNAME[0]}: unknown option: $1" ;;
        *) break ;;
        esac
    done
    local -n graphemes=${1?${FUNCNAME[0]}: array name missing}

    local out='' pad style text
    local -i i shown=0
    if ((offset < 0)); then
        printf -v out '%*s' "$((-offset))" ''
        shown=-offset
        offset=0
    fi
    for ((i = offset; i < ${#graphemes[@]}; i++)); do
        style=${graphemes[i]%%$'\t'*}
        text=${graphemes[i]#*$'\t'}
        kaomoji_text_width "$text"
        if ((clip > 0 && shown + REPLY > clip)); then break; fi
        shown+=REPLY
        if ((color)); then
            kaomoji_sgr_cache "$style"
            out+="${KAOMOJI_SGR[$style]}$text$KAOMOJI_SGR0"
        else
            out+=$text
        fi
    done
    if ((shown < width)); then
        printf -v pad '%*s' "$((width - shown))" ''
        out+=$pad
        shown=$width
    fi
    printf '%s' "$out"
    REPLY=$shown
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
    trap 'printf "%s" "$KAOMOJI_CNORM"' EXIT
    trap "$KAOMOJI_QUIT" INT
    printf '%s' "$KAOMOJI_CIVIS"
    # The pipe kaomoji_sleep_ms waits on: a FIFO opened for reading and writing never sees EOF.
    local fifo=${TMPDIR:-/tmp}/kaomoji.$$
    if mkfifo -m 600 "$fifo" 2>/dev/null; then
        exec {KAOMOJI_TICK}<>"$fifo"
        rm -f "$fifo"
    fi
}

kaomoji_animation_end() {
    printf '%s' "$KAOMOJI_CNORM"
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
    local -a color=() flags=() # flags are passed on to the frame
    local -i entrance=1 exit=0 loops=-1 frame_ms=50
    while [ $# -gt 0 ]; do
        case $1 in
        --mood) mood=${2?$1: missing value}; shift 2 ;;
        --mood=*) mood=${1#*=}; shift ;;
        --color) color=(--color); shift ;;
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
    local -i first=0 last=-1 step stop=0 shown
    if ((!entrance)); then first=$((timeline[0] + 1)); fi # the first hover step
    if ((loops >= 0)); then
        last=$((timeline[0] + loops * timeline[1]))
        if ((exit)); then
            flags+=(--exit "$last")
            last=$((last + timeline[2]))
        fi
    fi
    kaomoji_animation_begin
    if ((exit && loops < 0)); then trap 'stop=1' INT TERM; fi # endless: leave when stopped
    for ((step = first; ; step++)); do
        shown=${EPOCHREALTIME/./}
        printf '\r'
        "${name}_frame" --mood "$mood" --step "$step" "${color[@]}" "${flags[@]}"
        printf '%s' "$KAOMOJI_EL"
        if ((last >= 0 && step >= last)); then break; fi
        kaomoji_sleep_ms "$frame_ms" "$shown"
        if ((stop)); then # leave from the current step
            stop=0
            trap "$KAOMOJI_QUIT" INT
            trap - TERM
            flags+=(--exit "$step")
            last=$((step + timeline[2]))
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
    local dim
    kaomoji_sgr_cache dim
    dim=${KAOMOJI_SGR[dim]}

    # The label column fits every mood, a cell fits its title and every frame of a hover cycle,
    # and each mood's animation runs from its own first to its own last step.
    local -i label=4 cell=0 i s last=0
    local -a timeline first_steps=() exit_steps=() last_steps=() exit_flags=()
    local mood title
    for title in "${titles[@]}"; do
        if ((${#title} > cell)); then cell=${#title}; fi
    done
    for i in "${!moods[@]}"; do
        mood=${moods[i]}
        if ((${#mood} > label)); then label=${#mood}; fi
        "${name}_timeline" --mood "$mood" timeline
        for ((s = timeline[0]; s <= timeline[0] + timeline[1]; s++)); do
            "${name}_frame" --mood "$mood" --step "$s" "${flags[@]}" >/dev/null
            if ((REPLY > cell)); then cell=$REPLY; fi
        done
        first_steps[i]=$((entrance ? 0 : timeline[0] + 1))
        exit_steps[i]=$((timeline[0] + loops * timeline[1]))              # meaningless while endless
        last_steps[i]=$((exit_steps[i] + (exit ? timeline[2] : 0)))
        if ((last_steps[i] - first_steps[i] > last)); then last=$((last_steps[i] - first_steps[i])); fi
    done

    # The header and the rows are separated by empty lines; all of them are redrawn per step.
    local -i rows=$((1 + 2 * ${#moods[@]})) step shown
    printf '\n'
    kaomoji_animation_begin
    for ((step = 0; ; step++)); do
        shown=${EPOCHREALTIME/./}
        if ((step > 0)); then
            for ((i = 0; i < rows; i++)); do printf '%s' "$KAOMOJI_CUU1"; done
        fi
        printf '%s%-*s' "$dim" "$label" mood
        for title in "${titles[@]}"; do printf ' %-*s' "$cell" "$title"; done
        printf '%s%s\n' "$KAOMOJI_SGR0" "$KAOMOJI_EL"
        for i in "${!moods[@]}"; do
            printf '%s\n' "$KAOMOJI_EL"
            mood=${moods[i]}
            s=$((first_steps[i] + step))
            if ((loops >= 0 && s > last_steps[i])); then s=${last_steps[i]}; fi
            if ((exit)); then exit_flags=(--exit "${exit_steps[i]}"); fi
            printf '%s%-*s%s' "$dim" "$label" "$mood" "$KAOMOJI_SGR0"
            printf ' '
            "${name}_frame" --mood "$mood" --width "$cell"
            printf ' '
            "${name}_frame" --mood "$mood" --width "$cell" --color
            printf ' '
            "${name}_frame" --mood "$mood" --width "$cell" --step "$s" "${flags[@]}" "${exit_flags[@]}"
            printf ' '
            "${name}_frame" --mood "$mood" --width "$cell" --step "$s" --color "${flags[@]}" "${exit_flags[@]}"
            printf '%s\n' "$KAOMOJI_EL"
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
        "${name}_frame" "${mood_flag[@]}" "${color_flag[@]}"
        printf '\n'
    fi
}
