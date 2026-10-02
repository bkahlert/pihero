# Renders the GIFs in assets/ that the README shows: each character's whole animation and its preview grid.
# Needs asciinema and agg (brew install asciinema agg); the binary is built through the tools image, so
# podman and uv too. A GIF is rebuilt when the program or the renderer changed.
#   make -C packages/kaomoji                     # every stale GIF
#   make -C packages/kaomoji assets/hero.gif     # one
#   make -C packages/kaomoji .build/kaomoji      # just the binary for this Mac

CHARACTERS := hero wizard visitor
GIFS := $(foreach c,$(CHARACTERS),assets/$(c).gif assets/$(c)-grid.gif)
FONT := --font-family "Menlo,Apple Symbols"
BINARY := .build/kaomoji
GOOS := $(shell uname -s | tr A-Z a-z)
GOARCH := $(shell uname -m | sed -e 's/x86_64/amd64/' -e 's/aarch64/arm64/')

all: $(GIFS)

$(BINARY): kaomoji.go
	cd ../.. && uv run python -m pihero_testkit.tools -- env GOOS=$(GOOS) GOARCH=$(GOARCH) CGO_ENABLED=0 \
		go build -trimpath -ldflags "-s -w -X main.version=dev" -o /work/packages/kaomoji/$@ /work/packages/kaomoji/$<

assets/%-grid.gif: $(BINARY) kaomoji-gif
	./kaomoji-gif --output $@ $(FONT) --font-size 24 --hold 1 -- $(BINARY) $* --preview --loops 4 --exit

assets/%.gif: $(BINARY) kaomoji-gif
	./kaomoji-gif --output $@ $(FONT) --hold 1 -- $(BINARY) $* --animate --loops 2 --exit

.PHONY: all
