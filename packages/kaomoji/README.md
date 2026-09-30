# Kaomoji

The Pi Hero cast: three animated faces for the terminal, one bash script each on the shared engine
[kaomoji.bash](kaomoji.bash). Every call prints one kaomoji, static unless animated, colored on a terminal; `--help` on a
script lists its moods and options. How the engine paints, paces, and caches, and what was measured on a Raspberry Pi 1, is
in [docs/design.md](../../docs/design.md#kaomoji). The tests in [tests](tests) run in tier 0.

`apt install kaomoji` from the Pi Hero repository puts the three scripts on `PATH` and the engine in
`/usr/lib/kaomoji/`; `pihero` depends on it for its MOTD. In this directory they run as `./hero`, with the engine next to
them.

| Script             | Character                                                                                                  | Animation                              |
| ------------------ | ---------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| [hero](hero)       | The Pi Hero, `─=≡▰▩▩[ 蓬•ｏ•]⊐`: flies in from the left, hovers with a flickering tail, flies out to the right | ![hero](assets/hero.gif)               |
| [wizard](wizard)   | The Netmon wizard, `(つ◕౪◕)つ─｡ﾟ․☆･*ﾟ`: slides in, conjures the magic particle by particle, slides out         | ![wizard](assets/wizard.gif)           |
| [visitor](visitor) | The Busy Screen visitor, `┴┬┴┤´Ｏ´)ﾉ`: peeks out from behind a wall, waves and blinks, ducks back            | ![visitor](assets/visitor.gif)         |

```shell
./hero                                # one static kaomoji
./hero --mood happy --animate --exit  # flies in, hovers until Ctrl-C, then flies out
./wizard --loops 3 --exit             # entrance, three hover cycles, exit
./visitor --preview                   # every mood and style in a grid, animated
```

## Preview grids

One row per mood, one column per style: static and animated, each plain and colored.

![hero preview](assets/hero-grid.gif)

![wizard preview](assets/wizard-grid.gif)

![visitor preview](assets/visitor-grid.gif)

## Rendering the GIFs

[kaomoji-gif](kaomoji-gif) records a command with [asciinema](https://asciinema.org) and renders the recording with
[agg](https://github.com/asciinema/agg). The [Makefile](Makefile) holds the settings of the GIFs on this page; in this
directory:

```shell
brew install asciinema agg
make                                                        # every GIF whose character, engine, or renderer changed
./kaomoji-gif -- ./hero --animate --no-entrance --loops 1   # hero.gif: hovering once, a seamless loop
./kaomoji-gif --help                                        # font, size, padding, hold, theme
```

An endless animation never finishes recording, so give the command `--loops`.

The badge in the title of the repository's README, [assets/hero-badge.gif](../../assets/hero-badge.gif), is a one-off: a
recording of the hovering hero cut to 40 px with ffmpeg, grey and rounded like the badges next to it. It is kept as a file
with the logo, not rendered here, so that this renderer needs nothing but asciinema and agg.
