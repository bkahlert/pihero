# Renders the GIFs in assets/ that the README shows: each character's whole animation and its preview grid.
# Needs asciinema and agg (brew install asciinema agg); a GIF is rebuilt when its character, the
# engine, or the renderer changed.
#   make -C packages/kaomoji                     # every stale GIF
#   make -C packages/kaomoji assets/hero.gif     # one

CHARACTERS := hero wizard visitor
GIFS := $(foreach c,$(CHARACTERS),assets/$(c).gif assets/$(c)-grid.gif)
FONT := --font-family "Menlo,Apple Symbols"

all: $(GIFS)

assets/%-grid.gif: % kaomoji.bash kaomoji-gif
	./kaomoji-gif --output $@ $(FONT) --font-size 24 --hold 1 -- ./$< --preview --loops 4 --exit

assets/%.gif: % kaomoji.bash kaomoji-gif
	./kaomoji-gif --output $@ $(FONT) --hold 1 -- ./$< --animate --loops 2 --exit

.PHONY: all
