# `kaomoji` Package and MOTD Mood Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Pi Hero cast as the Debian package `kaomoji`, make `pihero` depend on it, and let the MOTD render the hero through `hero` in a mood that follows the board's state.

**Architecture:** `packages/kaomoji` stays a flat, runnable checkout; a new `nfpm.yaml` maps the three faces to `/usr/bin/` and the engine to `/usr/lib/kaomoji/kaomoji.bash`, and each face sources the engine next to itself if present, else the installed one. `pihero`'s MOTD gains a pure `mood()` and calls `hero --mood <mood> --no-color` on `PATH` instead of reading a committed banner file. The harness discovers the package by its manifest and installs every built `.deb` in one apt call, so nothing there changes.

**Tech Stack:** bash 5 scripts, nfpm, Python 3 standard library on the device, pytest with pytest-testinfra, podman for tier 1.

**Spec:** [docs/superpowers/specs/2026-09-30-kaomoji-package-design.md](../specs/2026-09-30-kaomoji-package-design.md)

## Global Constraints

- `kaomoji` is `Architecture: all`, depends on `bash (>= 5.0)` and nothing else; `ncurses-bin` is Essential and stays undeclared. It has no maintainer scripts and no `root/` tree: `nfpm.yaml` names the four files, faces `0755`, engine `0644`.
- Paths: `/usr/bin/hero`, `/usr/bin/wizard`, `/usr/bin/visitor`, `/usr/lib/kaomoji/kaomoji.bash`. `kaomoji-gif`, the Makefile, the assets, and the README are not shipped.
- `pihero` gets `Depends: kaomoji`, unversioned. The MOTD stays plain and Python 3 standard library; the mood is sad on a failed unit, else unknown on a pending reboot, else happy. `hero.txt` is removed.
- A face sources the engine without forking: `${BASH_SOURCE[0]%/*}/kaomoji.bash` if it exists, else `/usr/lib/kaomoji/kaomoji.bash`. Every shell file passes shellcheck; headers stay Google-style (`~/.config/agents/rules/bash.md`).
- Tests: one class per subject, names are claims, tests first and helpers last, result stored before asserting, no docstrings on tests or helpers (`~/.config/agents/rules/testing.md`). Markdown references to files are links.
- Commits: Conventional Commits with the package as scope, one change per commit, no AI attribution trailers. Gate every commit on `uv run pytest -m tier0 -q` being green. Work on the existing branch `feat/kaomoji`.
- Commands run from the repository root. `make build` and tier 1 need the podman machine running: `podman machine start`.

## Review Focus

1. A failed unit and a pending reboot at the same time must give the sad hero, not the puzzled one (Task 3, `TestMood`).
2. A face started without a directory in its path, as `bash hero` in the checkout does, must look for the installed engine and, where there is none, fail naming that path rather than silently doing something else (Task 1, `TestEngineLookup`).
3. The MOTD must still print its four lines when `hero` is not on `PATH`, with an empty banner, rather than crash at login (Task 3, `TestMain`).
4. Purging `kaomoji` on a system where `pihero` depends on it takes `pihero` with it; `reinstall` must bring both back so the remaining tests see a whole system (Task 2, `TestRemoval`).
5. The hero's UTF-8 glyphs must survive the MOTD's subprocess round trip in an environment without a locale, which is what pam_motd and `podman exec` provide (Task 3, tier-1 `TestMotd` asserts the exact face).

---

### Task 1: A face finds the engine next to itself or under `/usr/lib/kaomoji`

**Files:**
- Modify: `packages/kaomoji/hero:41-42`
- Modify: `packages/kaomoji/wizard:42-43`
- Modify: `packages/kaomoji/visitor:41-42`
- Modify: `packages/kaomoji/kaomoji.bash:3`
- Test: `packages/kaomoji/tests/test_kaomoji.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: the faces run from any directory as long as the engine is next to them or at `/usr/lib/kaomoji/kaomoji.bash`. `kaomoji-gif` is unchanged and keeps sourcing the sibling.

- [ ] **Step 1: Write the failing test**

Add to `packages/kaomoji/tests/test_kaomoji.py`, after the last test class and before the module-level helpers (`bash`, `tput`) at the bottom. `PACKAGE` is already defined at the top of the file, `subprocess` and `Path` are already imported.

```python
class TestEngineLookup:
    @pytest.mark.parametrize("face", ["hero", "wizard", "visitor"])
    def test_a_face_started_without_a_directory_looks_for_the_installed_engine(self, face):
        if Path("/usr/lib/kaomoji/kaomoji.bash").exists():
            pytest.skip("the installed engine would be found")

        result = subprocess.run(["bash", face, "--no-color"], cwd=PACKAGE, capture_output=True, text=True)

        assert result.returncode == 1
        assert "/usr/lib/kaomoji/kaomoji.bash" in result.stderr
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest packages/kaomoji/tests/test_kaomoji.py -k TestEngineLookup -q`

Expected: 3 failed. Today `dirname hero` is `.`, so the sibling engine is found and the face prints its kaomoji with exit code 0.

- [ ] **Step 3: Replace the sourcing line in the three faces**

In `packages/kaomoji/hero` (lines 41–42), `packages/kaomoji/wizard` (lines 42–43), and `packages/kaomoji/visitor` (lines 41–42), replace

```bash
# shellcheck source=kaomoji.bash
. "$(dirname "${BASH_SOURCE[0]}")/kaomoji.bash"
```

with

```bash
# The engine sits next to the face in the checkout, and in /usr/lib/kaomoji once installed.
KAOMOJI_ENGINE=${BASH_SOURCE[0]%/*}/kaomoji.bash
[ -e "$KAOMOJI_ENGINE" ] || KAOMOJI_ENGINE=/usr/lib/kaomoji/kaomoji.bash
# shellcheck source=kaomoji.bash
. "$KAOMOJI_ENGINE"
```

Leave `packages/kaomoji/kaomoji-gif` as it is.

- [ ] **Step 4: Update the engine's usage line**

In `packages/kaomoji/kaomoji.bash`, replace line 3

```bash
# Usage:   . "$(dirname "${BASH_SOURCE[0]}")/kaomoji.bash"
```

with

```bash
# Usage:   KAOMOJI_ENGINE=${BASH_SOURCE[0]%/*}/kaomoji.bash
#          [ -e "$KAOMOJI_ENGINE" ] || KAOMOJI_ENGINE=/usr/lib/kaomoji/kaomoji.bash
#          . "$KAOMOJI_ENGINE"
```

- [ ] **Step 5: Run the kaomoji tests and the static checks**

Run: `uv run pytest packages/kaomoji testkit/tests/test_static.py -q`

Expected: all pass, including the three new tests (`bash hero` now fails with bash's "No such file or directory" for `/usr/lib/kaomoji/kaomoji.bash`) and shellcheck over the three faces.

- [ ] **Step 6: Check the faces still run by path, and no fork was added**

Run:

```bash
packages/kaomoji/hero --no-color && packages/kaomoji/wizard --no-color && packages/kaomoji/visitor --no-color
(cd packages/kaomoji && ./hero --mood happy --no-color)
```

Expected: `─=≡▰▩▩[ 蓬•ｏ•]⊐`, `(つ◕౪◕)つ─｡ﾟ․☆･*ﾟ`, `┴┬┴┤´Ｏ´)ﾉ`, `─=≡▰▩▩[✿＾ｖ＾]⊐`.

- [ ] **Step 7: Commit**

```bash
uv run pytest -m tier0 -q
git add packages/kaomoji/hero packages/kaomoji/wizard packages/kaomoji/visitor packages/kaomoji/kaomoji.bash packages/kaomoji/tests/test_kaomoji.py
git commit -m 'refactor(kaomoji): let a face find the engine next to itself or under /usr/lib/kaomoji'
```

---

### Task 2: The `kaomoji` package

**Files:**
- Create: `packages/kaomoji/nfpm.yaml`
- Create: `packages/kaomoji/tests/test_installed.py`
- Modify: `docs/design.md` (Architecture block, layout block, "Names" and "Paths" bullets, Decisions table, `kaomoji` section)
- Modify: `README.md` (package table)
- Modify: `packages/kaomoji/README.md` (first paragraph)
- Modify: `docs/app-conventions.md` (bullet list)

**Interfaces:**
- Consumes: the engine lookup from Task 1.
- Produces: `dist/kaomoji_<version>_all.deb` with `/usr/bin/hero`, `/usr/bin/wizard`, `/usr/bin/visitor` (`0755`) and `/usr/lib/kaomoji/kaomoji.bash` (`0644`); tier-1 tests for it; the package name `kaomoji` Task 3 depends on.

- [ ] **Step 1: Write the failing tier-1 tests**

Create `packages/kaomoji/tests/test_installed.py`:

```python
import pytest

pytestmark = pytest.mark.installed


class TestPackage:
    def test_is_installed_at_the_built_version(self, host, version):
        package = host.package("kaomoji")

        assert package.is_installed
        assert package.version == version

    @pytest.mark.parametrize("path", ["/usr/bin/hero", "/usr/bin/wizard", "/usr/bin/visitor"])
    def test_ships_the_faces_as_commands_owned_by_root(self, host, path):
        file = host.file(path)

        assert file.exists
        assert file.mode == 0o755
        assert file.user == "root"

    def test_ships_the_engine_owned_by_root_read_only(self, host):
        file = host.file("/usr/lib/kaomoji/kaomoji.bash")

        assert file.exists
        assert file.mode == 0o644
        assert file.user == "root"


class TestFaces:
    @pytest.mark.parametrize(
        ("command", "text"),
        [
            ("hero --mood happy --no-color", "─=≡▰▩▩[✿＾ｖ＾]⊐"),
            ("wizard --no-color", "(つ◕౪◕)つ─｡ﾟ․☆･*ﾟ"),
            ("visitor --no-color", "┴┬┴┤´Ｏ´)ﾉ"),
        ],
    )
    def test_render_from_path_through_the_installed_engine(self, host, command, text):
        output = host.check_output(command)

        assert output == text


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_leaves_nothing_behind_and_reinstall_restores_the_system(self, host, target):
        target.purge(["kaomoji"])

        for path in SHIPPED:
            assert not host.file(path).exists

        target.reinstall()

        assert host.package("kaomoji").is_installed
        assert host.package("pihero").is_installed


SHIPPED = ["/usr/bin/hero", "/usr/bin/wizard", "/usr/bin/visitor", "/usr/lib/kaomoji/kaomoji.bash"]
```

- [ ] **Step 2: Run tier 1 to verify the new tests fail**

Run: `podman machine start 2>/dev/null; uv run pytest -m installed --target=podman packages/kaomoji -q`

Expected: every test in the new file fails or errors, because no `kaomoji` package exists yet (`host.package("kaomoji").is_installed` is false, the files do not exist, `hero` is not found). Tier 1 builds every package first; that takes a minute or two.

- [ ] **Step 3: Write the manifest**

Create `packages/kaomoji/nfpm.yaml`:

```yaml
name: kaomoji
arch: all
platform: linux
version: ${VERSION}
section: utils
priority: optional
maintainer: Björn Kahlert <bkahlert@users.noreply.github.com>
description: |
  The Pi Hero cast: three animated kaomoji for the terminal.
  hero, wizard, and visitor print one face each, static or animated, plain or colored, in every mood they have.
homepage: https://github.com/bkahlert/pihero
license: MIT
depends:
  - bash (>= 5.0)
contents:
  - src: kaomoji.bash
    dst: /usr/lib/kaomoji/kaomoji.bash
    file_info:
      mode: 0644
  - src: hero
    dst: /usr/bin/hero
    file_info:
      mode: 0755
  - src: wizard
    dst: /usr/bin/wizard
    file_info:
      mode: 0755
  - src: visitor
    dst: /usr/bin/visitor
    file_info:
      mode: 0755
```

No `scripts:` block: the package has no units, users, or rendered files. The build still writes unused `.build/` scripts next to it; that directory is gitignored.

- [ ] **Step 4: Build and inspect the package**

Run:

```bash
make build
ls dist/kaomoji_*_all.deb
ar p dist/kaomoji_*_all.deb data.tar.gz | tar -tzv
```

Expected: one `kaomoji_<version>_all.deb`; the listing shows `./usr/bin/hero`, `./usr/bin/wizard`, `./usr/bin/visitor` as `-rwxr-xr-x` and `./usr/lib/kaomoji/kaomoji.bash` as `-rw-r--r--`, nothing else under `usr/`.

- [ ] **Step 5: Run tier 1 for the package and the whole tier-0 suite**

Run: `uv run pytest -m installed --target=podman packages/kaomoji -q && uv run pytest -m tier0 -q`

Expected: all tier-1 tests of the package pass, including the purge and reinstall (at this point `pihero` does not depend on `kaomoji` yet, so the purge removes only `kaomoji`; Task 3 makes it cascade, and `reinstall` covers both). Tier 0 passes; shellcheck now also sees nothing new, since no shell file was added.

- [ ] **Step 6: Record the package in design.md**

In `docs/design.md`:

1. Architecture block (line 50–51): change

   ```
   │ Pi Hero         pihero, pihero-avahi, pihero-usb-gadget,     │  this repo, packages/*
   │                 pihero-kiosk, later pihero-bt-pan           │
   ```

   to

   ```
   │ Pi Hero         pihero, pihero-avahi, pihero-usb-gadget,     │  this repo, packages/*
   │                 pihero-kiosk, kaomoji, later pihero-bt-pan  │
   ```

2. Layout block: replace the `kaomoji/` entry

   ```
     kaomoji/                                                  # no nfpm.yaml: not built, not shipped yet
       README.md                                               # the cast, shown as GIFs
       kaomoji.bash                                            # bash, the engine: painting, pacing, grid, command line
       hero  wizard  visitor                                   # bash, one character each, sourcing the engine
       kaomoji-gif                                             # bash, records a command with asciinema and renders it with agg, Mac-side
       Makefile  assets/*.gif                                  # the README's GIFs and how they are rendered
       tests/test_<character>.py                               # tier 0
   ```

   with

   ```
     kaomoji/                                                  # flat, no root/: nfpm.yaml maps the files, see Decisions
       nfpm.yaml                                               # depends: bash; four contents entries, no maintainer scripts
       README.md                                               # the cast, shown as GIFs
       kaomoji.bash                                            # bash, the engine: painting, pacing, grid, command line; -> /usr/lib/kaomoji/
       hero  wizard  visitor                                   # bash, one character each, sourcing the engine; -> /usr/bin/
       kaomoji-gif                                             # bash, records a command with asciinema and renders it with agg, Mac-side, not shipped
       Makefile  assets/*.gif                                  # the README's GIFs and how they are rendered, not shipped
       tests/test_<character>.py                               # tier 0
       tests/test_installed.py                                 # tiers 1, 2, and ssh
   ```

3. "Names" bullet: change `**Names.** \`pihero\` is the core, everything else is \`pihero-<feature>\`.` to
   `**Names.** \`pihero\` is the core, everything else is \`pihero-<feature>\`, except \`kaomoji\`: the cast is no Pi Hero feature, and \`pihero\` depends on it.`

4. "Paths" bullet: append the sentence `\`kaomoji\` puts its faces in \`/usr/bin/\` and its engine in \`/usr/lib/kaomoji/\`.`

5. Decisions table: add a row after "Core package name":

   ```
   | Cast package | `kaomoji`, a flat directory; faces in `/usr/bin/`, the engine in `/usr/lib/kaomoji/` | `pihero` depends on it for its MOTD, so it cannot be a `pihero-*` feature package; the directory stays a runnable checkout for the README's `./hero`, the GIF Makefile, `kaomoji-gif`, and the tests, so `nfpm.yaml` maps the four files instead of a `root/` tree |
   ```

6. `kaomoji` section: replace the first two sentences

   ```
   The Pi Hero cast, not shipped yet: [packages/kaomoji](../packages/kaomoji) has no `nfpm.yaml`, so `make build` skips it,
   while its tests run in tier 0 and its scripts pass the static checks like every package's.
   ```

   with

   ```
   The Pi Hero cast, shipped as the package `kaomoji` from [packages/kaomoji](../packages/kaomoji): `hero`, `wizard`, and
   `visitor` in `/usr/bin/`, the engine in `/usr/lib/kaomoji/kaomoji.bash`, which a face sources next to itself in the
   checkout and from there once installed, without a fork. It depends on bash alone; `pihero` depends on it for its MOTD.
   Its tests run in tier 0, its scripts pass the static checks like every package's, and tier 1 runs the faces from `PATH`.
   ```

   and replace the closing sentences of the Performance paragraph

   ```
   Where the faces end up is open: the engine in `pihero` with each app owning its face, or the
   whole cast in one package. Tests, performance, and the function API come first.
   ```

   with

   ```
   The cast stays one package until an app needs to change a face of its own.
   ```

- [ ] **Step 7: Record the package in the READMEs and the app conventions**

1. `README.md`, package table: add a row after `pihero-kiosk`, aligned like the others:

   ```
   | `kaomoji`             | The Pi Hero cast: `hero`, `wizard`, and `visitor` print one animated kaomoji each on the terminal; `pihero` depends on it and shows the hero in its MOTD           |
   ```

2. `packages/kaomoji/README.md`: after the first paragraph, add

   ```
   `apt install kaomoji` from the Pi Hero repository puts the three scripts on `PATH` and the engine in
   `/usr/lib/kaomoji/`; `pihero` depends on it for its MOTD. In this directory they run as `./hero`, with the engine next to
   them.
   ```

3. `docs/app-conventions.md`: add a bullet after the `pihero-kiosk` bullet:

   ```
   - An app that shows a face runs `hero`, `wizard`, or `visitor` from the `kaomoji` package, which `pihero` brings along,
     and ships no copy of a script.
   ```

- [ ] **Step 8: Commit**

```bash
uv run pytest -m tier0 -q
git add packages/kaomoji/nfpm.yaml packages/kaomoji/tests/test_installed.py packages/kaomoji/README.md docs/design.md docs/app-conventions.md README.md
git commit -m 'feat(kaomoji): ship the cast as a Debian package

hero, wizard, and visitor land in /usr/bin and the engine in
/usr/lib/kaomoji, built from the flat directory by nfpm; the cast is
one package until an app needs a face of its own.'
```

---

### Task 3: The MOTD shows the hero in the mood of the board

**Files:**
- Modify: `packages/pihero/nfpm.yaml:14-16` (`depends`)
- Modify: `packages/pihero/root/usr/lib/pihero/motd`
- Delete: `packages/pihero/root/usr/share/pihero/hero.txt`
- Modify: `packages/pihero/tests/test_motd.py`
- Modify: `packages/pihero/tests/test_installed.py`
- Modify: `docs/design.md` (`pihero` section, MOTD paragraph)

**Interfaces:**
- Consumes: `/usr/bin/hero --mood <neutral|happy|sad|unknown> --no-color` from Task 2, printing one line.
- Produces: `mood(failed: list[str], reboot_required: bool) -> str` in the `motd` script, returning `"sad"`, `"unknown"`, or `"happy"`; `main()` renders the banner through `hero` on `PATH`.

- [ ] **Step 1: Write the failing tier-0 tests**

In `packages/pihero/tests/test_motd.py`, add `import os` to the imports, add `TestMood` after `TestRebootState`, add `TestMain` after `TestRender`, and add the `stub` helper at the very bottom of the file:

```python
class TestMood:
    def test_is_sad_on_a_failed_unit(self):
        assert motd.mood(["x.service"], False) == "sad"

    def test_is_unknown_on_a_pending_reboot(self):
        assert motd.mood([], True) == "unknown"

    def test_is_happy_otherwise(self):
        assert motd.mood([], False) == "happy"

    def test_a_failed_unit_wins_over_a_pending_reboot(self):
        assert motd.mood(["x.service"], True) == "sad"
```

```python
class TestMain:
    def test_renders_the_banner_through_hero_in_the_mood_of_the_state(self, tmp_path, monkeypatch, capsys):
        stub(tmp_path, "systemctl", 'printf "x.service loaded failed failed X\\n"')
        stub(tmp_path, "hero", 'printf "%s\\n" "$*" >> "$0.log"; printf "HERO %s\\n" "$2"')
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        monkeypatch.setattr(motd, "RUN", tmp_path)

        motd.main()

        out = capsys.readouterr().out
        assert out.startswith("\nHERO sad\n\n")
        assert (tmp_path / "hero.log").read_text() == "--mood sad --no-color\n"

    def test_asks_for_the_puzzled_hero_on_a_pending_reboot(self, tmp_path, monkeypatch, capsys):
        stub(tmp_path, "systemctl", "")
        stub(tmp_path, "hero", 'printf "HERO %s\\n" "$2"')
        (tmp_path / "reboot-required").write_text("*** System restart required ***\n")
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        monkeypatch.setattr(motd, "RUN", tmp_path)

        motd.main()

        out = capsys.readouterr().out
        assert out.startswith("\nHERO unknown\n\n")

    def test_prints_the_lines_without_a_hero(self, tmp_path, monkeypatch, capsys):
        stub(tmp_path, "systemctl", "")
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.setattr(motd, "RUN", tmp_path)

        motd.main()

        out = capsys.readouterr().out
        assert out.startswith("\n\n\n  packages:")
        assert "  failed units:    none\n" in out
        assert "  reboot required: no\n" in out
```

```python
def stub(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path
```

The `hero` stub prints `HERO <mood>`, where `$2` is the value after `--mood`, and logs its arguments next to itself. With `PATH` reduced to the stub directory, `dpkg-query`, `ip`, and `hero` are not found, which the MOTD's `_output` helper turns into empty output.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/pihero/tests/test_motd.py -q`

Expected: `TestMood` fails with `AttributeError: module has no attribute 'mood'`; `TestMain` fails because the banner is read from `/usr/share/pihero/hero.txt` (missing on the Mac, so empty) and the `hero.log` file is never written.

- [ ] **Step 3: Implement the mood and the banner**

In `packages/pihero/root/usr/lib/pihero/motd`:

1. Replace the module docstring

   ```python
   """Prints the Pi Hero MOTD: banner, installed pihero packages, failed units, pending reboot, usb0 address."""
   ```

   with

   ```python
   """Prints the Pi Hero MOTD: the hero in the mood of the board, installed pihero packages, failed units, pending reboot, usb0 address."""
   ```

2. Delete the line `BANNER = Path("/usr/share/pihero/hero.txt")`.

3. Add after `reboot_state`:

   ```python
   def mood(failed: list[str], reboot_required: bool) -> str:
       if failed:
           return "sad"
       if reboot_required:
           return "unknown"
       return "happy"
   ```

4. Replace `main`:

   ```python
   def main() -> int:
       packages = parse_dpkg(_output(["dpkg-query", "-W", "-f=${Package} ${Version} ${db:Status-Abbrev}\n", "pihero*"]))
       failed = parse_failed(_output(["systemctl", "--failed", "--no-legend", "--plain"]))
       usb0 = parse_usb0(_output(["ip", "-o", "-4", "addr", "show", "dev", "usb0"]))
       reboot = reboot_state(RUN)
       banner = _output(["hero", "--mood", mood(failed, reboot[0]), "--no-color"])
       sys.stdout.write(render(banner, packages, failed, reboot, usb0))
       return 0
   ```

`render` and `_output` stay as they are. `Path` is still used by `RUN` and `reboot_state`.

- [ ] **Step 4: Remove the committed banner and declare the dependency**

```bash
git rm -q packages/pihero/root/usr/share/pihero/hero.txt
```

In `packages/pihero/nfpm.yaml`, change

```yaml
depends:
  - python3
  - systemd
```

to

```yaml
depends:
  - python3
  - systemd
  - kaomoji
```

- [ ] **Step 5: Run the tier-0 MOTD tests**

Run: `uv run pytest packages/pihero/tests/test_motd.py -q`

Expected: all pass (the twelve existing, four `TestMood`, three `TestMain`).

- [ ] **Step 6: Write the failing tier-1 tests**

In `packages/pihero/tests/test_installed.py`:

1. Add to `TestMotd`:

   ```python
       def test_shows_the_hero_in_the_mood_of_the_board(self, host):
           output = host.check_output("/usr/lib/pihero/motd")

           banner, details = output.lstrip("\n").split("\n", 1)
           assert banner == face_for(details)
   ```

2. In `TestBootconfig.test_edits_cmdline_and_flags_a_reboot`, replace

   ```python
           assert "reboot required: yes (pihero-probe)" in host.check_output("/usr/lib/pihero/motd")
   ```

   with

   ```python
           output = host.check_output("/usr/lib/pihero/motd")
           assert "reboot required: yes (pihero-probe)" in output
           if "  failed units:    none\n" in output:
               assert output.lstrip("\n").startswith(FACES["unknown"] + "\n")
   ```

3. Add to `TestRemoval.test_purge_leaves_nothing_behind`, after the existing two `assert not` lines:

   ```python
           assert not host.file("/usr/share/pihero/hero.txt").exists
   ```

4. Add at the bottom of the file:

   ```python
   FACES = {"sad": "─=≡▰▩▩[ ༶◕︿◕ ]⊐", "unknown": "─=≡▰▩▩[༶´⊙﹏⊙`]⊐", "happy": "─=≡▰▩▩[✿＾ｖ＾]⊐"}


   def face_for(details: str) -> str:
       # The container is accepted degraded, so the expected face follows the lines the MOTD printed.
       if "  failed units:    none\n" not in details:
           return FACES["sad"]
       if "  reboot required: no\n" not in details:
           return FACES["unknown"]
       return FACES["happy"]
   ```

`host.check_output` strips the trailing newline, so the last line, `usb0`, has none, while the two lines the helper looks at do.

- [ ] **Step 7: Run tier 1 for `pihero` and `kaomoji`**

Run: `uv run pytest -m installed --target=podman packages/pihero packages/kaomoji -q`

Expected: all pass. In particular the banner matches the face the details call for, the bootconfig test sees the puzzled hero while its reboot is flagged, purging `kaomoji` now removes `pihero` as well and `reinstall` restores both, and `hero.txt` is gone after purge. Repeat for the 32-bit platform once: `uv run pytest -m installed --target=podman --platform=linux/arm/v7 packages/pihero packages/kaomoji -q`.

- [ ] **Step 8: Update the MOTD paragraph in design.md**

In `docs/design.md`, `pihero` section, replace

```
**MOTD.** `/etc/update-motd.d/50-pihero` runs `/usr/lib/pihero/motd`: the hero banner rendered once at build time, then the
installed `pihero-*` packages with versions, failed units, whether a reboot is pending and for which packages, and the address
of `usb0` if present. No colours, no animation, nothing beyond Python.
```

with

```
**MOTD.** `/etc/update-motd.d/50-pihero` runs `/usr/lib/pihero/motd`: a blank line to set it apart from Debian's kernel
line, the hero in the mood of the board, then the installed `pihero-*` packages with versions, failed units, whether a
reboot is pending and for which packages, and the address of `usb0` if present. The mood follows the lines below it: sad
when a unit has failed, puzzled (`unknown`) when a reboot is pending, happy otherwise; neutral, the hero at rest, is left
to the panels. The banner is `hero --mood <mood> --no-color` from `kaomoji`, found on `PATH` and run at every login: plain,
static, and 0.3–0.5 s on a Pi 1 next to the 2.4 s the probes take (busy-screen.local, 2026-09-30). No colours, no
animation, nothing beyond Python and that one call.
```

- [ ] **Step 9: Commit**

```bash
uv run pytest -m tier0 -q
git add packages/pihero/nfpm.yaml packages/pihero/root/usr/lib/pihero/motd packages/pihero/tests/test_motd.py packages/pihero/tests/test_installed.py docs/design.md
git commit -m 'feat(pihero): show the hero in the MOTD in the mood of the board

The banner is rendered by hero from the kaomoji package at login, sad
when a unit has failed, puzzled when a reboot is pending, happy
otherwise; the committed hero.txt goes.'
```

---

### Task 4: Prove it on hardware and hand the follow-up over

**Files:** none changed.

**Interfaces:**
- Consumes: the built packages from Tasks 2 and 3.
- Produces: the ssh-tier run on busy-screen.local and the handover text for the choam.de repository.

- [ ] **Step 1: Deploy to the Pi 1**

Run: `make deploy TARGET=pi@busy-screen.local`

Expected: apt installs `kaomoji` and the rebuilt `pihero`, `pihero-avahi`, `pihero-kiosk`, `pihero-usb-gadget` in one call; no error about an unmet `kaomoji` dependency.

- [ ] **Step 2: Look at the MOTD in all three moods**

```bash
ssh pi@busy-screen.local 'which hero; /usr/lib/pihero/motd'
ssh pi@busy-screen.local 'sudo systemd-run --unit=pihero-probe --quiet /bin/false; sleep 1; /usr/lib/pihero/motd; sudo systemctl reset-failed pihero-probe.service'
ssh pi@busy-screen.local 'sudo touch /run/reboot-required; /usr/lib/pihero/motd; sudo rm /run/reboot-required'
```

Expected, in order: `/usr/bin/hero` and the happy hero `─=≡▰▩▩[✿＾ｖ＾]⊐` over `failed units: none` and `reboot required: no`; the sad hero `─=≡▰▩▩[ ༶◕︿◕ ]⊐` over `failed units: pihero-probe.service`; the puzzled hero `─=≡▰▩▩[༶´⊙﹏⊙`]⊐` over `reboot required: yes`. The transient unit and the flag are removed again by the same commands. Then `ssh pi@busy-screen.local` once to see the login banner start with a blank line, the hero, a blank line, and the four lines.

- [ ] **Step 3: Run the ssh tier**

Run: `uv run pytest -m installed --target=ssh --target-uri=pi@busy-screen.local -q`

Expected: pass; the mutating tests are skipped on a real device. The version the tests compare against is the one installed in Step 1.

- [ ] **Step 4: Hand the choam.de follow-up over**

Nothing to commit here. Report the following text to the user for the AI working in the choam.de repository:

> In `docs/hosts/pi/shishakli/user-data.tmpl`, remove the `write_files` entry for `/usr/local/bin/hero` together with its comment ("pihero's assets/hero at commit a7ee2ca, verbatim ..."): the hero is now `/usr/bin/hero` from the `kaomoji` package, which `pihero` depends on, so it arrives with `packages: [pihero]`. In `/usr/local/lib/hero-lcd/run`, change the last line to `exec /usr/bin/hero --mood neutral --animate --color`. In `README.md`, section "The hero on tty1", the table row for `/usr/local/lib/hero-lcd/run` says `exec /usr/bin/hero ...` and the row for `/usr/local/bin/hero` goes; the "Provisioning" paragraph no longer lists "the hero script" among the `write_files`. Nothing changes on the other six hosts.
