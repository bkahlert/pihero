# `kaomoji` in Go: one file, one binary, one curl line

Date: 2026-10-02. Status: approved design, ready for planning.

## Intent

The cast in [packages/kaomoji](../../../packages/kaomoji) is three bash scripts on a shared engine,
[kaomoji.bash](../../../packages/kaomoji/kaomoji.bash), which a face sources next to itself or from `/usr/lib/kaomoji/`.
It works, and on a Raspberry Pi 1 it is as fast as bash gets: the first frame shows after 0.8 to 1.2 s, a cached frame
costs 9 ms, and the colored warm-up spends most of its 1.1 to 1.9 s in `tput`. It needs bash 5, which a stock Mac does not
have, and ncurses; a face cannot be copied anywhere on its own; and the engine's step-based pacing meets its floor on
wide terminals and slow boards.

This rewrites the cast as one Go program in one source file, with no dependency beyond the standard library, built into
one static binary per platform: `kaomoji hero`, `kaomoji wizard`, `kaomoji visitor`. Animations run on a clock, eased in
time, so an exit lasts the same on every width and the frame rate follows the distance. A bootstrap script published with
every release makes `curl -fsSL https://github.com/bkahlert/pihero/releases/latest/download/hero | bash -s -- --animate`
render the hero on any Linux or macOS machine with curl, nothing installed.

Success looks like this: `go run kaomoji.go hero` works from a bare checkout; the Debian package installs on arm64,
armhf, and amd64 and `pihero`'s MOTD shows its banner through `kaomoji hero`; the first frame on a Pi 1 shows within tens
of milliseconds and the hero's exit lasts 0.8 s on an 80-column and on a 200-column terminal; the curl line above plays
the hero on a Mac and on a Pi; and tiers 0 and 1 prove all of it.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Language | Go, standard library only | A compiled binary starts in milliseconds and paces frames in microseconds, where bash takes a second and Python a third of one; a static binary needs no bash, Python, or ncurses on the target. Go cross-compiles for every target from any host with one command and no extra toolchain; Rust reaches the Pi 1's ARMv6 only through `cross` or zig, slower builds, and a manifest and lock beside the source, and its smaller binary buys nothing for a one-line animation |
| One file | `kaomoji.go`, no `go.mod` | The file is the artifact in source form too: `go run kaomoji.go hero` from a checkout. The standard library's `syscall` has the window-size ioctl on Linux and macOS, so one file compiles for both without build tags |
| Platforms | Linux and macOS, arm64 and amd64, plus Linux ARMv6 for the Pi 1 | Windows natively would need `golang.org/x/term`, hence `go.mod` and `go.sum`, two more binaries per release, and a bootstrap that cannot run there without WSL, where the Linux binary already works |
| Binaries | One, `kaomoji`, with the character as the first argument | Three binaries triple the release assets and the installed size for what a name would give; `hero`, `wizard`, and `visitor` on `PATH` are generic names that invite conflicts on any device the package lands on. Breaking: callers of `hero` run `kaomoji hero` |
| Terminal control | Hardcoded ANSI sequences, no tput and no terminfo | ECMA-48 is what every terminal of the last twenty years speaks, including asciinema's; terminfo cost three forks and most of the colored warm-up |
| Colors | A style is a basic color 0–15 or a hex color; hex paints as truecolor when `COLORTERM` is `truecolor` or `24bit`, else as its listed 256-color index | The hero's palette is defined in hex today and its 256 indices are what the tests see; the wizard and the visitor use the terminal's own sixteen and keep following its theme |
| Pacing | A clock: a phase is N frames over a duration D, frame i due at the time the eased progress reaches i/N | The frame count follows the distance and the duration does not, so an exit over 200 cells plays 200 frames in the 0.8 s a 40-cell one plays 40; the easing keeps today's shape, constant acceleration with the fastest interval a quarter of the mean and the slowest one and three quarters |
| Behind schedule | Frames are never skipped; a late frame goes out at once and the schedule moves with it | Deterministic output, which the tests count frame by frame with `--frame-ms 0`; on a terminal that cannot keep up the motion stretches rather than stutters |
| Build | A `build` script in the package, run by the testkit in the tools image, which gains Debian's Go | One place for every Linux-side tool; the Mac keeps needing only podman, qemu, and uv. The cog mechanism, an own image per package, stays as it is |
| Package | `kaomoji_<version>_{armhf,arm64,amd64}.deb`, `/usr/bin/kaomoji`, no dependencies | One manifest with the architecture substituted; the ARMv6 binary runs on every 32-bit Pi and ships as armhf, the architecture Raspberry Pi OS 32-bit reports |
| Bootstrap | A POSIX sh script published as a release asset under four names, with version, character, and the binaries' hashes baked in | `releases/latest/download/<name>` pairs a script with the binaries of its own release without an API call, a redirect service, or hosting; the cache path is known without a round trip; the hash check makes the redirect's target irrelevant |
| GIF renderer | Stays a bash script beside the cast, now self-contained | Mac-side, needs asciinema and agg, and records any command; it inlines the few helpers it sourced |

## The program

### Command line

```
kaomoji <character> [--mood <mood>] [--color|--no-color]
kaomoji <character> [--mood <mood>] [--color|--no-color] --animate [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]
kaomoji <character> --preview [--mood <mood>] [--no-entrance] [--loops <n>] [--exit] [--frame-ms <ms>]
kaomoji <character> --help
kaomoji --help | --version
```

`<character>` is `hero`, `wizard`, or `visitor`. Every option keeps the meaning it has in the scripts today, see
[hero](../../../packages/kaomoji/hero). `kaomoji` alone, an unknown character, or an unknown option print the usage hint
to stderr and exit 2, as `die` does today. `--version` prints the version linked into the binary. The environment is read
as today: `NO_COLOR`, `TERM`, `COLUMNS`, and `KAOMOJI_COLUMNS`, where `0` makes a character leave through its own edge,
which the GIF renderer sets to keep its pictures minimal.

### Terminal

Output is one write per frame: carriage return, the frame, erase to the end of the line; the grid redraws with cursor up.
The cursor is hidden for an animation and shown again on every way out, a signal included. Color is on when stdout is a
terminal, `NO_COLOR` is unset, and `TERM` is not `dumb`, or when `--color` says so. The width of a frame's line is
`KAOMOJI_COLUMNS` if set; otherwise the terminal's width less one, since some terminals wrap on the last column, the
width being the TIOCGWINSZ ioctl on stdout, else `COLUMNS`, else 80. Signals keep today's contract: with `--exit`, the first SIGINT or SIGTERM during an endless
animation plays the exit and the second quits at once; without it, the first quits. Go retries a write a signal
interrupted, so the frame-restart logic of the bash engine has no counterpart.

### Sprites and painting

A sprite is a slice of graphemes, each with its text, its style, and its width in cells, one or two, from a table of the
East Asian wide ranges the engine has today. Painting a sprite at an offset and with a clip is a loop over graphemes
that emits a style's SGR sequence when it changes and the reset at the end; a grapheme straddling an edge is dropped, so a
wide glyph appears when it fits. Every pose a character has is built once before the first frame.

### Animation

An animation is a list of phases: the entrance, hover cycles, the exit. A phase has a frame count N, a duration D in
multiples of the frame time, an easing, and a function from the frame index to the frame. The hover shows one frame per
frame time, N being the cycle; the entrance decelerates and the exit accelerates. Frame i of a phase is due when the
eased progress reaches i/N, so the entrance's first frames come quick and its last ones slow, and the exit the other way
round. The engine renders a frame when it is due, writes it only if it differs from the one shown, and sleeps until the
next; the hover's frames repeat every cycle and are kept once rendered. `--frame-ms 0` makes every duration zero and the
output the full sequence of frames, which is what the tests read.

The choreographies stay: the hero flies in from the left, hovers with a flickering tail and a flexing hand, and flies out
through the terminal's right edge in sixteen frame times however wide it is; the wizard slides in, conjures the magic
particle by particle, runs the colors along it, and slides out to the left; the visitor peeks out from behind a wall
that slides in, waves and blinks, ducks back, and the wall slides out. One change: the hero enters cell by cell rather
than grapheme by grapheme, as it exits.

### Grid

`--preview` is the grid of today: a header, one row per mood, four columns, static and animated, each plain and colored,
redrawn in place with cursor up, every column at the cell width, and the animations paced as one.

## Package anatomy

```
packages/kaomoji/
  kaomoji.go          # the program: engine and the three characters; the only file that ships in the deb
  build               # cross-compiles, packs the debs, renders the bootstrap scripts; runs in the tools image
  nfpm.yaml.in        # the manifest with ${ARCH}; not nfpm.yaml, so the testkit does not build it as arch all
  bootstrap.sh        # the curl-line script, with @VERSION@, @CHARACTER@, and the hashes to fill in
  kaomoji-gif  Makefile  assets/  README.md   # Mac-side, not shipped
  tests/              # tier 0: conftest.py, test_hero.py, test_wizard.py, test_visitor.py, test_kaomoji.py,
                      #         test_bootstrap.py, test_kaomoji_gif.py; test_installed.py for tiers 1, 2, and ssh
  .build/kaomoji      # the Mac binary the tests and the GIF Makefile use, gitignored
```

Removed: `kaomoji.bash`, `hero`, `wizard`, `visitor`, `nfpm.yaml`.

## Build

`build --dist <dir> --version <version>` runs in the tools image with the repository at `/work`. It builds
`kaomoji-linux-armv6` (GOARM=6), `kaomoji-linux-arm64`, `kaomoji-linux-amd64`, `kaomoji-darwin-arm64`, and
`kaomoji-darwin-amd64` into `<dir>` with `CGO_ENABLED=0`, `-trimpath`, and `-ldflags "-s -w -X main.version=<version>"`,
then runs nfpm three times on `nfpm.yaml.in` with `ARCH` set, each with the matching Linux binary as
`/usr/bin/kaomoji`, and prints the three deb paths on stdout, nothing else. It then renders
[bootstrap.sh](#bootstrap) as `<dir>/kaomoji`, `<dir>/hero`, `<dir>/wizard`, and `<dir>/visitor`. The tools image gains
Debian trixie's `golang-go`, whose version the image's digest pins; the program uses no language feature beyond that
Go's.

The tests and the GIF Makefile need the Mac binary. The testkit's tools module gains a command-line form that runs a
command in the tools image, and both call it to build `.build/kaomoji` for the host's OS and architecture when
`kaomoji.go` is newer than the binary, a few seconds.

## Bootstrap

The script is POSIX sh, shellchecked, and everything is inside one function called on its last line, so a download cut
short runs nothing. Rendered, it knows its version, its character, empty for `kaomoji`, and the sha256 of each binary.
It maps `uname -s` and `uname -m` to an asset name: Linux or Darwin; `x86_64` to amd64, `aarch64` or `arm64` to arm64,
`armv6l` or `armv7l` to armv6; anything else is a one-line message and exit 1. A 32-bit Raspberry Pi OS on a 64-bit
kernel reports `aarch64` and gets the arm64 binary, which runs there, being static. If
`${XDG_CACHE_HOME:-$HOME/.cache}/kaomoji/<version>/kaomoji` is missing, it fetches
`https://github.com/bkahlert/pihero/releases/download/<tag>/kaomoji-<os>-<arch>` with `curl -fsSL` into a temporary
file next to it, checks the hash with `sha256sum` or `shasum -a 256`, whichever exists, makes it executable, and moves
it into place. The tag is `v` and the version with `~` as `-`, so `2.1.0~rc.1` fetches from `v2.1.0-rc.1`; a build
between tags has no release and its script no working URL, which is accepted. Then it execs the binary with its character, if it has one, and the arguments after `--`. Standard input
is the script's own pipe, which the binary never reads.

## Release

[release.yml](../../../.github/workflows/release.yml) attaches `dist/*.deb`, the five binaries, and the four scripts to
the GitHub release, so the curl line works from the first tag after this change on. The APT repository takes the debs as
before, now three for `kaomoji`.

## Harness

- [build.py](../../../testkit/src/pihero_testkit/build.py): a package directory is one with an `nfpm.yaml`, a `build`
  next to a `Containerfile`, or a `build` alone. The third runs in the tools image with `--dist` and `--version`, every
  time; the first two keep their paths and the reuse shortcut of self-versioned packages.
- The tools [Containerfile](../../../testkit/src/pihero_testkit/tools/Containerfile) installs `golang-go`.
- [tools.py](../../../testkit/src/pihero_testkit/tools.py): the command-line form.
- [test_static.py](../../../testkit/tests/test_static.py): `gofmt -l` and `go vet` over every `*.go` under `packages/`,
  through the tools image like shellcheck. The manifest sweep iterates `nfpm.yaml` files and leaves `kaomoji` alone; the
  Go file is no shell file.
- Tier 1 already installs the debs built for the container's architecture, so the arm64 and arm/v7 runs install theirs
  and `pihero`'s dependency resolves. The VM installs by name from the flat repository, where the arm64 deb is.

## Tests

Tier 0, kaomoji, the suite of today adapted to `kaomoji <character>` through a fixture that builds `.build/kaomoji`
once per session:

- Static output per mood for every character; the frame sequences of entrance, hover, and exit; the hero's exit through
  the terminal's edge, one cell per frame, gone after as many frames as the line is wide; the exit's duration at 40 and
  120 columns; `--no-entrance`; the grid. The hero's entrance assertions follow the per-cell entrance.
- Colors: the hero's 256-color sequences on `xterm-256color`, its truecolor sequences under `COLORTERM=truecolor`, the
  wizard's basic ones; `--no-color`, `NO_COLOR`, and `TERM=dumb`.
- Signals, as today: a stopped endless animation plays the exit, a second signal quits at once, a blocked write still
  leaves a whole frame.
- `--version`, the usage hint and exit code for no character and for an unknown one.
- Gone: the tests of the bash engine's internals, frame time arithmetic, sleep doubles, tput batching, the fake tput.

Tier 0, `test_bootstrap.py`: the rendered `hero` script, with a fake `curl` that copies from a directory standing in for
the release and a fake `uname`, fetches `kaomoji-linux-arm64` for `Linux aarch64` and `kaomoji-darwin-arm64` for
`Darwin arm64`, caches under a temporary `XDG_CACHE_HOME` and does not fetch twice, refuses a binary whose hash is wrong,
exits 1 for `Linux mips`, and execs the binary with `hero` and the arguments, which a fake binary records.

Tier 0, testkit: the build module routes a `build` without a Containerfile to the tools image with `--version`, and
`tools`'s command-line form runs a command there.

Tier 0, pihero: the MOTD stubs `kaomoji` and asserts `hero --mood <mood> --no-color` as its arguments.

Tiers 1, 2, and ssh, `test_installed.py`: `kaomoji` is installed at the built version for the container's architecture,
`/usr/bin/kaomoji` is `0755` root, `kaomoji hero --mood happy --no-color` prints the happy hero and
the other two their first mood, `kaomoji --version` prints the version, purge leaves nothing behind; `pihero`'s MOTD
test keeps asserting the face that matches the state.

## Documentation

- [design.md](../../design.md): the `kaomoji` section rewritten for the binary, the clock, the colors, the bootstrap, and
  the build; the Performance paragraph replaced by measurements of the binary on `busy-screen.local`, a Pi 1, taken
  during implementation; the Decisions table's "Cast package" row amended and a row for the language added, as the
  exception to "On-device logic"; the layout block, the "Paths" and "Manifest" bullets updated.
- [testing.md](../../testing.md): the tools image's Go, the tier-0 build of the Mac binary, the third package kind.
- [README.md](../../../README.md) and [packages/kaomoji/README.md](../../../packages/kaomoji/README.md): the curl line,
  `kaomoji hero`, `go run kaomoji.go hero`, the GIF workflow.
- [app-conventions.md](../../app-conventions.md): an app that shows a face runs `kaomoji hero`, `kaomoji wizard`, or
  `kaomoji visitor`.
- The implementing commit carries `BREAKING CHANGE: hero, wizard, and visitor are kaomoji hero, kaomoji wizard, and
  kaomoji visitor`.

## Follow-up in choam.de

Handed over, not done here: shishakli's `/usr/local/lib/hero-lcd/run`, if it runs `/usr/bin/hero` by now, runs
`/usr/bin/kaomoji hero --mood neutral --animate --color` instead.

## Out of scope

- Windows natively, a short domain in front of the release URL, a Homebrew formula.
- Reacting to a terminal resize during an animation.
- New choreographies or poses; the look stays, the motion gets smoother.
- `kaomoji-gif` as a subcommand of the binary.

QA for the whole change: tiers 0 and 1 green on both platforms, tier 2 green; `make deploy` to busy-screen.local, then
`ssh busy-screen.local` shows the MOTD's hero, `kaomoji hero --animate --loops 2 --exit` plays within the measured times
recorded in design.md; the curl line plays the hero on the Mac and on the Pi; and the GIFs regenerate with their boxes
unchanged.
