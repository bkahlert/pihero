# `kaomoji` in Go Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bash cast with one Go binary, `kaomoji hero|wizard|visitor`, built per architecture into the Debian
package and published with a bootstrap script so that `curl -fsSL …/releases/latest/download/hero | bash -s -- --animate`
plays the hero anywhere.

**Architecture:** One source file, [packages/kaomoji/kaomoji.go](../../../packages/kaomoji/kaomoji.go), standard library
only, holds the engine (ANSI terminal control, sprites of styled graphemes, a clock-paced animation loop, the preview grid,
the command line) and the three characters. A `build` script in the package cross-compiles five static binaries in the
tools image, which gains Debian's Go, packs three debs from one manifest, and renders the bootstrap script under four
names. The pytest suite stays the test of record and drives the binary through pipes exactly as it drove the scripts.

**Tech Stack:** Go (Debian trixie's `golang-go`, 1.24; no `go.mod`), nfpm, POSIX sh for the bootstrap, pytest with the
existing testkit, podman for the tools image, asciinema and agg for the GIFs.

**Spec:** [docs/superpowers/specs/2026-10-02-kaomoji-go-design.md](../specs/2026-10-02-kaomoji-go-design.md)

## Global Constraints

- One Go source file, `packages/kaomoji/kaomoji.go`, standard library only, no `go.mod`; `go run kaomoji.go hero` must
  work from a bare checkout. No language feature beyond Go 1.24's (the Mac used to write this plan has 1.21 and compiles it).
- Platforms: Linux and macOS, arm64 and amd64, plus Linux ARMv6 (`GOARCH=arm GOARM=6`) for the Pi 1. No Windows.
- Terminal control with hardcoded ANSI only, never tput or terminfo: `\x1b[?25l` hide, `\x1b[?25h` show, `\x1b[K` erase to
  the end of the line, `\x1b[A` up, `\x1b7`/`\x1b8` save and restore the cursor, `\x1b[0m` reset, `\x1b[2m` dim.
- Colors: a style is a basic color 0–15 or a hex color with its 256-color index; hex paints as truecolor when `COLORTERM`
  is `truecolor` or `24bit`, by index when `TERM` contains `256color` or `direct`, and is dropped otherwise; basic colors
  always paint. Color is on when stdout is a terminal, `NO_COLOR` is unset and `TERM` is not `dumb`, or with `--color`.
- Pacing: constant acceleration with `easing = 75`; frames are never skipped; a late frame goes out at once and the
  schedule moves with it. `--frame-ms 0` emits every frame without waiting.
- Line width: `KAOMOJI_COLUMNS` if set (0 means the character's own width), else the terminal's width less one, the width
  being the TIOCGWINSZ ioctl on stdout, else `COLUMNS`, else 80.
- Command line: `kaomoji <character> [options]`; `kaomoji` alone, an unknown character or option, a bad value: usage
  hint to stderr, exit 2, as `kaomoji: <message>\nSee 'kaomoji hero --help'\n`. `--version` prints the linked version.
- Signals: with `--exit` on an endless animation the first SIGINT or SIGTERM plays the exit and the second quits at once;
  otherwise the first quits. Quitting prints a newline and shows the cursor, exit status 130.
- Package: `kaomoji_<version>_{armhf,arm64,amd64}.deb`, `/usr/bin/kaomoji` only, no dependencies, section admin.
- Release assets: the debs, `kaomoji-linux-armv6`, `kaomoji-linux-arm64`, `kaomoji-linux-amd64`, `kaomoji-darwin-arm64`,
  `kaomoji-darwin-amd64`, and the scripts `kaomoji`, `hero`, `wizard`, `visitor`. The release is created as a draft and
  published once every asset is uploaded.
- Commits follow Conventional Commits with the package as scope; no AI attribution trailers. The commit that drops the
  three commands carries `BREAKING CHANGE: hero, wizard, and visitor are kaomoji hero, kaomoji wizard, and kaomoji visitor`.
- Every behaviour change ships with its tests in the same task; docs that describe the behaviour change in the same task.

## Notes against the spec

Three places where the plan is more specific than the spec, or departs from a sentence of it, decided while compiling the
program this plan carries:

- **No frame cache.** The spec keeps hover frames once rendered. A frame renders in microseconds in Go, so the program
  renders every frame when due and compares it with the one shown; a cache would be code for nothing.
- **The easing is the bash engine's discrete schedule.** Frame i of an entrance of n steps stays
  `total/n - total·75·(n-1-2i)/(100·n·(n-1))`, the exit the mirror image: constant acceleration, fastest interval a quarter
  of the mean, slowest one and three quarters, which is the spec's "due when the eased progress reaches i/N" in discrete
  form, and keeps the exit at sixteen frame times on any width.
- **SIGTERM without `--exit` quits like SIGINT.** The bash engine trapped only SIGINT there and died of SIGTERM with the
  cursor hidden; the binary restores the cursor and exits 130 for both.

## Review Focus

Inputs the spec implies but does not spell out; each has its test in the task named:

1. A non-numeric or negative `--loops` or `--frame-ms`, or `--mood` without a value: a usage hint and exit 2, not a Go
   panic or a silently endless animation (Task 3, `TestCommandLine.test_rejects_a_bad_option_value`).
2. A terminal narrower than the hero, `COLUMNS=10`: the animation completes and the hero leaves, it does not loop or crash
   (Task 3, `TestLine.test_a_line_narrower_than_the_hero_still_sees_it_leave`).
3. `KAOMOJI_COLUMNS` set to something that is no number: ignored, the terminal's width is used (Task 3,
   `TestLine.test_kaomoji_columns_that_is_no_number_is_ignored`).
4. `TERM` unset or empty with `--color`: paints what it can, prints the face, exits 0 (Task 3,
   `TestColor.test_survives_an_unset_term`).
5. The bootstrap on a machine with no binary, `Linux mips`, or a download whose hash does not match: a one-line message,
   exit 1, nothing left in the cache (Task 5, `TestBootstrap`).

## File structure

```
packages/kaomoji/
  kaomoji.go              # new: engine and the three characters, see Task 3
  build                   # new: cross-compiles, packs, renders the bootstrap; runs in the tools image, see Task 4
  nfpm.yaml.in            # new: the manifest with ${ARCH}, ${VERSION}, ${BINARY}; replaces nfpm.yaml
  bootstrap.sh            # new: the curl-line script template
  kaomoji-gif             # modified: self-contained, records ./.build/kaomoji <character>
  Makefile                # modified: builds .build/kaomoji through the tools image, records from it
  tests/conftest.py       # modified: the binary fixture, Kaomoji(binary, character)
  tests/test_kaomoji.py   # rewritten: command line, colors, line width, pacing, signals, preview
  tests/test_hero.py      # modified: per-cell entrance, 16 steps
  tests/test_wizard.py  tests/test_visitor.py   # unchanged assertions
  tests/test_bootstrap.py # new
  tests/test_build.py     # new: the build script through the tools image
  tests/test_installed.py # modified: /usr/bin/kaomoji, kaomoji hero
  tests/test_kaomoji_gif.py # modified: records the binary
  removed: kaomoji.bash, hero, wizard, visitor, nfpm.yaml
testkit/src/pihero_testkit/tools/Containerfile   # golang-go
testkit/src/pihero_testkit/tools.py              # GO_CACHE, main(argv)
testkit/src/pihero_testkit/build.py              # build_in_tools, is_package
testkit/tests/test_tools.py  testkit/tests/test_build.py  testkit/tests/test_static.py
packages/pihero/root/usr/lib/pihero/motd  packages/pihero/tests/test_motd.py
.github/workflows/release.yml
docs/design.md  docs/testing.md  docs/app-conventions.md  README.md  packages/kaomoji/README.md
```

Every command below runs from the repository root unless it says otherwise. Tier-0 tests of this package run as
`uv run pytest packages/kaomoji/tests -q`; the whole tier as `make test-tier0`.

---

### Task 1: Go in the tools image, and a command line to run things there

**Files:**
- Modify: `testkit/src/pihero_testkit/tools/Containerfile`
- Modify: `testkit/src/pihero_testkit/tools.py`
- Test: `testkit/tests/test_tools.py`

**Interfaces:**
- Produces: `tools.GO_CACHE: str`, a podman mount spec `"pihero-go-cache:/root/.cache/go-build"`, to pass as
  `mounts=[tools.GO_CACHE]` to `tools.run`/`tools.command` whenever a command runs `go`.
- Produces: `tools.main(argv: list[str]) -> int`: no arguments prints the tools image tag; `["--", *command]` runs the
  command in the tools image with the Go cache mounted and returns its exit status. Invoked as
  `uv run python -m pihero_testkit.tools -- <command>`.

- [ ] **Step 1: Write the failing tests**

Append to `testkit/tests/test_tools.py`:

```python
import subprocess
import sys


class TestMain:
    def test_without_arguments_prints_the_tools_image(self, capsys):
        status = tools.main([])

        assert status == 0
        assert capsys.readouterr().out.strip() == tools.image()

    def test_runs_a_command_in_the_tools_image_and_returns_its_status(self):
        result = subprocess.run([sys.executable, "-m", "pihero_testkit.tools", "--", "sh", "-c", "go version; exit 3"], capture_output=True, text=True)

        assert result.returncode == 3
        assert result.stdout.startswith("go version go1.")

    def test_keeps_gos_build_cache_in_a_volume(self):
        result = subprocess.run([sys.executable, "-m", "pihero_testkit.tools", "--", "sh", "-c", "go env GOCACHE; mount | grep -c /root/.cache/go-build"], capture_output=True, text=True)

        assert result.stdout.splitlines() == ["/root/.cache/go-build", "1"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest testkit/tests/test_tools.py -q -k TestMain`
Expected: FAIL, `tools` has no attribute `main`; the subprocess ones fail on `go: not found` or status 0.

- [ ] **Step 3: Add Go to the tools image**

In `testkit/src/pihero_testkit/tools/Containerfile`, extend the first `apt-get install` line list so it reads:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg \
      apt-utils dpkg-dev shellcheck systemd cloud-init python3 python3-yaml \
      mtools dosfstools e2fsprogs xz-utils util-linux mount fdisk qemu-utils \
      golang-go \
    && rm -rf /var/lib/apt/lists/*
```

The image is tagged by the file's digest, so the next `tools.ensure_image()` rebuilds it (a few minutes once).

- [ ] **Step 4: Add the cache mount and the command line to tools.py**

Below `CONTAINERFILE = …` add:

```python
# Go's build cache, kept in a named volume across the one-shot containers: without it every build
# recompiles the standard library, with it a build takes seconds.
GO_CACHE = "pihero-go-cache:/root/.cache/go-build"
```

Replace the `if __name__ == "__main__":` block at the end with:

```python
def main(argv: list[str]) -> int:
    """Without arguments prints the tools image; with `-- <command>` runs the command in it, Go's cache mounted, and returns its status."""
    if not argv:
        print(ensure_image())
        return 0
    if argv[0] == "--":
        argv = argv[1:]
    return run(argv, check=False, mounts=[GO_CACHE]).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Update the module docstring to: `"""Runs commands in pinned container images, the tools image by default, building an image on first use; `python -m pihero_testkit.tools -- <command>` runs one from the shell."""`

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest testkit/tests/test_tools.py -q`
Expected: all PASS (the first run builds the image).

- [ ] **Step 6: Commit**

```bash
git add testkit/src/pihero_testkit/tools/Containerfile testkit/src/pihero_testkit/tools.py testkit/tests/test_tools.py
git commit -m "feat(testkit): run a command in the tools image from the shell, with Go in it"
```

---

### Task 2: A build script without a Containerfile runs in the tools image

**Files:**
- Modify: `testkit/src/pihero_testkit/build.py`
- Test: `testkit/tests/test_build.py`

**Interfaces:**
- Consumes: `tools.GO_CACHE`, `tools.command` from Task 1.
- Produces: `build.build_in_tools(pkg_dir: Path, version: str, dist: Path = DIST) -> list[Path]`: runs
  `/work/packages/<name>/build --dist /work/<dist> --version <version>` in the tools image and returns the `.deb` paths the
  script printed; raises `RuntimeError` when it printed none. `build.is_package` is true for a directory with a `build`
  script alone; `build_all` routes such a directory here.

- [ ] **Step 1: Write the failing tests**

In `testkit/tests/test_build.py`, change `TestIsPackage.test_is_false_for_a_build_script_alone` to:

```python
    def test_is_true_for_a_build_script_alone(self, tmp_path):
        (tmp_path / "build").write_text("#!/bin/sh\n")

        assert build.is_package(tmp_path)
```

Change `probe_script` to take the Containerfile as an option and add the new test class:

```python
def probe_script(name: str, body: str, containerfile: bool = True) -> tuple[Path, Path]:
    pkg = Path("dist") / f"probe-{name}" / "src" / name
    pkg.mkdir(parents=True, exist_ok=True)
    if containerfile:
        (pkg / "Containerfile").write_text(f"FROM {tools.ensure_image()}\nHEALTHCHECK NONE\n")
    script = pkg / "build"
    script.write_text('#!/bin/sh\nset -e\n[ "$1" = --dist ] && shift\n' + body)
    script.chmod(0o755)
    return pkg, Path.cwd() / "dist" / f"probe-{name}"


class TestBuildInTools:
    def test_runs_the_script_in_the_tools_image_with_the_version_and_returns_the_debs_it_prints(self):
        # after the helper's shift: $1 is the dist directory, $2 is --version, $3 the version
        pkg, dist = probe_script("pihero-zz-tools", 'deb="$1/pihero-zz-tools_$3_arm64.deb"\n: > "$deb"\nprintf "%s\\n" "$deb"\n', containerfile=False)
        try:
            debs = build.build_in_tools(pkg, "9.9.9", dist=dist)

            assert debs == [dist / "pihero-zz-tools_9.9.9_arm64.deb"]
            assert debs[0].exists()
        finally:
            remove_probe(pkg)

    def test_fails_on_a_script_that_prints_no_deb(self):
        pkg, dist = probe_script("pihero-zz-mute", 'echo building >&2\n', containerfile=False)
        try:
            with pytest.raises(RuntimeError, match="pihero-zz-mute"):
                build.build_in_tools(pkg, "9.9.9", dist=dist)
        finally:
            remove_probe(pkg)

    def test_has_go_on_path(self):
        pkg, dist = probe_script("pihero-zz-go", 'go version >&2\ndeb="$1/pihero-zz-go_$3_all.deb"\n: > "$deb"\nprintf "%s\\n" "$deb"\n', containerfile=False)
        try:
            assert build.build_in_tools(pkg, "1.0", dist=dist) == [dist / "pihero-zz-go_1.0_all.deb"]
        finally:
            remove_probe(pkg)
```

`remove_probe` calls `podman rmi` on an image that does not exist for these probes; it already ignores that failure.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest testkit/tests/test_build.py -q -k "TestBuildInTools or build_script_alone"`
Expected: FAIL, no `build_in_tools`, and `is_package` false.

- [ ] **Step 3: Implement**

In `testkit/src/pihero_testkit/build.py`:

```python
def is_package(directory: Path) -> bool:
    """Returns whether directory builds a package: nfpm.yaml is there, or a build script."""
    return (directory / "nfpm.yaml").is_file() or (directory / "build").is_file()
```

Add after `build_script`:

```python
def build_in_tools(pkg_dir: Path, version: str, dist: Path = DIST) -> list[Path]:
    """Runs the package directory's build script in the tools image with the version; returns the debs the script printed."""
    pkg_dir = pkg_dir.resolve()
    dist = dist.resolve()
    dist.mkdir(parents=True, exist_ok=True)
    script = f"/work/{pkg_dir.relative_to(Path.cwd())}/build"
    # Only the deb paths come through stdout; the build's own output stays on the terminal.
    command = tools.command([script, "--dist", f"/work/{dist.relative_to(Path.cwd())}", "--version", version], mounts=[tools.GO_CACHE])
    result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE)
    debs = [Path.cwd() / line.removeprefix("/work/") for line in result.stdout.splitlines() if line.startswith("/work/")]
    if not debs:
        raise RuntimeError(f"{pkg_dir.name}: the build script printed no .deb path")
    return debs
```

Change `build_all`'s loop to:

```python
    for pkg_dir in discover():
        if (pkg_dir / "nfpm.yaml").exists():
            debs.append(build(pkg_dir, version, dist))
        elif (pkg_dir / "Containerfile").exists():
            debs.extend(build_script(pkg_dir, dist))
        else:
            debs.extend(build_in_tools(pkg_dir, version, dist))
```

Update the module docstring: `"""Builds every package under packages/ into dist/: nfpm manifests and plain build scripts in the tools container, build scripts with a Containerfile in their own image."""` and the `is_package` docstring as shown.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest testkit/tests/test_build.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/build.py testkit/tests/test_build.py
git commit -m "feat(testkit): run a package's build script in the tools image when it has no image of its own"
```

---

### Task 3: The binary, and the suite running against it

**Files:**
- Create: `packages/kaomoji/kaomoji.go`
- Rewrite: `packages/kaomoji/tests/conftest.py`, `packages/kaomoji/tests/test_kaomoji.py`
- Modify: `packages/kaomoji/tests/test_hero.py`
- Modify: `testkit/tests/test_static.py`
- Unchanged but now exercising the binary: `packages/kaomoji/tests/test_wizard.py`, `packages/kaomoji/tests/test_visitor.py`

**Interfaces:**
- Consumes: `tools.run`, `tools.GO_CACHE` from Task 1.
- Produces: the binary's command line as in Global Constraints; the session fixture `binary` building
  `packages/kaomoji/.build/kaomoji` for this machine with `-X main.version=test`; the fixture `kaomoji(character=None, term="xterm-256color", columns=80, env={})` returning a `Kaomoji` with `run`, `static`, `frames`, `grid`, `stopped`, `blocked`, `moods`, and the static helpers `split_frames`, `split_grid`, `plain`. Later tasks run the binary as `packages/kaomoji/.build/kaomoji`.

The bash scripts stay in place until Task 5; nothing in this task touches them, and their tests of the GIF renderer keep passing.

- [ ] **Step 1: Write the fixtures**

Replace `packages/kaomoji/tests/conftest.py` with:

```python
import os
import platform
import re
import subprocess
import time
from pathlib import Path

import pytest

from pihero_testkit import tools

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE / "kaomoji.go"
BINARY = PACKAGE / ".build" / "kaomoji"
ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[78]")  # CSI sequences, save and restore cursor
CIVIS, CNORM, CUU1 = "\x1b[?25l", "\x1b[?25h", "\x1b[A"


@pytest.fixture(scope="session")
def binary() -> Path:
    """The binary for this machine, built through the tools image when the source is newer than the last build."""
    if not BINARY.exists() or BINARY.stat().st_mtime < SOURCE.stat().st_mtime:
        BINARY.parent.mkdir(exist_ok=True)
        goos = {"Darwin": "darwin", "Linux": "linux"}[platform.system()]
        goarch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}[platform.machine()]
        tools.run(
            ["env", f"GOOS={goos}", f"GOARCH={goarch}", "CGO_ENABLED=0", "go", "build", "-trimpath", "-ldflags", "-s -w -X main.version=test",
             "-o", f"/work/{BINARY.relative_to(Path.cwd())}", f"/work/{SOURCE.relative_to(Path.cwd())}"],
            mounts=[tools.GO_CACHE],
        )
    return BINARY


class Kaomoji:
    """Runs the binary for one character, or without one, on a 256-color terminal and takes its output apart."""

    def __init__(self, binary: Path, character: str | None = None, term: str = "xterm-256color", columns: int = 80, env: dict[str, str] | None = None):
        self.binary = binary
        self.character = character
        self.term = term
        self.columns = columns  # the terminal's width, as COLUMNS reports it to a program without a terminal
        self.extra_env = env or {}

    def command(self, *args: str) -> list[str]:
        return [str(self.binary), *([self.character] if self.character else []), *args]

    def run(self, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(self.command(*args), capture_output=True, env=self.env())
        # decoded by hand: text mode would turn the \r between frames into newlines
        return subprocess.CompletedProcess(result.args, result.returncode, result.stdout.decode(), result.stderr.decode())

    def stopped(self, *args: str, signals: list[int], frame_mark: bytes = b"\r") -> subprocess.CompletedProcess:
        """Runs an endless animation and sends each signal once two more frames have shown."""
        proc = subprocess.Popen(self.command("--no-color", *args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env(), bufsize=0)
        out = b""
        for sig in signals:
            seen = out.count(frame_mark)
            while out.count(frame_mark) < seen + 2:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                out += chunk
            proc.send_signal(sig)
        rest, err = proc.communicate(timeout=10)
        return subprocess.CompletedProcess(proc.args, proc.returncode, (out + rest).decode(), err.decode())

    def blocked(self, *args: str, signals: list[int]) -> subprocess.CompletedProcess:
        """Runs an animation into a pipe nobody reads, so that it blocks in a write, and sends each signal there."""
        proc = subprocess.Popen(self.command("--no-color", "--frame-ms", "0", *args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env(), bufsize=0)
        for sig in signals:
            time.sleep(0.5)  # the pipe is full and the program blocked long before that
            proc.send_signal(sig)
        out, err = proc.communicate(timeout=10)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out.decode(), err.decode())

    @staticmethod
    def plain(out: str) -> str:
        """The output without escape sequences."""
        return ESCAPES.sub("", out)

    def static(self, mood: str) -> str:
        return self.run("--mood", mood, "--no-color").stdout.rstrip("\n")

    def frames(self, *args: str, color: bool = False) -> list[str]:
        """The frames of a single-line animation, one per step; --frame-ms implies --animate."""
        out = self.run("--color" if color else "--no-color", "--frame-ms", "0", *args).stdout
        return self.split_frames(out, color)

    @staticmethod
    def split_frames(out: str, color: bool = False) -> list[str]:
        """Splits an animation's output into its frames, escape sequences stripped unless colored."""
        chunks = out.split("\r")[1:]  # before the first \r the cursor is only hidden
        chunks[-1] = chunks[-1].split("\n")[0]  # the newline and the returning cursor end the animation
        return [c if color else ESCAPES.sub("", c) for c in chunks]

    def grid(self, *args: str) -> list[list[str]]:
        """The frames of the preview grid, each as its header line followed by one line per mood."""
        out = self.run("--preview", "--frame-ms", "0", *args).stdout
        return self.split_grid(out, 1 if "--mood" in args else len(self.moods()))

    @staticmethod
    def split_grid(out: str, moods: int) -> list[list[str]]:
        """Splits a preview's output at the cursor moving back up, into the non-empty lines of each redraw."""
        frames = []
        for chunk in out.split(CUU1 * (1 + 2 * moods)):
            lines = [line for line in ESCAPES.sub("", chunk).split("\n") if line.strip()]
            frames.append(lines)
        return frames

    def moods(self) -> list[str]:
        line = next(l for l in self.run("--help").stdout.splitlines() if l.strip().startswith("--mood <mood>"))
        return line.split("One of", 1)[1].split(" (")[0].strip(" .").split(", ")

    def env(self) -> dict[str, str]:
        env = {**os.environ, "TERM": self.term, "COLUMNS": str(self.columns)}
        for key in ("NO_COLOR", "COLORTERM", "KAOMOJI_COLUMNS"):
            env.pop(key, None)
        return {**env, **self.extra_env}


@pytest.fixture
def kaomoji(binary):
    def factory(character: str | None = None, **kwargs) -> Kaomoji:
        return Kaomoji(binary, character, **kwargs)

    factory.split_frames = Kaomoji.split_frames
    factory.split_grid = Kaomoji.split_grid
    factory.plain = Kaomoji.plain
    return factory
```

- [ ] **Step 2: Write the engine tests**

Replace `packages/kaomoji/tests/test_kaomoji.py` with:

```python
import re
import signal
import time
import unicodedata

import pytest

pytestmark = pytest.mark.tier0

CNORM, CUU1 = "\x1b[?25h", "\x1b[A"
HERO = "─=≡▰▩▩[ 蓬•ｏ•]⊐"


class TestCommandLine:
    def test_help_names_the_cast(self, kaomoji):
        result = kaomoji().run("--help")

        assert result.returncode == 0
        assert result.stdout.startswith("Usage: kaomoji <character>")
        assert "hero, wizard, and visitor" in result.stdout

    def test_a_characters_help_is_its_header_with_its_moods(self, kaomoji):
        result = kaomoji("hero").run("--help")

        assert result.returncode == 0
        assert result.stdout.startswith("Purpose: Render the Pi Hero kaomoji")
        assert kaomoji("hero").moods() == ["neutral", "happy", "sad", "unknown"]

    def test_version_is_what_the_build_linked_in(self, kaomoji):
        result = kaomoji().run("--version")

        assert result.returncode == 0
        assert result.stdout == "test\n"

    def test_needs_a_character(self, kaomoji):
        result = kaomoji().run()

        assert result.returncode == 2
        assert result.stderr == "kaomoji: character missing\nSee 'kaomoji --help'\n"

    def test_rejects_an_unknown_character(self, kaomoji):
        result = kaomoji().run("dragon")

        assert result.returncode == 2
        assert result.stderr == "kaomoji: unknown character: dragon\nSee 'kaomoji --help'\n"

    def test_rejects_unknown_options_with_a_hint(self, kaomoji):
        result = kaomoji("hero").run("--bogus")

        assert result.returncode == 2
        assert result.stderr == "kaomoji: unknown option: --bogus\nSee 'kaomoji hero --help'\n"

    def test_rejects_unknown_moods(self, kaomoji):
        result = kaomoji("hero").run("--mood", "grumpy")

        assert result.returncode == 2
        assert "unknown mood: grumpy" in result.stderr

    @pytest.mark.parametrize(("args", "message"), [(["--loops", "many"], "--loops: not a number: many"), (["--frame-ms", "-1"], "--frame-ms: not a number: -1"), (["--mood"], "--mood: missing value")])
    def test_rejects_a_bad_option_value(self, kaomoji, args, message):
        result = kaomoji("hero").run(*args)

        assert result.returncode == 2
        assert result.stderr == f"kaomoji: {message}\nSee 'kaomoji hero --help'\n"

    def test_renders_the_first_mood_by_default(self, kaomoji):
        assert kaomoji("hero").run().stdout == HERO + "\n"

    def test_is_plain_when_stdout_is_no_terminal(self, kaomoji):
        assert kaomoji("hero").run("--mood", "happy").stdout == "─=≡▰▩▩[✿＾ｖ＾]⊐\n"

    class TestAnimate:
        def test_is_off_by_default(self, kaomoji):
            assert "\r" not in kaomoji("hero").run("--mood", "happy").stdout

        @pytest.mark.parametrize("option", [["--no-entrance"], ["--exit"], ["--frame-ms", "0"], ["--animate"]])
        def test_is_implied_by_the_animation_options(self, kaomoji, option):
            result = kaomoji("hero").run(*option, "--loops", "1", "--frame-ms", "0")

            assert result.returncode == 0
            assert result.stdout.count("\r") > 1


class TestColor:
    def test_paints_the_heros_palette_by_index_on_a_256_color_terminal(self, kaomoji):
        out = kaomoji("hero").run("--mood", "happy", "--color").stdout

        assert "\x1b[38;5;214m" in out and "\x1b[48;5;221m" in out
        assert out.startswith("\x1b[2m─=≡\x1b[0m")  # the dim tail, one sequence for the three graphemes

    def test_paints_it_by_value_when_colorterm_says_truecolor(self, kaomoji):
        out = kaomoji("hero", env={"COLORTERM": "truecolor"}).run("--color").stdout

        assert "\x1b[38;2;246;181;53m" in out and "\x1b[48;2;247;220;56m" in out
        assert "38;5" not in out

    def test_drops_hex_colors_on_a_terminal_without_256_colors_but_keeps_the_basic_ones(self, kaomoji):
        hero = kaomoji("hero", term="xterm").run("--color").stdout
        wizard = kaomoji("wizard", term="xterm").run("--color").stdout

        assert "38;5" not in hero and "\x1b[30m" in hero  # the black of the face stays
        assert "\x1b[37m(" in wizard and "\x1b[91m｡" in wizard  # gray, and bright pink as 91

    def test_paints_the_basic_sixteen_as_the_terminal_sets_them(self, kaomoji):
        out = kaomoji("visitor").run("--color").stdout

        assert out.startswith("\x1b[2m┴┬┴┤\x1b[0m\x1b[97m")  # the dim wall, then white

    def test_survives_an_unset_term(self, kaomoji):
        result = kaomoji("hero", term="").run("--color")

        assert result.returncode == 0
        assert kaomoji.plain(result.stdout) == HERO + "\n"

    def test_no_color_wins_over_color(self, kaomoji):
        assert kaomoji("hero").run("--color", "--no-color").stdout == HERO + "\n"


class TestLine:
    """The cells a frame's line has, which the hero's exit crosses."""

    def test_follows_columns_less_the_last_one_without_a_terminal(self, kaomoji):
        frames = kaomoji("hero", columns=30).frames("--no-entrance", "--loops", "1", "--exit")

        assert len(frames) == 12 + 29

    def test_kaomoji_columns_zero_keeps_the_hero_to_its_own_width(self, kaomoji):
        frames = kaomoji("hero", env={"KAOMOJI_COLUMNS": "0"}).frames("--no-entrance", "--loops", "1", "--exit")

        assert len(frames) == 12 + 16
        assert frames[-2] == " " * 15 + "-" and frames[-1] == ""

    def test_kaomoji_columns_that_is_no_number_is_ignored(self, kaomoji):
        frames = kaomoji("hero", columns=30, env={"KAOMOJI_COLUMNS": "wide"}).frames("--no-entrance", "--loops", "1", "--exit")

        assert len(frames) == 12 + 29

    def test_a_line_narrower_than_the_hero_still_sees_it_leave(self, kaomoji):
        frames = kaomoji("hero", columns=10).frames("--loops", "1", "--exit")

        assert len(frames) == 1 + 16 + 12 + 9
        assert frames[-1] == ""


class TestPacing:
    def test_holds_every_frame_for_the_frame_time(self, kaomoji):
        started = time.monotonic()
        frames = kaomoji("hero").frames("--no-entrance", "--loops", "1", "--frame-ms", "40")
        elapsed = time.monotonic() - started

        assert len(frames) == 12
        assert elapsed >= 11 * 0.040

    def test_shows_the_first_frame_at_once(self, kaomoji):
        started = time.monotonic()
        kaomoji("hero").run("--no-color", "--no-entrance", "--loops", "0", "--frame-ms", "1000")
        elapsed = time.monotonic() - started

        assert elapsed < 0.5  # no warm-up: the landed frame is the whole animation with zero loops


class TestStopping:
    @pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM])
    def test_an_endless_animation_with_exit_plays_the_exit_when_stopped(self, kaomoji, stop):
        result = kaomoji("visitor").stopped("--exit", "--no-entrance", "--frame-ms", "20", signals=[stop])

        assert result.returncode == 0
        assert kaomoji.split_frames(result.stdout)[-4:] == ["┬┴┤", "┴┤", "┤", ""]
        assert result.stdout.endswith("\n" + CNORM)

    def test_quits_at_once_on_a_second_interrupt(self, kaomoji):
        result = kaomoji("visitor").stopped("--exit", "--no-entrance", "--frame-ms", "50", signals=[signal.SIGINT] * 2)

        drawn = [frame for frame in kaomoji.split_frames(result.stdout) if frame]
        assert result.returncode == 130
        assert drawn[-1].startswith("┴┬┴┤")

    @pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM])
    def test_an_animation_without_exit_quits_at_once(self, kaomoji, stop):
        result = kaomoji("hero").stopped("--no-entrance", "--frame-ms", "20", signals=[stop])

        assert result.returncode == 130
        assert result.stdout.endswith("\n" + CNORM)

    class TestSlowTerminal:
        """A signal arrives while a write to a full pipe blocks; the frame is completed and the signal handled."""

        def test_the_preview_finishes_the_redraw_and_quits(self, kaomoji):
            result = kaomoji("hero").blocked("--preview", signals=[signal.SIGINT])

            assert result.stderr == ""
            assert result.returncode == 130
            assert len(kaomoji.split_grid(result.stdout, 4)[-1]) == 1 + 4
            assert kaomoji.plain(result.stdout).endswith("\n\n") and result.stdout.endswith(CNORM)

        def test_an_endless_animation_plays_the_exit(self, kaomoji):
            result = kaomoji("visitor").blocked("--exit", "--no-entrance", signals=[signal.SIGTERM])

            assert result.stderr == ""
            assert result.returncode == 0
            assert kaomoji.split_frames(result.stdout)[-4:] == ["┬┴┤", "┴┤", "┤", ""]

        def test_an_animation_quits_at_once(self, kaomoji):
            result = kaomoji("hero").blocked("--no-entrance", signals=[signal.SIGINT])

            assert result.stderr == ""
            assert result.returncode == 130
            assert result.stdout.endswith("\n" + CNORM)


class TestPreview:
    def test_shows_a_grid_of_every_mood(self, kaomoji):
        header, *rows = kaomoji("hero").grid("--loops", "1")[-1]

        assert header.split()[0] == "mood"
        assert [row.split()[0] for row in rows] == ["neutral", "happy", "sad", "unknown"]

    def test_narrows_to_the_given_mood(self, kaomoji):
        header, *rows = kaomoji("hero").grid("--mood", "happy", "--loops", "1")[-1]

        assert [row.split()[0] for row in rows] == ["happy"]

    def test_leaves_the_cursor_below_the_grid_when_interrupted(self, kaomoji):
        result = kaomoji("hero").stopped("--preview", "--frame-ms", "20", signals=[signal.SIGINT], frame_mark=CUU1.encode())

        assert result.returncode == 130
        assert len(kaomoji.split_grid(result.stdout, 4)[-1]) == 1 + 4  # the header and every row, redrawn completely
        assert kaomoji.plain(result.stdout).endswith("\n\n") and result.stdout.endswith(CNORM)

    def test_lines_up_a_face_narrower_than_the_titles_under_them(self, kaomoji):
        header, *rows = kaomoji("visitor").grid("--loops", "1")[-1]

        titles = ["static plain", "static color", "animated plain", "animated color"]
        title_columns = [columns(header[: header.index(title)]) for title in titles]
        for row in rows:
            assert [columns(row[: wall.start()]) for wall in re.finditer("┴┬┴┤", row)] == title_columns

    def test_colors_the_color_columns_whatever_stdout_is(self, kaomoji):
        out = kaomoji("hero").run("--preview", "--mood", "happy", "--no-entrance", "--loops", "0", "--frame-ms", "0").stdout

        assert out.count("\x1b[38;5;214m") == 4  # one redraw: the [ and the ] of the static and the animated colored hero


def columns(text: str) -> int:
    """Display width, counting East Asian wide and fullwidth characters twice like the engine does."""
    return sum(2 if unicodedata.east_asian_width(c) in "FW" else 1 for c in text)
```

- [ ] **Step 3: Adapt the hero's entrance tests to one cell per step**

In `packages/kaomoji/tests/test_hero.py` change the constants line to

```python
ENTRANCE, CYCLE, EXIT = 16, 12, COLUMNS - 1  # neutral: cells, hover steps, cells before the last column
```

and replace `test_flies_in_from_the_left_one_grapheme_per_step` with:

```python
    def test_flies_in_from_the_left_one_cell_per_step(self, frames):
        assert frames[0] == ""
        assert frames[1] == "⊐"
        assert frames[2] == "]⊐"
        assert frames[3] == "•]⊐"
        assert frames[4] == " •]⊐"  # the wide ｏ straddles the edge and waits a step
        assert frames[5] == "ｏ•]⫎"
        assert frames[ENTRANCE] == STATIC["neutral"]
```

Nothing else in `test_hero.py`, `test_wizard.py`, or `test_visitor.py` changes: their `kaomoji("hero", columns=COLUMNS)` and `kaomoji("wizard")` calls fit the new fixture.

- [ ] **Step 4: Run the suite to verify it fails**

Run: `uv run pytest packages/kaomoji/tests -q --ignore=packages/kaomoji/tests/test_kaomoji_gif.py`
Expected: ERROR in the `binary` fixture, `kaomoji.go` does not exist.

- [ ] **Step 5: Write the program**

Create `packages/kaomoji/kaomoji.go`. This is the whole file; it compiles with Go 1.21 and later, `gofmt -l` is silent and `go vet` clean:

```go
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
// truecolor, else as their 256-color index, and a TERM without "256color" drops them; TERM=dumb is plain;
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

// The depth a terminal paints at: colors16 drops hex colors, colors256 paints them by index, truecolor by value.
type depth int

const (
	colors16 depth = iota
	colors256
	truecolor
)

// sgr returns the SGR sequence setting the color as a foreground (layer 3) or a background (layer 4),
// or "" where the depth lacks it.
func (c color) sgr(layer int, d depth) string {
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

func (s style) sgr(d depth) string {
	var b strings.Builder
	if s.dim {
		b.WriteString(dim)
	}
	b.WriteString(s.fg.sgr(3, d))
	b.WriteString(s.bg.sgr(4, d))
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

// terminalDepth reads the environment: truecolor when COLORTERM says so, 256 colors when TERM does, else
// the basic sixteen.
func terminalDepth() depth {
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
```

- [ ] **Step 6: Run the suite to verify it passes**

Run: `uv run pytest packages/kaomoji/tests -q --ignore=packages/kaomoji/tests/test_kaomoji_gif.py`
Expected: all PASS; the first run builds the binary through the tools image (seconds with the cache volume warm, longer the first time). Then run `uv run pytest packages/kaomoji/tests -q` to see the GIF tests still pass against the bash scripts.

- [ ] **Step 7: Add the Go static checks**

In `testkit/tests/test_static.py` add after `unit_files()`:

```python
def go_files():
    for path in (ROOT / "packages").rglob("*.go"):
        if ".build" not in path.parts:
            yield path
```

and after `test_shell_file_passes_shellcheck`:

```python
@pytest.mark.parametrize("source", sorted(go_files()), ids=lambda p: str(p.relative_to(ROOT)))
def test_go_file_is_formatted_and_vets_clean(source):
    path = f"/work/{source.relative_to(ROOT)}"
    unformatted = tools.run(["gofmt", "-l", path], capture=True).stdout
    vet = tools.run(["go", "vet", path], check=False, capture=True, mounts=[tools.GO_CACHE])

    assert unformatted == ""
    assert vet.returncode == 0, vet.stderr
```

Run: `uv run pytest testkit/tests/test_static.py -q -k go_file`
Expected: PASS. Then break the formatting on purpose (add two spaces before a `}` in `kaomoji.go`), run again, see it FAIL on `unformatted`, and undo.

- [ ] **Step 8: Commit**

```bash
git add packages/kaomoji/kaomoji.go packages/kaomoji/tests/conftest.py packages/kaomoji/tests/test_kaomoji.py packages/kaomoji/tests/test_hero.py testkit/tests/test_static.py
git commit -m "feat(kaomoji): render and animate the cast from one Go binary"
```

---

### Task 4: The build script, the per-architecture debs, and the bootstrap

**Files:**
- Create: `packages/kaomoji/build`, `packages/kaomoji/nfpm.yaml.in`, `packages/kaomoji/bootstrap.sh`
- Delete: `packages/kaomoji/nfpm.yaml`
- Rewrite: `packages/kaomoji/README.md`
- Test: `packages/kaomoji/tests/test_bootstrap.py`, `packages/kaomoji/tests/test_build.py`

**Interfaces:**
- Consumes: `build.build_in_tools` and the routing from Task 2; `kaomoji.go` from Task 3.
- Produces: `build --dist <dir> --version <v>` writing `<dir>/kaomoji-{linux-armv6,linux-arm64,linux-amd64,darwin-arm64,darwin-amd64}`, `<dir>/kaomoji_<v>_{armhf,arm64,amd64}.deb` (printed on stdout), and `<dir>/{kaomoji,hero,wizard,visitor}` rendered from `bootstrap.sh`. Task 6 relies on the deb installing `/usr/bin/kaomoji`; Task 7 on the asset names.

- [ ] **Step 1: Write the bootstrap tests**

Create `packages/kaomoji/tests/test_bootstrap.py`:

```python
import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier0

PACKAGE = Path(__file__).resolve().parents[1]
TEMPLATE = PACKAGE / "bootstrap.sh"
FAKE_CURL = '#!/bin/sh\nout=""; url=""\nwhile [ $# -gt 0 ]; do case $1 in -o) out=$2; shift 2 ;; -*) shift ;; *) url=$1; shift ;; esac; done\nprintf "%s\\n" "$url" >> "$FAKE/curl.log"\ncp "$FAKE/release/${url##*/}" "$out"\n'
FAKE_UNAME = '#!/bin/sh\ncase $1 in -s) echo "$FAKE_OS" ;; -m) echo "$FAKE_ARCH" ;; esac\n'
FAKE_BINARY = '#!/bin/sh\nprintf "%s\\n" "$*" > "$FAKE/run.log"\n'


class Release:
    """A directory standing in for the GitHub release, a curl that copies from it, a uname that says what we want, and a binary that records its arguments."""

    def __init__(self, directory: Path):
        self.dir = directory
        self.bin, self.assets, self.cache = directory / "bin", directory / "release", directory / "cache"
        self.bin.mkdir()
        self.assets.mkdir()
        self.binary = self.assets / "kaomoji-linux-arm64"
        for path, text in [(self.binary, FAKE_BINARY), (self.bin / "curl", FAKE_CURL), (self.bin / "uname", FAKE_UNAME)]:
            path.write_text(text)
            path.chmod(0o755)

    def script(self, version: str = "2.1.0~rc.1", character: str = "hero", sha: str | None = None) -> Path:
        """The template rendered as the build renders it, with the hash of the fake binary unless given."""
        sha = sha or hashlib.sha256(self.binary.read_bytes()).hexdigest()
        name = character or "kaomoji"
        text = TEMPLATE.read_text().replace("@VERSION@", version).replace("@NAME@", name).replace("@CHARACTER@", character).replace("@SHA256_LINUX_ARM64@", sha)
        path = self.dir / name
        path.write_text(text)
        return path

    def run(self, script: Path, *args: str, os_: str = "Linux", arch: str = "aarch64") -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "XDG_CACHE_HOME": str(self.cache), "FAKE": str(self.dir), "FAKE_OS": os_, "FAKE_ARCH": arch}
        return subprocess.run(["sh", str(script), *args], capture_output=True, text=True, env=env)

    def fetched(self) -> list[str]:
        log = self.dir / "curl.log"
        return log.read_text().splitlines() if log.exists() else []

    def ran(self) -> str:
        return (self.dir / "run.log").read_text().strip()


@pytest.fixture
def release(tmp_path):
    return Release(tmp_path)


class TestBootstrap:
    def test_fetches_the_binary_of_its_release_for_this_machine_and_runs_its_character_with_the_arguments(self, release):
        result = release.run(release.script(), "--animate", "--exit")

        assert result.returncode == 0, result.stderr
        assert release.fetched() == ["https://github.com/bkahlert/pihero/releases/download/v2.1.0-rc.1/kaomoji-linux-arm64"]
        assert release.ran() == "hero --animate --exit"
        cached = release.cache / "kaomoji" / "2.1.0~rc.1" / "kaomoji"
        assert cached.exists() and cached.stat().st_mode & stat.S_IXUSR

    def test_runs_from_the_cache_the_second_time(self, release):
        script = release.script()

        release.run(script)
        release.run(script, "--loops", "1")

        assert len(release.fetched()) == 1
        assert release.ran() == "hero --loops 1"

    def test_without_a_character_passes_the_arguments_through(self, release):
        result = release.run(release.script(character=""), "wizard", "--mood", "happy")

        assert result.returncode == 0, result.stderr
        assert release.ran() == "wizard --mood happy"

    def test_maps_a_full_release_version_to_its_tag(self, release):
        release.run(release.script(version="2.1.0"))

        assert release.fetched() == ["https://github.com/bkahlert/pihero/releases/download/v2.1.0/kaomoji-linux-arm64"]

    @pytest.mark.parametrize(
        ("os_", "arch", "asset"),
        [("Darwin", "arm64", "kaomoji-darwin-arm64"), ("Darwin", "x86_64", "kaomoji-darwin-amd64"), ("Linux", "x86_64", "kaomoji-linux-amd64"), ("Linux", "armv7l", "kaomoji-linux-armv6"), ("Linux", "armv6l", "kaomoji-linux-armv6")],
    )
    def test_picks_the_asset_by_os_and_architecture(self, release, os_, arch, asset):
        (release.assets / asset).write_bytes(release.binary.read_bytes())

        release.run(release.script(), os_=os_, arch=arch)

        assert release.fetched()[0].endswith("/" + asset)

    def test_refuses_a_machine_without_a_binary(self, release):
        result = release.run(release.script(), arch="mips")

        assert result.returncode == 1
        assert result.stderr == "kaomoji: no binary for Linux mips\n"
        assert release.fetched() == []

    def test_refuses_a_download_whose_hash_does_not_match_and_leaves_no_file(self, release):
        result = release.run(release.script(sha="0" * 64))

        assert result.returncode == 1
        assert result.stderr == "kaomoji: checksum mismatch for kaomoji-linux-arm64\n"
        assert list((release.cache / "kaomoji" / "2.1.0~rc.1").iterdir()) == []

    def test_runs_nothing_when_cut_short(self, release):
        script = release.script()
        lines = script.read_text().splitlines(keepends=True)
        script.write_text("".join(lines[: len(lines) // 2]))  # a download that ended halfway through

        result = release.run(script)

        assert release.fetched() == [] and not (release.dir / "run.log").exists()
        assert result.returncode in (0, 2)  # sh reads the truncated text, finds no call, or chokes on a cut construct
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/kaomoji/tests/test_bootstrap.py -q`
Expected: FAIL, `bootstrap.sh` does not exist.

- [ ] **Step 3: Write the bootstrap template**

Create `packages/kaomoji/bootstrap.sh`:

```sh
#!/bin/sh
# Purpose: Run kaomoji @VERSION@ without installing it: fetches the binary for this machine once, then runs it.
# Usage:   curl -fsSL https://github.com/bkahlert/pihero/releases/latest/download/@NAME@ | sh -s -- [<argument>...]
#
# Published with every release as kaomoji, hero, wizard, and visitor; the last three run that character.
# The binary for this machine's OS and architecture is fetched from the release this script belongs to
# into ${XDG_CACHE_HOME:-~/.cache}/kaomoji/<version>/, checked against the hash baked in here, and run
# with the arguments. Needs curl, and sha256sum or shasum. Everything is inside one function called on
# the last line, so a download cut short runs nothing.

set -eu

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

main() {
    version='@VERSION@'
    character='@CHARACTER@'
    repo='https://github.com/bkahlert/pihero'
    hashes='
kaomoji-linux-armv6 @SHA256_LINUX_ARMV6@
kaomoji-linux-arm64 @SHA256_LINUX_ARM64@
kaomoji-linux-amd64 @SHA256_LINUX_AMD64@
kaomoji-darwin-arm64 @SHA256_DARWIN_ARM64@
kaomoji-darwin-amd64 @SHA256_DARWIN_AMD64@
'
    case $(uname -s) in
    Linux) os=linux ;;
    Darwin) os=darwin ;;
    *) os='' ;;
    esac
    # A 32-bit Raspberry Pi OS on a 64-bit kernel reports aarch64 and gets the arm64 binary, which runs there, being static.
    case $(uname -m) in
    x86_64 | amd64) arch=amd64 ;;
    aarch64 | arm64) arch=arm64 ;;
    armv6l | armv7l) arch=armv6 ;;
    *) arch='' ;;
    esac
    if [ -z "$os" ] || [ -z "$arch" ]; then
        printf 'kaomoji: no binary for %s %s\n' "$(uname -s)" "$(uname -m)" >&2
        exit 1
    fi
    asset="kaomoji-$os-$arch"
    expected=$(printf '%s\n' "$hashes" | awk -v asset="$asset" '$1 == asset { print $2 }')

    dir="${XDG_CACHE_HOME:-$HOME/.cache}/kaomoji/$version"
    bin="$dir/kaomoji"
    if [ ! -x "$bin" ]; then
        tag="v$(printf '%s' "$version" | tr '~' '-')" # the Debian version 2.1.0~rc.1 was tagged v2.1.0-rc.1
        url="$repo/releases/download/$tag/$asset"
        mkdir -p "$dir"
        tmp="$dir/.$asset.$$"
        if ! curl -fsSL -o "$tmp" "$url"; then
            rm -f "$tmp"
            printf 'kaomoji: download failed: %s\n' "$url" >&2
            exit 1
        fi
        if [ "$(sha256 "$tmp")" != "$expected" ]; then
            rm -f "$tmp"
            printf 'kaomoji: checksum mismatch for %s\n' "$asset" >&2
            exit 1
        fi
        chmod 755 "$tmp"
        mv "$tmp" "$bin"
    fi
    if [ -n "$character" ]; then
        exec "$bin" "$character" "$@"
    fi
    exec "$bin" "$@"
}

main "$@"
```

Run: `uv run pytest packages/kaomoji/tests/test_bootstrap.py -q && shellcheck -s sh packages/kaomoji/bootstrap.sh`
Expected: all PASS, shellcheck silent.

- [ ] **Step 4: Write the build tests**

Create `packages/kaomoji/tests/test_build.py`:

```python
import hashlib
import platform
import subprocess
from pathlib import Path

import pytest

from pihero_testkit import build, tools

pytestmark = pytest.mark.tier0

PACKAGE = Path(__file__).resolve().parents[1]
BINARIES = ["kaomoji-darwin-amd64", "kaomoji-darwin-arm64", "kaomoji-linux-amd64", "kaomoji-linux-arm64", "kaomoji-linux-armv6"]


@pytest.fixture(scope="module")
def built():
    """The build script run once for this module into dist/probe-kaomoji: the debs it printed and the directory."""
    dist = Path.cwd() / "dist" / "probe-kaomoji"
    try:
        yield build.build_in_tools(PACKAGE, "9.9.9", dist=dist), dist
    finally:
        subprocess.run(["rm", "-rf", str(dist)], check=True)


class TestDebs:
    def test_builds_one_deb_per_linux_architecture(self, built):
        debs, _ = built

        assert sorted(deb.name for deb in debs) == ["kaomoji_9.9.9_amd64.deb", "kaomoji_9.9.9_arm64.deb", "kaomoji_9.9.9_armhf.deb"]

    @pytest.mark.parametrize("arch", ["armhf", "arm64", "amd64"])
    def test_ships_the_binary_for_its_architecture_and_nothing_else(self, built, arch):
        _, dist = built
        deb = f"/work/{(dist / f'kaomoji_9.9.9_{arch}.deb').relative_to(Path.cwd())}"

        info = tools.run(["dpkg-deb", "--info", deb], capture=True).stdout
        contents = tools.run(["dpkg-deb", "--contents", deb], capture=True).stdout

        assert f" Architecture: {arch}" in info and " Version: 9.9.9" in info and " Section: admin" in info
        assert " Depends:" not in info
        files = [line.split()[-1] for line in contents.splitlines() if not line.split()[-1].endswith("/")]
        assert files == ["./usr/bin/kaomoji"]
        assert contents.splitlines()[-1].startswith("-rwxr-xr-x")


class TestBinaries:
    def test_builds_five_static_binaries(self, built):
        _, dist = built

        assert sorted(path.name for path in dist.glob("kaomoji-*")) == BINARIES
        assert (dist / "kaomoji-linux-armv6").read_bytes()[:5] == b"\x7fELF\x01"  # 32-bit ELF
        assert (dist / "kaomoji-linux-arm64").read_bytes()[:5] == b"\x7fELF\x02"

    def test_links_the_version_in(self, built):
        _, dist = built
        mine = dist / f"kaomoji-{platform.system().lower()}-{ {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'amd64'}[platform.machine()] }"

        result = subprocess.run([str(mine), "--version"], capture_output=True, text=True)

        assert result.stdout == "9.9.9\n"


class TestScripts:
    @pytest.mark.parametrize(("name", "character"), [("kaomoji", ""), ("hero", "hero"), ("wizard", "wizard"), ("visitor", "visitor")])
    def test_renders_the_bootstrap_with_the_version_the_character_and_the_hashes(self, built, name, character):
        _, dist = built
        script = (dist / name).read_text()

        assert "@VERSION@" not in script and "@NAME@" not in script and "@CHARACTER@" not in script and "@SHA256_" not in script
        assert f"version='9.9.9'" in script and f"character='{character}'" in script
        assert f"releases/latest/download/{name} |" in script
        for binary in BINARIES:
            assert f"{binary} {hashlib.sha256((dist / binary).read_bytes()).hexdigest()}" in script
        assert (dist / name).stat().st_mode & 0o111
```

Run: `uv run pytest packages/kaomoji/tests/test_build.py -q`
Expected: FAIL, the build script does not exist.

- [ ] **Step 5: Write the manifest and the build script, drop nfpm.yaml**

Create `packages/kaomoji/nfpm.yaml.in` (nfpm expands `${…}` from the environment the build sets; the name keeps the
testkit's manifest discovery and the architecture-all sweep off it):

```yaml
name: kaomoji
arch: ${ARCH}
platform: linux
version: ${VERSION}
section: admin
priority: optional
maintainer: Björn Kahlert <bkahlert@users.noreply.github.com>
description: |
  The Pi Hero cast: three animated kaomoji for the terminal.
  kaomoji hero, kaomoji wizard, and kaomoji visitor print one face each, static or animated, plain or colored, in every mood they have.
homepage: https://github.com/bkahlert/pihero
license: MIT
contents:
  - src: ${BINARY}
    dst: /usr/bin/kaomoji
    file_info:
      mode: 0755
```

Create `packages/kaomoji/build`, executable (`chmod 755`):

```bash
#!/usr/bin/env bash
# Purpose: Build kaomoji: five static binaries, three Debian packages, and the four bootstrap scripts.
# Usage:   build --dist <directory> --version <version>
#
# Runs in the tools image with the repository at /work and Go and nfpm on PATH. Cross-compiles kaomoji.go
# for Linux armv6 (every 32-bit Raspberry Pi), arm64, and amd64 and for macOS arm64 and amd64 into
# <directory>/kaomoji-<os>-<arch>, packs the Linux ones as kaomoji_<version>_{armhf,arm64,amd64}.deb from
# nfpm.yaml.in, and renders bootstrap.sh as kaomoji, hero, wizard, and visitor with the version, the
# character, and the binaries' hashes filled in. Prints the paths of the .deb files on stdout, nothing else.
#
# Options:
#   --dist <directory>   Where everything goes.
#   --version <version>  The Debian version to build, as the testkit derives it from git.
#   -h, --help           Show this help.

set -euo pipefail

usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"; }
die() { printf '%s: %s\nSee '\''%s --help'\''\n' "${0##*/}" "$1" "${0##*/}" >&2; exit 2; }

dist='' version=''
while (($#)); do
    case $1 in
    -h | --help) usage; exit 0 ;;
    --dist) dist=${2?--dist: missing value}; shift 2 ;;
    --dist=*) dist=${1#*=}; shift ;;
    --version) version=${2?--version: missing value}; shift 2 ;;
    --version=*) version=${1#*=}; shift ;;
    -?*) die "unknown option: $1" ;;
    *) die "unexpected argument: $1" ;;
    esac
done
[[ -n $dist && -n $version ]] || { usage >&2; exit 2; }

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$dist"
export CGO_ENABLED=0 GOFLAGS=-trimpath

# Builds one static binary: <os> <arch> [<arm version>]
binary() {
    GOOS=$1 GOARCH=$2 GOARM=${3:-} go build -ldflags "-s -w -X main.version=$version" -o "$dist/kaomoji-$1-$2${3:+v$3}" "$here/kaomoji.go" >&2
}
binary linux arm 6
binary linux arm64
binary linux amd64
binary darwin arm64
binary darwin amd64

# One deb per Linux binary: nfpm's GOARCH-style arch, Debian's name for it, and the binary.
for spec in 'arm6 armhf kaomoji-linux-armv6' 'arm64 arm64 kaomoji-linux-arm64' 'amd64 amd64 kaomoji-linux-amd64'; do
    read -r arch debarch name <<<"$spec"
    deb="$dist/kaomoji_${version}_${debarch}.deb"
    ARCH=$arch BINARY="$dist/$name" VERSION=$version nfpm package -f "$here/nfpm.yaml.in" -p deb -t "$deb" >&2
    printf '%s\n' "$deb"
done

sha() { sha256sum "$dist/$1" | cut -d' ' -f1; }
# Renders the bootstrap script: <name> <character>
render() {
    sed -e "s|@VERSION@|$version|g" -e "s|@NAME@|$1|g" -e "s|@CHARACTER@|$2|g" \
        -e "s|@SHA256_LINUX_ARMV6@|$(sha kaomoji-linux-armv6)|" -e "s|@SHA256_LINUX_ARM64@|$(sha kaomoji-linux-arm64)|" \
        -e "s|@SHA256_LINUX_AMD64@|$(sha kaomoji-linux-amd64)|" -e "s|@SHA256_DARWIN_ARM64@|$(sha kaomoji-darwin-arm64)|" \
        -e "s|@SHA256_DARWIN_AMD64@|$(sha kaomoji-darwin-amd64)|" "$here/bootstrap.sh" >"$dist/$1"
    chmod 755 "$dist/$1"
}
render kaomoji ''
render hero hero
render wizard wizard
render visitor visitor
```

Then:

```bash
chmod 755 packages/kaomoji/build
git rm -q packages/kaomoji/nfpm.yaml
uv run pytest packages/kaomoji/tests/test_build.py -q
shellcheck packages/kaomoji/build
make build && ls dist/kaomoji*
```

Expected: the tests PASS (the first run compiles five binaries in the tools image, about a minute; later runs seconds),
shellcheck silent, `make build` prints three `kaomoji_<version>_*.deb` among the others and `dist/` holds the five
binaries and the four scripts. `uv run pytest testkit/tests/test_static.py -q` passes too: the manifest sweep no longer
sees a kaomoji manifest, shellcheck covers `build` and `bootstrap.sh`.

- [ ] **Step 6: Rewrite the package README**

Replace `packages/kaomoji/README.md` with:

````markdown
# Kaomoji

The Pi Hero cast: three animated faces for the terminal, one Go program, [kaomoji.go](kaomoji.go), standard library
only. `kaomoji hero`, `kaomoji wizard`, and `kaomoji visitor` print one kaomoji each, static unless animated, colored on
a terminal; `kaomoji <character> --help` lists its moods and options. How the engine paints and paces, how the package is
built, and what was measured on a Raspberry Pi 1 is in [docs/design.md](../../docs/design.md#kaomoji). The tests in
[tests](tests) run in tier 0.

```shell
curl -fsSL https://github.com/bkahlert/pihero/releases/latest/download/hero | bash -s -- --animate --exit
```

That line fetches the binary for this machine once, into `~/.cache/kaomoji/`, checks it against the hash in the script,
and runs it; `wizard`, `visitor`, and `kaomoji` are published the same way, the last taking the character as its first
argument. Linux and macOS, arm64 and amd64, and every 32-bit Raspberry Pi. `apt install kaomoji` from the Pi Hero
repository puts `/usr/bin/kaomoji` on a Pi; `pihero` depends on it for its MOTD. In a checkout, `go run kaomoji.go hero`
needs nothing but Go, and `make .build/kaomoji` builds the binary through the tools image without a Go of your own.

| Character          | Face                                                                                                           | Animation                              |
| ------------------ | -------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `kaomoji hero`     | The Pi Hero, `─=≡▰▩▩[ 蓬•ｏ•]⊐`: flies in from the left, hovers with a flickering tail, flies out through the right edge of the terminal | ![hero](assets/hero.gif)               |
| `kaomoji wizard`   | The Netmon wizard, `(つ◕౪◕)つ─｡ﾟ․☆･*ﾟ`: slides in, conjures the magic particle by particle, slides out         | ![wizard](assets/wizard.gif)           |
| `kaomoji visitor`  | The Busy Screen visitor, `┴┬┴┤´Ｏ´)ﾉ`: peeks out from behind a wall, waves and blinks, ducks back            | ![visitor](assets/visitor.gif)         |

```shell
kaomoji hero                                # one static kaomoji
kaomoji hero --mood happy --animate --exit  # flies in, hovers until Ctrl-C, then flies out
kaomoji wizard --loops 3 --exit             # entrance, three hover cycles, exit
kaomoji visitor --preview                   # every mood and style in a grid, animated
```

## Preview grids

One row per mood, one column per style: static and animated, each plain and colored.

![hero preview](assets/hero-grid.gif)

![wizard preview](assets/wizard-grid.gif)

![visitor preview](assets/visitor-grid.gif)

## Building

[build](build) runs in the testkit's tools image, which has Go and nfpm: it cross-compiles the five binaries, packs the
Linux ones as `kaomoji_<version>_{armhf,arm64,amd64}.deb` from [nfpm.yaml.in](nfpm.yaml.in), and renders
[bootstrap.sh](bootstrap.sh) under the four names with the version, the character, and the binaries' hashes baked in.
`make build` at the repository root runs it along with every other package; the release workflow attaches everything it
produces to the GitHub release.

## Rendering the GIFs

[kaomoji-gif](kaomoji-gif) records a command with [asciinema](https://asciinema.org) and renders the recording with
[agg](https://github.com/asciinema/agg). The [Makefile](Makefile) holds the settings of the GIFs on this page; in this
directory:

```shell
brew install asciinema agg
make                                                                      # every GIF whose program or renderer changed
./kaomoji-gif -- ./.build/kaomoji hero --animate --no-entrance --loops 1   # hero.gif: hovering once, a seamless loop
./kaomoji-gif --help                                                      # font, size, padding, hold, theme
```

An endless animation never finishes recording, so give the command `--loops`.

The badge in the title of the repository's README, [assets/hero-badge.gif](../../assets/hero-badge.gif), is a one-off: a
recording of the hovering hero cut to 40 px with ffmpeg, grey and rounded like the badges next to it. It is kept as a file
with the logo, not rendered here, so that this renderer needs nothing but asciinema and agg.
````

- [ ] **Step 7: Commit**

```bash
git add packages/kaomoji/build packages/kaomoji/nfpm.yaml.in packages/kaomoji/bootstrap.sh packages/kaomoji/README.md packages/kaomoji/tests/test_bootstrap.py packages/kaomoji/tests/test_build.py
git commit -m "feat(kaomoji): ship one binary per architecture and a curl line

The package builds itself in the tools image: five static binaries, a deb
for armhf, arm64, and amd64 holding /usr/bin/kaomoji, and a bootstrap
script published as kaomoji, hero, wizard, and visitor that fetches the
binary of its own release once and runs it.

BREAKING CHANGE: hero, wizard, and visitor are kaomoji hero, kaomoji
wizard, and kaomoji visitor; the package no longer installs the three
commands nor /usr/lib/kaomoji/kaomoji.bash."
```

---

### Task 5: Retire the bash engine, record the GIFs from the binary

**Files:**
- Delete: `packages/kaomoji/kaomoji.bash`, `packages/kaomoji/hero`, `packages/kaomoji/wizard`, `packages/kaomoji/visitor`
- Modify: `packages/kaomoji/kaomoji-gif`, `packages/kaomoji/Makefile`
- Test: `packages/kaomoji/tests/test_kaomoji_gif.py`
- Regenerate: `packages/kaomoji/assets/*.gif`

**Interfaces:**
- Consumes: `packages/kaomoji/.build/kaomoji` from Task 3's fixture; `uv run python -m pihero_testkit.tools -- …` from Task 1; the deb from Task 4 no longer ships the scripts, so deleting them changes nothing a device sees.
- Produces: `kaomoji-gif` sources nothing and writes the same sequences the binary does; `make -C packages/kaomoji` builds `.build/kaomoji` through the tools image and records from it.

- [ ] **Step 1: Point the GIF tests at the binary**

In `packages/kaomoji/tests/test_kaomoji_gif.py`:

```python
pytestmark = [pytest.mark.tier0, pytest.mark.usefixtures("binary")]

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "kaomoji-gif"
BINARY = str(PACKAGE / ".build" / "kaomoji")
HERO, WIZARD = [BINARY, "hero"], [BINARY, "wizard"]
ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
CIVIS, CNORM = "\x1b[?25l", "\x1b[?25h"
```

and every `run(..., "--", HERO, ...)` becomes `run(..., "--", *HERO, ...)`, every `WIZARD` likewise (`grep -n "HERO\|WIZARD" packages/kaomoji/tests/test_kaomoji_gif.py` lists the seven call sites). In `test_passes_the_look_on_to_agg` the expected line stays `f"{gif}: 1 event on 18x3 cells\n"`.

Add one test to `TestCast`:

```python
    def test_names_the_gif_after_the_character_when_the_command_is_the_binary(self, tmp_path, fake_agg, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = run("--", *HERO, "--mood", "happy", path=fake_agg.directory)

        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith(f"hero.gif: ")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/kaomoji/tests/test_kaomoji_gif.py -q`
Expected: `TestCast` fails on `CNORM`/`CIVIS` expectations and the new name test; the engine the script sources still exists, so nothing else breaks yet.

- [ ] **Step 3: Make kaomoji-gif self-contained**

In `packages/kaomoji/kaomoji-gif` replace the two lines

```bash
# shellcheck source=kaomoji.bash
. "$(dirname "${BASH_SOURCE[0]}")/kaomoji.bash" # usage, die and kaomoji_text_width
```

with

```bash
# Bash slices strings by character only in a UTF-8 locale, and kaomoji are made of multibyte ones.
case ${LC_ALL:-${LC_CTYPE:-${LANG:-}}} in
*[Uu][Tt][Ff]-8* | *[Uu][Tt][Ff]8*) ;;
*) export LC_ALL=C.UTF-8 ;;
esac

usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; }
die() { printf '%s: %s\nSee '\''%s --help'\''\n' "${0##*/}" "$1" "${0##*/}" >&2; exit 2; }

# The sequences the cast writes, see kaomoji.go: hide and show the cursor, cursor up one line.
readonly CIVIS=$'\e[?25l' CNORM=$'\e[?25h' CUU1=$'\e[A'

# Sets REPLY to the cells the text takes: two for East Asian wide and fullwidth characters, one
# for everything else, as kaomoji.go counts them.
text_width() {
    local text=$1 ch
    local -i i cp
    REPLY=0
    for ((i = 0; i < ${#text}; i++)); do
        ch=${text:i:1}
        printf -v cp '%d' "'$ch"
        if ((cp >= 0x1100 && (cp <= 0x115F ||
            (cp >= 0x2E80 && cp <= 0xA4CF && cp != 0x303F) || (cp >= 0xAC00 && cp <= 0xD7A3) ||
            (cp >= 0xF900 && cp <= 0xFAFF) || (cp >= 0xFE30 && cp <= 0xFE4F) ||
            (cp >= 0xFF00 && cp <= 0xFF60) || (cp >= 0xFFE0 && cp <= 0xFFE6) ||
            (cp >= 0x20000 && cp <= 0x3FFFD)))); then
            REPLY+=2
        else
            REPLY+=1
        fi
    done
}
```

Then, in `trim()`, replace `kaomoji_tput cnorm` and `cnorm=$(json_escape "${KAOMOJI_CAP[cnorm]}")` with the one line `cnorm=$(json_escape "$CNORM")`; in `measure()`, replace `kaomoji_tput cuu1` and `cuu1=$(json_escape "${KAOMOJI_CAP[cuu1]}")` with `cuu1=$(json_escape "$CUU1")` and `kaomoji_text_width "$line"` with `text_width "$line"`; in `write_cast()`, replace `kaomoji_tput civis` and `civis=$(json_escape "${KAOMOJI_CAP[civis]}")` with `civis=$(json_escape "$CIVIS")`. `grep -n "kaomoji_\|KAOMOJI_CAP" packages/kaomoji/kaomoji-gif` must then list only the `KAOMOJI_COLUMNS=0` on the asciinema line.

In `kaomoji_gif()`, replace `[ -n "$output" ] || output=${command[0]##*/}.gif` with:

```bash
    if [ -z "$output" ]; then
        # Named after the command, or after the character when the command is the kaomoji binary.
        output=${command[0]##*/}
        if [ "$output" = kaomoji ] && ((${#command[@]} > 1)); then output=${command[1]}; fi
        output+=.gif
    fi
```

In the header, change the Purpose line to end in `a kaomoji in particular.`, the option `--output` default to `(default: <command>.gif, named after the command's file, or after the character when the command is kaomoji)`, and the five example lines to use `./.build/kaomoji hero …` and `./.build/kaomoji wizard …` in place of `./hero` and `./wizard`.

- [ ] **Step 4: Rewrite the Makefile**

Replace `packages/kaomoji/Makefile` with:

```make
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
```

- [ ] **Step 5: Delete the scripts and run the tests**

The bash implementation stays reachable at the annotated tag `kaomoji-bash`, which points at its last commit,
`8113d23`; the tag does not match the release workflow's `v*` nor the version's `git describe --match v*`.

```bash
git rm -q packages/kaomoji/kaomoji.bash packages/kaomoji/hero packages/kaomoji/wizard packages/kaomoji/visitor
uv run pytest packages/kaomoji/tests -q
shellcheck packages/kaomoji/kaomoji-gif
```

Expected: all PASS, shellcheck silent; `make build` still builds the three debs, which never contained the scripts.

- [ ] **Step 6: Regenerate the GIFs**

Run: `make -C packages/kaomoji`
Expected: six GIFs, the boxes as before: hero 18x3 cells, hero grid 77x13, wizard 19x3, wizard grid 81x13, visitor
13x3, visitor grid 69x13 (the script prints `<file>: <n> events on <w>x<h> cells`). Open one to see the motion.

- [ ] **Step 7: Commit**

```bash
git add packages/kaomoji/kaomoji-gif packages/kaomoji/Makefile packages/kaomoji/tests/test_kaomoji_gif.py packages/kaomoji/assets
git commit -m "refactor(kaomoji): retire the bash engine and record the GIFs from the binary"
```

---

### Task 6: The MOTD and the installed tests follow the binary

**Files:**
- Modify: `packages/pihero/root/usr/lib/pihero/motd:69`, `packages/pihero/tests/test_motd.py:92-104`
- Rewrite: `packages/kaomoji/tests/test_installed.py`
- Modify: `docs/app-conventions.md:34-35`

**Interfaces:**
- Consumes: the deb from Task 4 installing `/usr/bin/kaomoji`; `kaomoji hero --mood <mood> --no-color` from Task 3.
- Produces: the MOTD runs `kaomoji hero --mood <mood> --no-color`; tiers 1, 2, and ssh prove the installed binary.

- [ ] **Step 1: Change the MOTD tests**

In `packages/pihero/tests/test_motd.py`, `TestMain`:

```python
    def test_renders_the_banner_through_kaomoji_hero_in_the_mood_of_the_state(self, tmp_path, monkeypatch, capsys):
        stub(tmp_path, "systemctl", 'printf "x.service loaded failed failed X\\n"')
        stub(tmp_path, "kaomoji", 'printf "%s\\n" "$*" >> "$0.log"; printf "HERO %s\\n" "$3"')
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        monkeypatch.setattr(motd, "RUN", tmp_path)

        motd.main()

        out = capsys.readouterr().out
        assert out.startswith("\nHERO sad\n\n")
        assert (tmp_path / "kaomoji.log").read_text() == "hero --mood sad --no-color\n"

    def test_asks_for_the_puzzled_hero_on_a_pending_reboot(self, tmp_path, monkeypatch, capsys):
        stub(tmp_path, "systemctl", "")
        stub(tmp_path, "kaomoji", 'printf "HERO %s\\n" "$3"')
        (tmp_path / "reboot-required").write_text("*** System restart required ***\n")
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        monkeypatch.setattr(motd, "RUN", tmp_path)

        motd.main()
```

The rest of the second test stays as it is.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/pihero/tests/test_motd.py -q -k TestMain`
Expected: FAIL, the MOTD still calls `hero`, so the `kaomoji` stub never runs.

- [ ] **Step 3: Change the MOTD**

In `packages/pihero/root/usr/lib/pihero/motd` line 69:

```python
    banner = _output(["kaomoji", "hero", "--mood", mood(failed, reboot[0]), "--no-color"])
```

Run: `uv run pytest packages/pihero/tests/test_motd.py -q`
Expected: all PASS.

- [ ] **Step 4: Rewrite the installed tests of the cast**

Replace `packages/kaomoji/tests/test_installed.py` with:

```python
import pytest

pytestmark = pytest.mark.installed


class TestPackage:
    def test_is_installed_at_the_built_version(self, host, version):
        package = host.package("kaomoji")

        assert package.is_installed
        assert package.version == version

    def test_is_built_for_the_hosts_architecture(self, host):
        architecture = host.check_output("dpkg-query -W -f='${Architecture}' kaomoji")

        assert architecture == host.check_output("dpkg --print-architecture")

    def test_ships_the_binary_as_a_command_owned_by_root(self, host):
        file = host.file("/usr/bin/kaomoji")

        assert file.exists
        assert file.mode == 0o755
        assert file.user == "root"

    @pytest.mark.parametrize("path", ["/usr/bin/hero", "/usr/bin/wizard", "/usr/bin/visitor", "/usr/lib/kaomoji"])
    def test_ships_none_of_the_scripts_it_used_to(self, host, path):
        assert not host.file(path).exists


class TestFaces:
    @pytest.mark.parametrize(
        ("command", "text"),
        [
            ("kaomoji hero --mood happy --no-color", "─=≡▰▩▩[✿＾ｖ＾]⊐"),
            ("kaomoji wizard --no-color", "(つ◕౪◕)つ─｡ﾟ․☆･*ﾟ"),
            ("kaomoji visitor --no-color", "┴┬┴┤´Ｏ´)ﾉ"),
        ],
    )
    def test_render_from_path(self, host, command, text):
        assert host.check_output(command) == text

    def test_prints_the_built_version(self, host, version):
        assert host.check_output("kaomoji --version") == version

    def test_leaves_through_its_own_edge_without_a_terminal(self, host):
        frames = host.check_output("KAOMOJI_COLUMNS=0 kaomoji hero --no-color --no-entrance --loops 1 --exit --frame-ms 0").split("\r")

        assert len(frames) == 1 + 12 + 16  # the hidden cursor, a hover cycle, the exit over the hero's own width


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_leaves_nothing_behind_and_reinstall_restores_the_system(self, host, target):
        target.purge(["kaomoji"])

        assert not host.file("/usr/bin/kaomoji").exists

        target.reinstall()

        assert host.package("kaomoji").is_installed
        assert host.package("pihero").is_installed
```

- [ ] **Step 5: Update the app conventions**

In `docs/app-conventions.md`, replace the bullet beginning `- An app that shows a face runs` with:

```markdown
- An app that shows a face runs `kaomoji hero`, `kaomoji wizard`, or `kaomoji visitor` from the `kaomoji` package, which
  `pihero` brings along, and ships no copy of its own.
```

Handed over to the choam.de repository, not done here: if shishakli's `/usr/local/lib/hero-lcd/run` runs
`/usr/bin/hero` by now, it runs `/usr/bin/kaomoji hero --mood neutral --animate --color` from the release that carries
this change on.

- [ ] **Step 6: Run tier 1 on both platforms**

```bash
make test-tier1
make test-tier1 PLATFORM=linux/arm/v7
```

Expected: both green, about a minute each plus the image builds; `packages/kaomoji/tests/test_installed.py` and
`packages/pihero/tests/test_installed.py`'s MOTD tests among them. If `test_is_built_for_the_hosts_architecture` fails
on arm/v7, the deb's `Architecture:` is not `armhf`: check nfpm's mapping of `arch: arm6` in Task 4's manifest.

- [ ] **Step 7: Commit, two changes**

```bash
git add packages/kaomoji/tests/test_installed.py
git commit -m "test(kaomoji): prove /usr/bin/kaomoji on an installed system"
git add packages/pihero/root/usr/lib/pihero/motd packages/pihero/tests/test_motd.py docs/app-conventions.md
git commit -m "fix(pihero): run the MOTD banner through kaomoji hero"
```

---

### Task 7: The release attaches the binaries and the scripts, and publishes once complete

**Files:**
- Modify: `.github/workflows/release.yml:54-61`

**Interfaces:**
- Consumes: the files `make build` leaves in `dist/` from Task 4: `kaomoji-*`, `kaomoji`, `hero`, `wizard`, `visitor`, `*.deb`.
- Produces: a GitHub release whose `releases/latest/download/<name>` serves the scripts and `releases/download/<tag>/kaomoji-<os>-<arch>` the binaries.

- [ ] **Step 1: Change the publish step**

Replace the step `Publish the GitHub release` in `.github/workflows/release.yml` with:

```yaml
      - name: Publish the GitHub release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          prerelease=()
          case "$GITHUB_REF_NAME" in *-*) prerelease=(--prerelease) ;; esac
          # Created as a draft and published once every asset is up: releases/latest/download/hero must
          # never serve a bootstrap script whose binary is not there yet.
          gh release create "$GITHUB_REF_NAME" --draft --verify-tag --generate-notes "${prerelease[@]}" \
            dist/*.deb dist/kaomoji-* dist/kaomoji dist/hero dist/wizard dist/visitor
          gh release edit "$GITHUB_REF_NAME" --draft=false
```

- [ ] **Step 2: Check it the way the runner will**

```bash
make build && ls dist/*.deb dist/kaomoji-* dist/kaomoji dist/hero dist/wizard dist/visitor
gh release create --help | grep -E -- '--draft|--verify-tag|--generate-notes'
gh release edit --help | grep -- '--draft'
```

Expected: every glob of the workflow lists files; the three `create` flags and `edit --draft` exist in the installed `gh`.
There is no local run of the workflow; the first `v*` tag after this change is its test, and the QA line at the end of
this plan runs the curl line against it.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): attach the kaomoji binaries and curl-line scripts, publish once complete"
```

---

### Task 8: The documentation, and the measurements on the Pi 1

**Files:**
- Modify: `docs/design.md` (the Decisions table, the layout block, the "Paths" and "Manifest" bullets, the whole `## kaomoji` section)
- Modify: `docs/testing.md` (the tier table, the "Tools container" section, the "Release" section)
- Modify: `README.md` (the packages table)

**Interfaces:**
- Consumes: everything built so far; `busy-screen.local`, the Pi 1, reachable over SSH, for the measurements.

- [ ] **Step 1: Deploy to the Pi 1 and measure**

```bash
make deploy TARGET=busy-screen.local
ssh busy-screen.local 'time kaomoji hero --no-color >/dev/null'
ssh busy-screen.local 'python3 - <<"EOF"
import os, subprocess, time

def measure(args, cols):
    env = {**os.environ, "COLUMNS": str(cols), "TERM": "xterm-256color"}
    started = time.monotonic()
    proc = subprocess.Popen(["kaomoji", *args], stdout=subprocess.PIPE, env=env, bufsize=0)
    marks = []
    while chunk := proc.stdout.read(1):
        if chunk == b"\r":
            marks.append(time.monotonic())
    proc.wait()
    gaps = [b - a for a, b in zip(marks, marks[1:])]
    return f"{len(marks)} frames, first after {(marks[0] - started) * 1000:.0f} ms, all in {(marks[-1] - marks[0]) * 1000:.0f} ms, longest gap {max(gaps) * 1000:.0f} ms"

for cols in (80, 200):
    print(cols, "plain:", measure(["hero", "--no-color", "--loops", "1", "--exit"], cols))
    print(cols, "color:", measure(["hero", "--color", "--loops", "1", "--exit"], cols))
EOF'
```

Expected: the static hero well under 100 ms; the first frame within tens of milliseconds; `--loops 1 --exit` close to
its nominal 2200 ms (16 entrance, 12 hover, and 16 exit frame times of 50 ms) on both widths, the longest gap near the
slowest entrance interval of 88 ms. Write the numbers down; they go into the Performance paragraph below.

- [ ] **Step 2: Rewrite the `kaomoji` section of design.md**

Replace everything from the line `## \`kaomoji\`` up to, not including, `## Planned packages` with the following,
the `N`s in the Performance paragraph replaced by the measurements of Step 1:

````markdown
## `kaomoji`

The Pi Hero cast, shipped as the package `kaomoji` from [packages/kaomoji](../packages/kaomoji): one Go program,
[kaomoji.go](../packages/kaomoji/kaomoji.go), standard library only, built into `/usr/bin/kaomoji` for armhf, arm64, and
amd64; `kaomoji hero`, `kaomoji wizard`, and `kaomoji visitor` print one face each. It depends on nothing; `pihero` depends
on it for its MOTD. Its tests run in tier 0 against the binary built for the Mac through the tools image, gofmt and go vet
pass over the source as shellcheck does over the scripts, and tier 1 installs the deb of the container's architecture and
runs the faces from `PATH`. The engine drives the terminal with ANSI sequences alone, no tput and no terminfo: hide and
show the cursor, erase to the end of the line, cursor up for the grid, SGR for colors. A sprite is a slice of graphemes,
each with its text, its cells from a small East Asian width table, and its style; a style is a basic color, which follows
the terminal's theme and is what the wizard and the visitor wear, or a hex color with the 256-color index that stands in
for it, the hero's palette, painted as truecolor when `COLORTERM` says so, by index on a `TERM` with `256color`, and
dropped elsewhere.

An animation runs on a clock. A character gives a timeline for a mood and a line width: the steps of its entrance, of one
hover cycle, of its exit, and the frame times the exit lasts. The frame of a step is a pure function, hover steps map
onto the first cycle, and the frame of a step is due when the one before has stayed its time, counted from when that one
was due; a late frame goes out at once and the schedule moves with it, so frames are never skipped and the output stays
deterministic, which the tests count frame by frame at `--frame-ms 0`. The hover shows a frame per frame time; the
entrance and the exit spread their duration under constant acceleration, the fastest interval a quarter of the mean and
the slowest one and three quarters, the entrance slowing down into the hover and the exit speeding up out of it. The hero
enters and leaves one cell per step, its exit crossing the whole line in sixteen frame times however wide it is, so a
200-column terminal sees 200 frames one to eight milliseconds apart where a 40-column one sees 40. `hero` flies in from
the left, hovers, and flies out through the terminal's right edge; `wizard` slides in, conjures its magic particle by
particle, runs the colors along it, and slides out to the left; `visitor` peeks out from behind a wall that slides in,
waves and blinks, and ducks back before the wall slides out. Every call prints one kaomoji: the first mood, static,
colored on a terminal; `--animate` or any animation option animates it, and `--exit` on an endless animation plays the
exit when the program is stopped by SIGINT or SIGTERM, a second signal quitting at once, so an app can show a face until
it is done and let it leave. Go finishes a write a signal interrupted, so a frame is never torn. Only `--help`,
`--version`, and `--preview`, the grid, print anything else. A terminal moves text by whole cells and redraws at its own
rate, so beyond about sixty frames a second the clock buys timing accuracy, not visible motion.

The package builds itself: [build](../packages/kaomoji/build) runs in the tools image, which carries Debian's Go next to
nfpm, cross-compiles five static binaries, Linux armv6 for every 32-bit Pi and Linux and macOS arm64 and amd64, packs the
Linux ones from [nfpm.yaml.in](../packages/kaomoji/nfpm.yaml.in) with the architecture substituted, and renders
[bootstrap.sh](../packages/kaomoji/bootstrap.sh) as `kaomoji`, `hero`, `wizard`, and `visitor` with the version, the
character, and the binaries' hashes baked in. The release attaches all of it, created as a draft and published once every
asset is up, so `curl -fsSL https://github.com/bkahlert/pihero/releases/latest/download/hero | bash -s -- --animate`
fetches the binary of that script's own release once, into `~/.cache/kaomoji/<version>/`, checks the hash, and runs it: no
API call, no redirect service, no hosting, and script and binary cannot mismatch. The Debian version `2.1.0~rc.1` was
tagged `v2.1.0-rc.1`, which the script derives; a build between tags has no release and its script no working URL, which
is accepted since only the release workflow publishes scripts. The language is the exception to the on-device-logic rule,
recorded in the Decisions table: a terminal animation needs an instant start and a binary without a runtime, which neither
bash nor Python gives, and Go reaches the Pi 1 and a Mac from one build command.

[kaomoji-gif](../packages/kaomoji/kaomoji-gif) records the command given after `--` with asciinema on a virtual 256-color
terminal and renders the recording with agg: the terminal sized to the picture, the final newline and the cursor trimmed,
and the last frame held for the frames it repeats plus one more, since agg merges identical frames. It stays a bash script
beside the cast, self-contained and Mac-side, since asciinema and agg have no place on a Pi; the pictures are GIFs, not
animated SVG, because SVG text renders with the viewer's fonts and the faces depend on glyphs few machines share.
[packages/kaomoji/README.md](../packages/kaomoji/README.md) shows them, and `make -C packages/kaomoji` builds the Mac
binary through the tools image and re-renders the GIFs whose program or renderer changed; the badge in the repository's
README is a one-off cut with ffmpeg, kept with the logo (2026-09-30). The bash implementation this replaced stays
reachable at the tag `kaomoji-bash`.

**Performance.** The target is a Raspberry Pi 1 at 50 ms per frame. Measured on `busy-screen.local` (Pi 1, the kiosk
browser taking half the CPU) with the binary of this change: a static plain hero in N ms, the first frame of an animation
after N ms plain and N ms colored, the whole of `--loops 1 --exit` on 80 columns in N ms against 2200 ms nominal and on
200 columns in N ms, the longest gap between frames N ms. Before, in bash, the first frame showed after 0.8–1.2 s plain
and 1.6–2 s colored, a cached frame cost 9 ms and a fresh one 25–70 ms, the engine never forked while animating and
batched its `tput` calls to get there, and the grid's startup took 3.5–8 s (2026-10-02).
````

- [ ] **Step 3: Update the Decisions table, the layout block, and the bullets**

In `docs/design.md`'s Decisions table, replace the `Cast package` row with

```markdown
| Cast package | `kaomoji`, a flat directory with a `build` script; one binary in `/usr/bin/`, a deb per architecture built in the tools image | `pihero` depends on it for its MOTD, so it cannot be a `pihero-*` feature package; the directory stays a runnable checkout for `go run kaomoji.go hero`, the GIF Makefile, `kaomoji-gif`, and the tests; a compiled program needs a deb per architecture, which a manifest alone cannot give, see [`kaomoji`](#kaomoji) |
| Cast language | Go, standard library only, one source file, no `go.mod` | The exception to "On-device logic": a terminal animation needs an instant start and a binary without a runtime, which neither bash (a second to the first frame on a Pi 1, bash 5 and ncurses needed) nor Python (a third of a second, Python needed) gives; Go cross-compiles for the Pi 1's ARMv6 and for a Mac with one command, where Rust needs a cross toolchain and a manifest beside the source; one file keeps `go run kaomoji.go hero` possible from a checkout |
```

and append to the `On-device logic` row's third column: `; the cast is the exception, see "Cast language"`.

Replace the `kaomoji/` block of the layout (from `  kaomoji/` to the line before `  cog/`) with:

```
  kaomoji/                                                  # flat, no root/ and no nfpm.yaml: builds itself, see Decisions
    kaomoji.go                                              # Go, the engine and the three characters -> /usr/bin/kaomoji
    build  nfpm.yaml.in  bootstrap.sh                       # cross-compiles in the tools image, packs a deb per architecture, renders the curl-line scripts
    README.md                                               # the cast, shown as GIFs
    kaomoji-gif                                             # bash, records a command with asciinema and renders it with agg, Mac-side, not shipped
    Makefile  assets/*.gif                                  # the README's GIFs and how they are rendered, not shipped
    tests/test_<character>.py  test_kaomoji.py  test_bootstrap.py  test_build.py   # tier 0
    tests/test_installed.py                                 # tiers 1, 2, and ssh
```

In the `Paths` bullet replace `` `kaomoji` puts its faces in `/usr/bin/` and its engine in `/usr/lib/kaomoji/`. `` with
`` `kaomoji` puts its one binary in `/usr/bin/`. ``. In the `Manifest` bullet replace `` `kaomoji` names its four files
instead of a tree and has no maintainer scripts. `` with `` `kaomoji` has no manifest the build reads directly: a `build`
script without a Containerfile runs in the tools image with the version and prints its debs, one per architecture, from a
manifest template. ``

- [ ] **Step 4: Update testing.md**

In the tier table's row 0, replace `shellcheck,` with `shellcheck, gofmt and go vet,`. In "Tools container", extend the
first sentence's list to `(nfpm, Go, cloud-init, shellcheck, apt-utils, mtools, dosfstools, e2fsprogs, qemu-utils)` and
append to the second paragraph:

```markdown
A `build` script without a Containerfile runs in the tools image instead, with `--dist` and `--version`, every time;
[packages/kaomoji](../packages/kaomoji) cross-compiles its Go binaries that way, Go's build cache living in the podman
volume `pihero-go-cache`, so a build takes seconds, and the tier-0 suite builds the Mac binary it tests the same way
through `python -m pihero_testkit.tools -- <command>`.
```

In "Release", after the paragraph on pre-release tags, add:

```markdown
The release carries the debs, the five `kaomoji` binaries, and the four bootstrap scripts, see
[design.md](design.md#kaomoji); it is created as a draft and published when every asset is up, so
`releases/latest/download/hero` never serves a script whose binary is missing.
```

- [ ] **Step 5: Update the root README**

In `README.md`'s packages table, replace the `kaomoji` row with:

```markdown
| `kaomoji`             | The Pi Hero cast: `kaomoji hero`, `wizard`, and `visitor` print one animated kaomoji each on the terminal, from one static binary that a curl line runs anywhere; `pihero` depends on it and shows the hero in its MOTD |
```

- [ ] **Step 6: Check the docs and the whole tier 0**

```bash
awk 'length > 160 {print FILENAME": "FNR}' docs/testing.md packages/kaomoji/README.md
make test-tier0
```

Expected: no line over 160 columns (design.md's Decisions table rows and the README tables cannot wrap and are exempt),
tier 0 green.

- [ ] **Step 7: Commit**

```bash
git add docs/design.md docs/testing.md README.md
git commit -m "docs(kaomoji): the cast in Go, measured on the Pi 1"
```

---

## QA for the whole change

Tiers 0 and 1 green on both platforms (`make test`), tier 2 green (`make test-tier2`); on `busy-screen.local` after
`make deploy`, `ssh busy-screen.local` shows the MOTD's hero and `kaomoji hero --animate --loops 2 --exit` plays within
the times recorded in design.md; on the Mac, `./packages/kaomoji/.build/kaomoji hero --animate --exit` on a 200-column
terminal leaves in the same time as on an 80-column one; the GIFs regenerate with their boxes unchanged. After the first
`v*` tag: `curl -fsSL https://github.com/bkahlert/pihero/releases/latest/download/hero | bash -s -- --animate --exit`
plays the hero on the Mac and on the Pi, and a second run fetches nothing.
