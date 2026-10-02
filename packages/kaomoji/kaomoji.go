// Purpose: The Pi Hero cast, three animated kaomoji for the terminal: kaomoji hero|wizard|visitor.
// Usage:   kaomoji <character> [--mood <mood>] [--color|--no-color]
//
//	kaomoji <character> [--mood <mood>] [--color|--no-color] --animate [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]
//	kaomoji <character> --preview [--mood <mood>] [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]
//	kaomoji <character> --help
//	kaomoji --help | --version
//
// One file, standard library only: `go run kaomoji.go hero` works from a checkout. The terminal is driven
// with ANSI sequences alone. An animation runs on a clock: an entrance slows down into the hover and an exit
// speeds up out of it under constant acceleration, each over the frame times its character gives, so the
// hero crosses a terminal of any width in the same time. Frames are never skipped; a late one goes out at
// once and the schedule moves with it, which keeps the output deterministic for the tests.
//
// Environment: NO_COLOR disables color on a terminal; COLORTERM=truecolor|24bit paints hex colors as
// truecolor, else as their 256-color index, and a TERM without "256color" drops them, fbterm excepted, which
// gets its own form of 256 colors; TERM=dumb is plain;
// KAOMOJI_COLUMNS sets the cells a frame's line has, 0 meaning the character's own width; COLUMNS is the
// terminal's width when stdout is no terminal.
package main

import (
	"fmt"
	"os"
	"os/signal"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

var version = "dev" // set by the build: -ldflags "-X main.version=<version>"

// Terminal control, ECMA-48 and the DEC private modes every terminal of the last twenty years knows.
const (
	civis = "\x1b[?25l" // hide the cursor
	cnorm = "\x1b[?25h" // show the cursor
	el    = "\x1b[K"    // erase to the end of the line
	cuu1  = "\x1b[A"    // cursor up one line
	sc    = "\x1b7"     // save the cursor position
	rc    = "\x1b8"     // restore the cursor position
	sgr0  = "\x1b[0m"   // reset every attribute
	dim   = "\x1b[2m"
)

// A color is one of the terminal's basic sixteen, which follow its theme, or a hex color with the
// 256-color index that stands in for it on a terminal without truecolor.
type color struct {
	kind  int // colorNone, colorBasic or colorHex
	basic int // 0–15
	index int // 256-color index of a hex color
	rgb   uint32
}

const (
	colorNone = iota
	colorBasic
	colorHex
)

func basic(n int) color               { return color{kind: colorBasic, basic: n} }
func hex(rgb uint32, index int) color { return color{kind: colorHex, index: index, rgb: rgb} }

// The depth a terminal paints at: colors16 drops hex colors, colors256 paints them by index, truecolor by
// value; fbterm256 is fbterm's own form of 256 colors, since that framebuffer terminal ignores the standard one.
type depth int

const (
	colors16 depth = iota
	colors256
	truecolor
	fbterm256
)

// sgr returns the SGR sequence setting the color as a foreground (layer 3) or a background (layer 4),
// or "" where the depth lacks it.
func (c color) sgr(layer int, d depth) string {
	if d == fbterm256 && c.kind != colorNone {
		n := c.basic
		if c.kind == colorHex {
			n = c.index
		}
		return fmt.Sprintf("\x1b[%d;%d}", layer-2, n) // ESC[1;N} sets the foreground, ESC[2;N} the background
	}
	switch c.kind {
	case colorBasic:
		if c.basic < 8 {
			return fmt.Sprintf("\x1b[%d%dm", layer, c.basic)
		}
		return fmt.Sprintf("\x1b[%d%dm", layer+6, c.basic-8) // bright: 90–97 and 100–107
	case colorHex:
		switch d {
		case truecolor:
			return fmt.Sprintf("\x1b[%d8;2;%d;%d;%dm", layer, c.rgb>>16&0xff, c.rgb>>8&0xff, c.rgb&0xff)
		case colors256:
			return fmt.Sprintf("\x1b[%d8;5;%dm", layer, c.index)
		}
	}
	return ""
}

// A style is what a grapheme is painted with: dim, or a foreground and a background, either of which may be none.
type style struct {
	dim    bool
	fg, bg color
}

var plain = style{}

// sgr is the sequence painting a style at a depth. A terminal lacking one of a style's colors paints
// neither: the hero's black eyes on a yellow face that is not painted would vanish on a dark theme.
func (s style) sgr(d depth) string {
	fg, bg := s.fg.sgr(3, d), s.bg.sgr(4, d)
	if (s.fg.kind != colorNone && fg == "") || (s.bg.kind != colorNone && bg == "") {
		fg, bg = "", ""
	}
	var b strings.Builder
	if s.dim {
		b.WriteString(dim)
	}
	b.WriteString(fg)
	b.WriteString(bg)
	return b.String()
}

// runeWidth is the cells a character takes: two for the East Asian wide and fullwidth ranges, one for
// everything else, ambiguous characters included, as Western terminals render them.
func runeWidth(r rune) int {
	switch {
	case r >= 0x1100 && r <= 0x115F,
		r >= 0x2E80 && r <= 0xA4CF && r != 0x303F,
		r >= 0xAC00 && r <= 0xD7A3,
		r >= 0xF900 && r <= 0xFAFF,
		r >= 0xFE30 && r <= 0xFE4F,
		r >= 0xFF00 && r <= 0xFF60,
		r >= 0xFFE0 && r <= 0xFFE6,
		r >= 0x20000 && r <= 0x3FFFD:
		return 2
	}
	return 1
}

func textWidth(text string) int {
	width := 0
	for _, r := range text {
		width += runeWidth(r)
	}
	return width
}

// A sprite is a slice of graphemes, each with its text, its cells, and its style.
type grapheme struct {
	text  string
	width int
	style style
}

type sprite []grapheme

func g(text string, s style) grapheme { return grapheme{text: text, width: textWidth(text), style: s} }

func (s sprite) width() int {
	width := 0
	for _, gr := range s {
		width += gr.width
	}
	return width
}

// A painting is a frame's text and the cells it covers.
type painting struct {
	text  string
	width int
}

// paint renders the graphemes of a sprite from the first to the end, excluded, behind pad spaces; a
// clip above zero stops before the cells would exceed it, and the padding goes when nothing is left to
// position. Colored, a style's sequence is written when it changes and the reset at the end.
func paint(s sprite, first, end, pad, clip int, colored bool, d depth) painting {
	if first < 0 {
		first = 0
	}
	if end > len(s) {
		end = len(s)
	}
	if clip > 0 {
		width := pad
		for i := first; ; i++ {
			if i >= end || width+s[i].width > clip {
				end = i
				break
			}
			width += s[i].width
		}
	}
	if first >= end {
		return painting{}
	}
	var b strings.Builder
	b.WriteString(strings.Repeat(" ", pad))
	width := pad
	current := ""
	for _, gr := range s[first:end] {
		if colored {
			if seq := gr.style.sgr(d); seq != current {
				if current != "" {
					b.WriteString(sgr0)
				}
				b.WriteString(seq)
				current = seq
			}
		}
		b.WriteString(gr.text)
		width += gr.width
	}
	if current != "" {
		b.WriteString(sgr0)
	}
	return painting{text: b.String(), width: width}
}

// suffix returns the index of the first grapheme of the longest suffix of a sprite that fits in the cells.
func (s sprite) suffix(cells int) int {
	width := 0
	for i := len(s) - 1; i >= 0; i-- {
		if width+s[i].width > cells {
			return i + 1
		}
		width += s[i].width
	}
	return 0
}

// A timeline is the shape of a character's animation for a mood on a line of some cells.
type timeline struct {
	entrance int // steps of the entrance; the step after them shows the character landed
	cycle    int // steps of one hover cycle, showing every pose the character has
	exit     int // steps of the exit; the last one shows nothing
	exitLen  int // frame times the exit lasts, however many steps it has
}

// A character has moods, a sprite per pose of its hover cycle, a frame for every step, and a timeline.
// A frame's step is -1 for the character at rest; exitStep is the step after which the exit begins, -1
// for none; cols is the line's cells, 0 for the character's own width.
type character struct {
	name     string
	usage    string
	moods    []string
	pose     func(mood string, step int) sprite
	timeline func(mood string, cols int) timeline
	frame    func(mood string, step, exitStep, cols int, colored bool, d depth) painting
}

// The hero: ─=≡▰▩▩[ 蓬•ｏ•]⊐, in the 256-color palette of the Pi Hero logo.

var (
	heroOrange = hex(0xf6b535, 214)
	heroYellow = hex(0xf7dc38, 221)
	heroPink   = hex(0xf80884, 198)
	heroViolet = hex(0x8a4bd8, 93)
	heroBlue   = hex(0x3b4bef, 62)
	heroRed    = hex(0xb1133b, 125)
	heroBrown  = hex(0x974219, 94)
)

// While hovering, the tail cycles through four poses held for three steps each, and the hand
// alternates between two poses held for six steps each.
var (
	heroTailPoses = []string{"-─=", " -─", "-─=", "─=≡"}
	heroHandPoses = []string{"⫎", "⊐"}
)

const (
	heroCycle = 12
	heroRest  = heroCycle - 1 // step of the pose at rest: ─=≡ and ⊐
)

func heroSprite(mood string, tail, hand int) sprite {
	var face []string
	switch mood {
	case "neutral":
		face = []string{" ", "蓬", "•", "ｏ", "•", ""}
	case "happy":
		face = []string{"", "✿", "＾", "ｖ", "＾", ""}
	case "sad":
		face = []string{" ", "༶", "◕", "︿", "◕", " "}
	case "unknown":
		face = []string{"", "༶", "´⊙", "﹏", "⊙`", ""}
	}
	faceFg := []color{basic(0), heroRed, basic(0), heroPink, basic(0), heroRed}
	var s sprite
	for _, r := range heroTailPoses[tail] {
		s = append(s, g(string(r), style{dim: true}))
	}
	s = append(s,
		g("▰", style{fg: heroBrown, bg: heroPink}),
		g("▩", style{fg: heroBlue, bg: heroPink}),
		g("▩", style{fg: heroViolet, bg: heroPink}),
		g("[", style{fg: heroOrange, bg: heroYellow}),
	)
	for i, text := range face {
		if text != "" {
			s = append(s, g(text, style{fg: faceFg[i], bg: heroYellow}))
		}
	}
	return append(s,
		g("]", style{fg: heroOrange, bg: heroYellow}),
		g(heroHandPoses[hand], style{fg: heroYellow}),
	)
}

func heroPose(mood string, step int) sprite {
	return heroSprite(mood, step/3%len(heroTailPoses), step/6%len(heroHandPoses))
}

// The hero's entrance is one cell per step, its exit one cell per step across the whole line, lasting
// as many frame times as the hero is wide however long the line is.
func heroTimeline(mood string, cols int) timeline {
	size := heroPose(mood, heroRest).width()
	line := cols
	if line <= 0 {
		line = size
	}
	return timeline{entrance: size, cycle: heroCycle, exit: line, exitLen: size}
}

// The hero flies in from the left, its right end advancing a cell per step, so that it has fully
// arrived at the step of its width; the poses are phased so that it is at rest then and after every
// hover cycle. On exit it moves right a cell per step, clipped at the line's edge.
func heroFrame(mood string, step, exitStep, cols int, colored bool, d depth) painting {
	if step < 0 {
		s := heroPose(mood, heroRest)
		return paint(s, 0, len(s), 0, 0, colored, d)
	}
	tl := heroTimeline(mood, cols)
	phase := (heroRest - tl.entrance%heroCycle + heroCycle) % heroCycle
	s := heroPose(mood, (step+phase)%heroCycle)
	entered := step
	if exitStep >= 0 && step > exitStep && exitStep < entered {
		entered = exitStep // leaving from where it was
	}
	first, pad, clip := 0, 0, 0
	if entered < tl.entrance {
		first = s.suffix(entered)
		pad = entered - s[first:].width()
	}
	if exitStep >= 0 && step > exitStep {
		pad += step - exitStep
		clip = tl.exit
	}
	return paint(s, first, len(s), pad, clip, colored, d)
}

// The wizard: (つ◕౪◕)つ─｡ﾟ․☆･*ﾟ, in the terminal's own sixteen colors.

var (
	wizardGray  = basic(7)
	wizardWhite = basic(15)
)

// The magic streams out of the wand: while hovering, its colors move outwards by one particle
// every wizardShift steps and are back where they started after one cycle.
var (
	wizardMagic       = []string{"｡", "ﾟ", "․", "☆", "･", "*", "ﾟ"}
	wizardMagicColors = []color{basic(9), basic(14), basic(11), basic(9), basic(11), basic(10), basic(12)}
)

const wizardShift = 3

var wizardCycle = wizardShift * len(wizardMagicColors)

func wizardSprite(mood string, shift int) sprite {
	var face []string
	switch mood {
	case "neutral":
		face = []string{"つ", "◕", "౪", "◕"}
	case "happy":
		face = []string{"＾", "∀", "＾"}
	case "sad":
		face = []string{" ", "◕", "︿", "◕"}
	case "unknown":
		face = []string{" ", "⊙", "﹏", "⊙"}
	}
	s := sprite{g("(", style{fg: wizardGray})}
	for _, text := range face {
		s = append(s, g(text, style{fg: wizardGray}))
	}
	s = append(s, g(")", style{fg: wizardGray}), g("つ", style{fg: wizardWhite}), g("─", style{fg: wizardGray}))
	n := len(wizardMagicColors)
	for i, text := range wizardMagic {
		s = append(s, g(text, style{fg: wizardMagicColors[((i-shift)%n+n)%n]}))
	}
	return s
}

func wizardPose(mood string, step int) sprite {
	return wizardSprite(mood, step/wizardShift%len(wizardMagicColors))
}

func wizardTimeline(mood string, cols int) timeline {
	n := len(wizardPose(mood, 0))
	return timeline{entrance: n, cycle: wizardCycle, exit: n, exitLen: n}
}

// The wizard slides in from the left, one grapheme per step, then conjures the magic one particle per
// step; on exit the magic vanishes from the right and the wizard slides out to the left.
func wizardFrame(mood string, step, exitStep, cols int, colored bool, d depth) painting {
	if step < 0 {
		s := wizardPose(mood, 0)
		return paint(s, 0, len(s), 0, 0, colored, d)
	}
	tl := wizardTimeline(mood, cols)
	magic := len(wizardMagic)
	body := tl.entrance - magic
	offset, shown := 0, magic
	if step <= body {
		offset, shown = body-step, 0
	} else if step < body+magic {
		shown = step - body
	}
	if exitStep >= 0 && step > exitStep {
		gone := step - exitStep
		if gone <= magic {
			shown = magic - gone
		} else {
			shown, offset = 0, gone-magic
		}
	}
	return paint(wizardPose(mood, step), offset, body+shown, 0, 0, colored, d)
}

// The visitor: ┴┬┴┤´Ｏ´)ﾉ, white behind a dim wall.

var (
	visitorWhite = basic(15)
	visitorWall  = []string{"┴", "┬", "┴", "┤"}
	// While hovering, the hand alternates between two poses held for visitorSwing steps each, and the
	// eyes close once per cycle for visitorBlink steps, in the middle of a hold.
	visitorHandPoses = []string{"ﾉ", "ノ"}
)

const (
	visitorSwing   = 6
	visitorCycle   = 36
	visitorBlinkAt = 32
	visitorBlink   = 2
)

func visitorSprite(mood string, hand int, blink bool) sprite {
	var face []string // a gap towards the wall, an eye, the mouth, an eye
	switch mood {
	case "neutral":
		face = []string{"", "´", "Ｏ", "´"}
	case "happy":
		face = []string{" ", "･", "‿", "･"}
	case "sad":
		face = []string{"", "◕", "︿", "◕"}
	case "unknown":
		face = []string{"", "⊙", "﹏", "⊙"}
	}
	if blink {
		face[1], face[3] = "-", "-"
	}
	var s sprite
	for _, text := range visitorWall {
		s = append(s, g(text, style{dim: true}))
	}
	for _, text := range face {
		if text != "" {
			s = append(s, g(text, style{fg: visitorWhite}))
		}
	}
	return append(s, g(")", style{fg: visitorWhite}), g(visitorHandPoses[hand], style{fg: visitorWhite}))
}

func visitorPose(mood string, step int) sprite {
	at := step % visitorCycle
	blink := at >= visitorBlinkAt && at < visitorBlinkAt+visitorBlink
	return visitorSprite(mood, at/visitorSwing%len(visitorHandPoses), blink)
}

func visitorTimeline(mood string, cols int) timeline {
	n := len(visitorPose(mood, 0))
	return timeline{entrance: n, cycle: visitorCycle, exit: n, exitLen: n}
}

// The wall slides in from the left, one grapheme per step, then the person peeks out from behind it,
// one grapheme per step; on exit the person ducks back and the wall slides out. Both show their
// rightmost graphemes, whether coming or going.
func visitorFrame(mood string, step, exitStep, cols int, colored bool, d depth) painting {
	if step < 0 {
		s := visitorPose(mood, 0)
		return paint(s, 0, len(s), 0, 0, colored, d)
	}
	tl := visitorTimeline(mood, cols)
	wall := len(visitorWall)
	person := tl.entrance - wall
	hover := step - tl.entrance
	if hover < 0 {
		hover = 0
	}
	wallShown, personShown := wall, person
	if step <= wall {
		wallShown, personShown = step, 0
	} else if step < tl.entrance {
		personShown = step - wall
	}
	if exitStep >= 0 && step > exitStep {
		gone := step - exitStep
		if gone <= person {
			personShown = person - gone
		} else {
			personShown = 0
			wallShown = wall - (gone - person)
			if wallShown < 0 {
				wallShown = 0
			}
		}
	}
	s := visitorPose(mood, hover)
	if wallShown == wall && personShown == person {
		return paint(s, 0, len(s), 0, 0, colored, d)
	}
	a := paint(s, wall-wallShown, wall, 0, 0, colored, d)
	b := paint(s, wall+person-personShown, len(s), 0, 0, colored, d)
	return painting{text: a.text + b.text, width: a.width + b.width}
}

// Options of a run: what the command line and the environment decided.
type options struct {
	mood     string
	colored  bool
	depth    depth
	entrance bool
	loops    int // -1 for endless
	exit     bool
	frameMs  int
	cols     int // cells of a frame's line, 0 for the character's own width
}

// stepFrame renders the frame of a step: hover steps map onto the first cycle, and the exit is passed
// on only once it has begun.
func stepFrame(ch *character, o options, tl timeline, step, exitStep int) painting {
	if exitStep >= 0 && step > exitStep {
		return ch.frame(o.mood, step, exitStep, o.cols, o.colored, o.depth)
	}
	if step > tl.entrance {
		step = tl.entrance + 1 + (step-tl.entrance-1)%tl.cycle
	}
	return ch.frame(o.mood, step, -1, o.cols, o.colored, o.depth)
}

// How unevenly an entrance or an exit spreads its duration over its steps, in percent: the fastest
// step stays this much less than the mean step time and the slowest this much more, the steps
// between them changing evenly, as under constant acceleration.
const easing = 75

// frameTime is how long the frame of a step stays. A hover frame stays a frame time. The frames of the
// entrance share as many frame times as the entrance has steps, the first staying shortest and the last
// longest, so that the character slows down into the hover; the frames of the exit share its duration
// the other way round, so that it speeds up out of it.
func frameTime(step, entrance, exitStep, exitSteps int, frame, exitDur time.Duration) time.Duration {
	var i, n int
	var total time.Duration
	var sign int64
	switch {
	case exitStep >= 0 && step >= exitStep:
		i, n, total, sign = step-exitStep, exitSteps, exitDur, 1
	case step < entrance:
		i, n, total, sign = step, entrance, time.Duration(entrance)*frame, -1
	default:
		return frame
	}
	if n < 2 {
		return total
	}
	t := int64(total)
	return time.Duration(t/int64(n) + sign*t*easing*int64(n-1-2*i)/(100*int64(n)*int64(n-1)))
}

// sleepUntil waits for the time to come or a signal to arrive, and reports the signal. A time that has
// passed still takes a pending signal, so a frame rate of zero stays interruptible.
func sleepUntil(t time.Time, sig <-chan os.Signal) bool {
	d := time.Until(t)
	if d <= 0 {
		select {
		case <-sig:
			return true
		default:
			return false
		}
	}
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-sig:
		return true
	case <-timer.C:
		return false
	}
}

// write puts text on the terminal in one call; the runtime finishes a write a signal interrupted.
func write(text string) {
	if _, err := os.Stdout.WriteString(text); err != nil {
		fmt.Fprintf(os.Stderr, "kaomoji: write error: %v\n", err)
		os.Exit(1)
	}
}

// quit leaves the cursor on a fresh line and visible, the way a stopped animation ends.
func quit() int {
	write("\n" + cnorm)
	return 130
}

func notify() chan os.Signal {
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	return sig
}

// animate plays a single kaomoji on the current line and ends it with a newline. The next frame is due
// when the current one has stayed its time, counted from when the current one was due, so that a late
// frame is caught up on; one later than its whole time is not.
func animate(ch *character, o options) int {
	tl := ch.timeline(o.mood, o.cols)
	frame := time.Duration(o.frameMs) * time.Millisecond
	exitDur := time.Duration(tl.exitLen) * frame
	first, last, exitStep := 0, -1, -1
	if !o.entrance {
		first = tl.entrance + 1 // the first hover step
	}
	if o.loops >= 0 {
		last = tl.entrance + o.loops*tl.cycle
		if o.exit {
			exitStep = last
			last += tl.exit
		}
	}
	leaving := o.exit && o.loops < 0 // endless: the first signal plays the exit, the second quits
	sig := notify()
	write(civis)
	text := stepFrame(ch, o, tl, first, exitStep).text
	due := time.Now()
	for step := first; ; step++ {
		shown := time.Now()
		write("\r" + text + el)
		if last >= 0 && step >= last {
			break
		}
		ft := frameTime(step, tl.entrance, exitStep, tl.exit, frame, exitDur)
		due = due.Add(ft)
		if due.Before(shown) {
			due = shown.Add(ft)
		}
		text = stepFrame(ch, o, tl, step+1, exitStep).text
		if sleepUntil(due, sig) {
			if !leaving {
				return quit()
			}
			leaving = false // leave from the current step, at once
			exitStep = step
			last = step + tl.exit
			text = stepFrame(ch, o, tl, step+1, exitStep).text
			due = time.Now()
		}
	}
	write("\n" + cnorm)
	return 0
}

// grid prints every variant: a header, one row per mood, four columns, static and animated, each
// plain and colored; the animated columns play in place, paced by the first mood's timeline.
func grid(ch *character, o options, moods []string) int {
	titles := []string{"static plain", "static color", "animated plain", "animated color"}
	// The label column fits every mood, a cell fits its title and every frame of a hover cycle.
	label, cell := 4, 0
	for _, title := range titles {
		if len(title) > cell {
			cell = len(title)
		}
	}
	for _, mood := range moods {
		if len(mood) > label {
			label = len(mood)
		}
		tl := ch.timeline(mood, 0)
		for s := tl.entrance; s <= tl.entrance+tl.cycle; s++ {
			if w := ch.frame(mood, s, -1, 0, false, o.depth).width; w > cell {
				cell = w
			}
		}
	}
	// An animated cell is a line of its own, which an exit crosses; each mood's animation runs from
	// its own first to its own last step.
	o.cols = cell
	frame := time.Duration(o.frameMs) * time.Millisecond
	var firsts, exits, lasts []int
	var timelines []timeline
	last := 0
	for _, mood := range moods {
		tl := ch.timeline(mood, cell)
		first, exitStep := 0, -1
		if !o.entrance {
			first = tl.entrance + 1
		}
		if o.exit && o.loops >= 0 {
			exitStep = tl.entrance + o.loops*tl.cycle
		}
		end := tl.entrance + o.loops*tl.cycle
		if o.exit {
			end += tl.exit
		}
		if end-first > last {
			last = end - first
		}
		timelines, firsts, exits, lasts = append(timelines, tl), append(firsts, first), append(exits, exitStep), append(lasts, end)
	}
	exitDur := time.Duration(timelines[0].exitLen) * frame

	// The header and the rows are separated by empty lines; all of them are redrawn per step, each line
	// in one write. The cursor is saved below the grid once it exists: a redraw returns there first, and so
	// does a signal, which quits between redraws, not in the middle of one.
	rows := 1 + 2*len(moods)
	up := strings.Repeat(cuu1, rows)
	sig := notify()
	write("\n" + civis)
	due := time.Now()
	for step := 0; ; step++ {
		shown := time.Now()
		var b strings.Builder
		if step > 0 {
			b.WriteString(rc + up)
		}
		fmt.Fprintf(&b, "\r%s%-*s", dim, label, "mood")
		for _, title := range titles {
			fmt.Fprintf(&b, " %-*s", cell, title)
		}
		b.WriteString(sgr0 + el + "\n")
		for i, mood := range moods {
			o := o
			o.mood = mood
			s := firsts[i] + step
			if o.loops >= 0 && s > lasts[i] {
				s = lasts[i]
			}
			fmt.Fprintf(&b, "\r%s\n\r%s%-*s%s", el, dim, label, mood, sgr0)
			for _, p := range []painting{
				ch.frame(mood, -1, -1, cell, false, o.depth),
				ch.frame(mood, -1, -1, cell, true, o.depth),
				stepFrame(ch, plainOptions(o), timelines[i], s, exits[i]),
				stepFrame(ch, coloredOptions(o), timelines[i], s, exits[i]),
			} {
				fmt.Fprintf(&b, " %s%*s", p.text, cell-p.width, "")
			}
			b.WriteString(el + "\n")
		}
		if step == 0 {
			b.WriteString(sc)
		}
		write(b.String())
		if o.loops >= 0 && step >= last {
			break
		}
		ft := frameTime(firsts[0]+step, timelines[0].entrance, exits[0], timelines[0].exit, frame, exitDur)
		due = due.Add(ft)
		if due.Before(shown) {
			due = shown.Add(ft)
		}
		if sleepUntil(due, sig) {
			write(rc)
			return quit()
		}
	}
	write("\n" + cnorm)
	return 0
}

func plainOptions(o options) options   { o.colored = false; return o }
func coloredOptions(o options) options { o.colored = true; return o }

// lineColumns is the cells a frame's line has: KAOMOJI_COLUMNS if the environment says, else the
// terminal's width less the last column, which some terminals wrap on.
func lineColumns() int {
	if v := os.Getenv("KAOMOJI_COLUMNS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			return n
		}
	}
	return terminalColumns() - 1
}

// terminalColumns is the terminal's width: what stdout reports, else COLUMNS, else 80.
func terminalColumns() int {
	var ws struct{ rows, cols, x, y uint16 }
	_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, os.Stdout.Fd(), uintptr(syscall.TIOCGWINSZ), uintptr(unsafe.Pointer(&ws)))
	if errno == 0 && ws.cols > 0 {
		return int(ws.cols)
	}
	if n, err := strconv.Atoi(os.Getenv("COLUMNS")); err == nil && n > 0 {
		return n
	}
	return 80
}

func isTerminal(f *os.File) bool {
	info, err := f.Stat()
	return err == nil && info.Mode()&os.ModeCharDevice != 0
}

// terminalDepth reads the environment: fbterm's own 256 colors on fbterm, truecolor when COLORTERM says so,
// 256 colors when TERM does, else the basic sixteen.
func terminalDepth() depth {
	if os.Getenv("TERM") == "fbterm" {
		return fbterm256
	}
	switch os.Getenv("COLORTERM") {
	case "truecolor", "24bit":
		return truecolor
	}
	if term := os.Getenv("TERM"); strings.Contains(term, "256color") || strings.Contains(term, "direct") {
		return colors256
	}
	return colors16
}

const mainUsage = `Usage: kaomoji <character> [--mood <mood>] [--color|--no-color] [--animate] [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]
       kaomoji <character> --preview [--mood <mood>] [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]
       kaomoji <character> --help
       kaomoji --help | --version

The Pi Hero cast: hero, wizard, and visitor. Each prints one kaomoji, static unless animated, plain
or colored, in every mood it has; 'kaomoji <character> --help' lists its moods and options.

Examples:
  kaomoji hero                            ─=≡▰▩▩[ 蓬•ｏ•]⊐
  kaomoji wizard --mood happy             (＾∀＾)つ─｡ﾟ․☆･*ﾟ
  kaomoji visitor --animate --exit        peeks out, waves until Ctrl-C, ducks back
`

// The options every character shares, with the character's name filled in.
const sharedOptions = `
Options:
  --mood <mood>     One of %s (default: %s).
  --animate         Play the animation (default: static). Implied by the options below.
  --no-entrance     Skip the entrance and start hovering right away.
  --loops <n>       Stop after <n> hover cycles (default: endless, until stopped with Ctrl-C).
  --exit            Play the exit after the last hover cycle, or when an endless animation is stopped with
                    Ctrl-C or SIGTERM; a second Ctrl-C quits at once.
  --frame-ms <ms>   Delay between animation frames (default: 50).
  --color           Colored output (default: if stdout is a terminal and NO_COLOR is unset).
  --no-color        Plain output.
  --preview         Show all variants in a grid, animated, instead of one kaomoji.
  -h, --help        Show this help.
`

const heroUsage = `Purpose: Render the Pi Hero kaomoji ─=≡▰▩▩[ 蓬•ｏ•]⊐ in all moods, plain or colored, static or animated.
Usage:   kaomoji hero [--mood <mood>] [--color|--no-color]
         kaomoji hero [--mood <mood>] [--color|--no-color] --animate [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]
         kaomoji hero --preview [--mood <mood>] [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]

Prints one kaomoji, static unless animated. --preview shows all variants instead: a grid with one
row per mood and one column per style. Colors need a 256-color terminal.

The hero flies in from the left and hovers, tail flickering and hand flexing; on exit it flies
out through the right edge of the terminal, in the same time however wide the terminal is.
%s
Examples:
  kaomoji hero
  ─=≡▰▩▩[ 蓬•ｏ•]⊐
  kaomoji hero --mood happy
  ─=≡▰▩▩[✿＾ｖ＾]⊐
  kaomoji hero --animate                        # entrance, then hovering until Ctrl-C
  kaomoji hero --animate --exit                 # ... leaving on Ctrl-C
  kaomoji hero --mood sad --loops 3 --exit      # entrance, three hover cycles, exit
  kaomoji hero --no-entrance                    # hovering right away, until Ctrl-C
  kaomoji hero --no-color > motd                # plain text for a file
  kaomoji hero --preview                        # grid of all variants, animated until Ctrl-C
  kaomoji hero --preview --loops 2 --exit       # grid, hovering twice, then leaving
`

const wizardUsage = `Purpose: Render the Netmon wizard kaomoji (つ◕౪◕)つ─｡ﾟ․☆･*ﾟ in all moods, plain or colored, static or animated.
Usage:   kaomoji wizard [--mood <mood>] [--color|--no-color]
         kaomoji wizard [--mood <mood>] [--color|--no-color] --animate [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]
         kaomoji wizard --preview [--mood <mood>] [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]

Prints one kaomoji, static unless animated. --preview shows all variants instead: a grid with one
row per mood and one column per style. Colors need a 16-color terminal.

The wizard slides in from the left and conjures the magic particle by particle; while hovering,
the colors run along the particles. On exit the particles vanish from the right and the wizard
slides out to the left.
%s
Examples:
  kaomoji wizard
  (つ◕౪◕)つ─｡ﾟ․☆･*ﾟ
  kaomoji wizard --mood happy --animate --exit  # entrance, hovering until Ctrl-C, exit
  kaomoji wizard --loops 3 --exit               # entrance, three hover cycles, exit
`

const visitorUsage = `Purpose: Render the Busy Screen visitor kaomoji ┴┬┴┤´Ｏ´)ﾉ in all moods, plain or colored, static or animated.
Usage:   kaomoji visitor [--mood <mood>] [--color|--no-color]
         kaomoji visitor [--mood <mood>] [--color|--no-color] --animate [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]
         kaomoji visitor --preview [--mood <mood>] [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]

Prints one kaomoji, static unless animated. --preview shows all variants instead: a grid with one
row per mood and one column per style. Colors need a 16-color terminal.

The wall slides in from the left and the visitor peeks out from behind it; while hovering,
they wave and blink. On exit they duck back behind the wall, which then slides out to the left.
%s
Examples:
  kaomoji visitor
  ┴┬┴┤´Ｏ´)ﾉ
  kaomoji visitor --mood happy --animate --exit  # entrance, hovering until Ctrl-C, exit
  kaomoji visitor --loops 3 --exit               # entrance, three hover cycles, exit
`

var characters = map[string]*character{
	"hero":    {name: "hero", usage: heroUsage, moods: []string{"neutral", "happy", "sad", "unknown"}, pose: heroPose, timeline: heroTimeline, frame: heroFrame},
	"wizard":  {name: "wizard", usage: wizardUsage, moods: []string{"neutral", "happy", "sad", "unknown"}, pose: wizardPose, timeline: wizardTimeline, frame: wizardFrame},
	"visitor": {name: "visitor", usage: visitorUsage, moods: []string{"neutral", "happy", "sad", "unknown"}, pose: visitorPose, timeline: visitorTimeline, frame: visitorFrame},
}

// die prints the message and where to find help, and returns the status for the command line.
func die(ch *character, format string, args ...any) int {
	help := "kaomoji --help"
	if ch != nil {
		help = "kaomoji " + ch.name + " --help"
	}
	fmt.Fprintf(os.Stderr, "kaomoji: %s\nSee '%s'\n", fmt.Sprintf(format, args...), help)
	return 2
}

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	if len(args) == 0 {
		return die(nil, "character missing")
	}
	switch args[0] {
	case "-h", "--help":
		fmt.Print(mainUsage)
		return 0
	case "--version":
		fmt.Println(version)
		return 0
	}
	ch := characters[args[0]]
	if ch == nil {
		if strings.HasPrefix(args[0], "-") {
			return die(nil, "unknown option: %s", args[0])
		}
		return die(nil, "unknown character: %s", args[0])
	}
	return ch.run(args[1:])
}

// run is the command line of a character: every call prints one kaomoji, static unless animated;
// only --help and --preview print something else.
func (ch *character) run(args []string) int {
	o := options{mood: ch.moods[0], entrance: true, loops: -1, frameMs: 50, depth: terminalDepth()}
	animated, preview, color := false, false, ""
	value := func(i *int) (string, bool) { // the value of the option at i, inline or next
		if at := strings.IndexByte(args[*i], '='); at >= 0 {
			return args[*i][at+1:], true
		}
		if *i+1 < len(args) {
			*i++
			return args[*i], true
		}
		return "", false
	}
	number := func(i *int, option string, into *int) int {
		v, ok := value(i)
		if !ok {
			return die(ch, "%s: missing value", option)
		}
		n, err := strconv.Atoi(v)
		if err != nil || n < 0 {
			return die(ch, "%s: not a number: %s", option, v)
		}
		*into = n
		return 0
	}
	for i := 0; i < len(args); i++ {
		arg := args[i]
		name := arg
		if at := strings.IndexByte(arg, '='); at >= 0 {
			name = arg[:at]
		}
		switch name {
		case "-h", "--help", "--preview", "--animate", "--no-entrance", "--exit", "--color", "--no-color":
			if name != arg {
				return die(ch, "%s: takes no value", name)
			}
		}
		switch name {
		case "-h", "--help":
			moods := strings.Join(ch.moods, ", ")
			fmt.Printf(ch.usage, fmt.Sprintf(sharedOptions, moods, ch.moods[0]))
			return 0
		case "--mood":
			v, ok := value(&i)
			if !ok {
				return die(ch, "--mood: missing value")
			}
			o.mood = v
		case "--preview":
			preview = true
		case "--animate":
			animated = true
		case "--no-entrance":
			animated, o.entrance = true, false
		case "--exit":
			animated, o.exit = true, true
		case "--color":
			color = "yes"
		case "--no-color":
			color = "no"
		case "--loops":
			animated = true
			if status := number(&i, "--loops", &o.loops); status != 0 {
				return status
			}
		case "--frame-ms":
			animated = true
			if status := number(&i, "--frame-ms", &o.frameMs); status != 0 {
				return status
			}
		default:
			if strings.HasPrefix(arg, "-") {
				return die(ch, "unknown option: %s", arg)
			}
			return die(ch, "unexpected argument: %s", arg)
		}
	}
	known := sort.SearchStrings(sortedMoods(ch), o.mood)
	if known >= len(ch.moods) || sortedMoods(ch)[known] != o.mood {
		return die(ch, "unknown mood: %s", o.mood)
	}
	if preview {
		moods := ch.moods
		if o.mood != ch.moods[0] || moodGiven(args) {
			moods = []string{o.mood}
		}
		return grid(ch, o, moods)
	}
	switch color {
	case "yes":
		o.colored = true
	case "no":
		o.colored = false
	default:
		o.colored = isTerminal(os.Stdout) && os.Getenv("NO_COLOR") == "" && os.Getenv("TERM") != "dumb"
	}
	if animated {
		o.cols = lineColumns()
		return animate(ch, o)
	}
	write(ch.frame(o.mood, -1, -1, 0, o.colored, o.depth).text + "\n")
	return 0
}

func sortedMoods(ch *character) []string {
	moods := append([]string(nil), ch.moods...)
	sort.Strings(moods)
	return moods
}

func moodGiven(args []string) bool {
	for _, arg := range args {
		if arg == "--mood" || strings.HasPrefix(arg, "--mood=") {
			return true
		}
	}
	return false
}
