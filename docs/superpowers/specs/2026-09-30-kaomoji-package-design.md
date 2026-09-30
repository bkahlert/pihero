# `kaomoji`: the cast as a package, and a hero with a mood in the MOTD

Date: 2026-09-30. Status: approved design, ready for planning.

## Intent

The Pi Hero cast in [packages/kaomoji](../../../packages/kaomoji) is finished as code and tested in tier 0, but ships
nowhere: the directory has no `nfpm.yaml`, so `make build` skips it. The MOTD of `pihero` shows the hero from a committed
copy, [hero.txt](../../../packages/pihero/root/usr/share/pihero/hero.txt), and one fleet host, shishakli in the choam.de
repository, carries a 600-line copy of the single-file `hero` of commit a7ee2ca in its cloud-init `write_files`, "refreshed
by hand when it changes". That copy cannot be refreshed any more: today's `hero` sources `kaomoji.bash` next to it.

This ships the cast as one Debian package, `kaomoji`, in the same repository and at the same version as everything else,
makes `pihero` depend on it, and lets the MOTD render its banner through `hero` with a mood that follows the board's state:
happy when nothing is wrong, puzzled when a reboot is pending, sad when a unit has failed.

Success looks like this: `apt install pihero` on any Pi Hero host brings `hero`, `wizard`, and `visitor` onto `PATH`;
`ssh <host>` shows a hero whose face matches the lines below it; the tests prove the package builds, installs, runs from
`/usr/bin`, and purges cleanly; and the shishakli template in choam.de can drop its inline copy for `/usr/bin/hero`, a
two-line edit handed over to that repository.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Package name | `kaomoji`, not `pihero-kaomoji` | `pihero` depends on it, so it cannot be a `pihero-*` feature package, which by rule depends on `pihero`; the cast is also of use without Pi Hero. The MOTD's package list matches `pihero*` and will not list it, which is accepted |
| Scope of the package | The whole cast: engine, `hero`, `wizard`, `visitor` | Closes the open question in [design.md](../../design.md#kaomoji): one package, apps own no faces yet; `kaomoji-gif` stays out, it is a Mac-side tool needing asciinema and agg |
| Paths | Faces in `/usr/bin/`, the engine in `/usr/lib/kaomoji/kaomoji.bash` | The faces are user commands, unlike `pihero`'s executables under `/usr/lib/pihero/`; the engine is not a command, and the package gets its own namespace since it is not a Pi Hero feature |
| Layout in the repository | Flat, as today; `nfpm.yaml` maps the four files to their destinations | The directory is a runnable checkout: `./hero` in the README, the GIF Makefile, `kaomoji-gif`, and the tests all address the scripts by their bare names, and a `root/usr/bin/hero` would end that. The exception to the `root/` convention is recorded in design.md |
| Engine lookup | A face sources the engine next to itself if there is one, else `/usr/lib/kaomoji/kaomoji.bash`, without forking | The checkout, the tests, and the GIF renderer keep working unchanged; the installed face finds the installed engine; `dirname` would cost a fork, 40 ms on a Pi 1 |
| Dependencies | `bash (>= 5.0)` | What the scripts need; `tput` comes from `ncurses-bin`, Essential in Debian, so not declared |
| Maintainer scripts | None | No units, no users, nothing to render |
| `pihero` and the cast | `Depends: kaomoji`, unversioned | The MOTD uses `hero --mood <mood> --no-color`, a stable interface; a versioned dependency would only complicate `apt-mark hold` and version pins |
| MOTD banner | `hero --mood <mood> --no-color`, run at every login | One source of truth for the hero; plain, as the MOTD decision stands. Measured on busy-screen.local (Pi 1, kiosk running): 0.3–0.5 s for a static plain hero next to 2.4 s for the MOTD itself |
| Mood | Sad on a failed unit, unknown on a pending reboot, else happy; failed wins | Each face has its reason two lines below it; the puzzled face reads as "not yet what I will be"; neutral stays the hero at rest, the face on shishakli's panel |

## Package anatomy

```
packages/kaomoji/
  nfpm.yaml                              # new: depends: bash (>= 5.0); four contents entries; no scripts
  kaomoji.bash                           # -> /usr/lib/kaomoji/kaomoji.bash, 0644
  hero  wizard  visitor                  # -> /usr/bin/<name>, 0755; unchanged but for the engine lookup
  kaomoji-gif  Makefile  assets/  README.md   # Mac-side, not shipped
  tests/test_kaomoji.py  test_hero.py  test_wizard.py  test_visitor.py  test_kaomoji_gif.py   # tier 0, as today
  tests/test_installed.py                # new: tiers 1, 2, and ssh
```

`nfpm.yaml` follows [pihero-avahi](../../../packages/pihero-avahi/nfpm.yaml) in its header: `Architecture: all`,
`Section: admin`, maintainer, homepage, license. Instead of a `root/` tree its `contents` name the four files with their
destinations and modes, and it has no `scripts:` block. The description says what the package is in two lines: the Pi Hero
cast, three animated kaomoji for the terminal, `hero`, `wizard`, and `visitor`.

### The engine lookup

Every face and `kaomoji-gif` today source the engine with `dirname`:

```bash
. "$(dirname "${BASH_SOURCE[0]}")/kaomoji.bash"
```

They instead source the first of two paths that exists: `kaomoji.bash` in the directory of the script, taken from
`BASH_SOURCE` by parameter expansion, and `/usr/lib/kaomoji/kaomoji.bash`. A script started without a slash in its path,
as `bash hero` does, has no directory and takes the installed engine. `kaomoji-gif` keeps sourcing the sibling only; it is
never installed.

## The MOTD

[motd](../../../packages/pihero/root/usr/lib/pihero/motd) gains one pure function and changes one line of `main`:

- `mood(failed, reboot_required)` returns `"sad"` if any unit failed, else `"unknown"` if a reboot is required, else
  `"happy"`.
- `main` runs `hero --mood <mood> --no-color` through the existing `_output` helper, found on `PATH` like `dpkg-query` and
  `systemctl` are, and passes its output to `render` as the banner. The state is collected first, since the mood depends
  on it. A missing `hero` yields an empty banner through the same helper, the way a missing `systemctl` yields no failed
  units; the dependency makes that case theoretical.
- `hero.txt` goes, and with it the `BANNER` constant.

`render` keeps its signature and its output shape: a blank line, the banner, a blank line, the four lines. The engine
forces a UTF-8 locale on itself when the environment has none, which pam_motd's has not, so the hero renders correctly
where `uname` runs today.

## Harness

Nothing changes. The build discovers the package by its `nfpm.yaml`; tier 1 installs all built `.deb` files in one
`apt-get install`, so `pihero`'s dependency resolves against the freshly built `kaomoji`; the VM installs by name from the
flat repository the run serves, where `kaomoji` now is; `make deploy` copies and installs all `.deb` files in one call. The
all-features device file lists `pihero`, which pulls `kaomoji`. The release workflow publishes `dist/*.deb`, so the
package reaches the signed repository and the GitHub release with the next tag.

The tier-0 sweeps need no change either: shellcheck already covers the scripts, and "every package builds" iterates the
`nfpm.yaml` files, so it now builds `kaomoji` too.

## Tests

Tier 0, [test_motd.py](../../../packages/pihero/tests/test_motd.py):

- `mood`: sad on a failed unit, unknown on a pending reboot, happy otherwise, sad when both a unit failed and a reboot is
  pending.
- `main` with a `hero` stub first on `PATH` that records its argv and prints a marker: the MOTD calls it once with
  `--mood` set to the mood of the recorded state and `--no-color`, and the marker is the banner. The other probes are
  stubbed the same way, as the harness does for `modprobe` and `nmcli` in `pihero-usb-gadget`.

Tier 0, kaomoji: the existing tests stay as they are. The sibling lookup is what every one of them exercises; the
installed lookup is proven in tier 1.

Tiers 1, 2, and ssh, `packages/kaomoji/tests/test_installed.py`:

- `kaomoji` is installed at the built version.
- `/usr/bin/hero`, `/usr/bin/wizard`, and `/usr/bin/visitor` are `0755` root; `/usr/lib/kaomoji/kaomoji.bash` is `0644`
  root.
- `hero --mood happy --no-color` prints `─=≡▰▩▩[✿＾ｖ＾]⊐`, `wizard --no-color` and `visitor --no-color` print their first
  mood, all three from `PATH` and so through the installed engine.
- Purge (mutating) leaves none of the four files behind; then reinstall. Purging `kaomoji` takes `pihero` and its feature
  packages with it, as purging `pihero` already does in its own test, and `reinstall` puts everything back.

Tiers 1, 2, and ssh, [pihero's test_installed.py](../../../packages/pihero/tests/test_installed.py):

- `TestMotd` asserts the banner matches the state the MOTD reports below it: the sad face when the failed-units line
  names a unit, the puzzled face when a reboot is required, the happy face otherwise. The container is accepted in a
  degraded state, so the test derives the expectation from the output rather than assuming happy.
- The bootconfig test, which flags a reboot and reads the MOTD, additionally asserts the puzzled face unless a unit has
  failed.

## Documentation

- [design.md](../../design.md): the `kaomoji` section says the cast is shipped, its paths, its dependency, and that the
  open question is closed; the layout block loses "not built, not shipped yet" and gains the `nfpm.yaml`, and the "Names"
  and "Paths" bullets take the exception; the Decisions table gets the row for the package name and the flat layout; the
  `pihero` section's MOTD paragraph describes the banner through `hero` with the mood rule and the measured cost,
  replacing "rendered once at build time" and "nothing beyond Python".
- [README.md](../../../README.md): a `kaomoji` row in the package table.
- [packages/kaomoji/README.md](../../../packages/kaomoji/README.md): that `apt install kaomoji` from the Pi Hero
  repository puts the three faces on `PATH`, and where the engine lands.
- [app-conventions.md](../../app-conventions.md): one bullet: an app that shows a face runs `/usr/bin/hero`, `wizard`, or
  `visitor` from `kaomoji`, which `pihero` brings along, and ships no copy of its own.

## Follow-up in choam.de

Handed over to the other repository, not done here: in `docs/hosts/pi/shishakli/user-data.tmpl`, the `write_files`
entry for `/usr/local/bin/hero` and its comment go, and `/usr/local/lib/hero-lcd/run` execs `/usr/bin/hero --mood neutral
--animate --color`, an interface the current `hero` still accepts. The README's "The hero on tty1" table follows. Nothing
else changes on any host: every one installs `pihero` from the same signed repository and gets the cast with it.

## Out of scope

- `kaomoji-gif` as a generic renderer of a command given after `--`.
- Apps owning their faces; `wizard` and `visitor` stay in the cast until an app needs to change one.
- A colored or animated MOTD.

QA for the whole change: tiers 0 and 1 green on both platforms, tier 2 green, `make deploy` to busy-screen.local, then
`ssh busy-screen.local` shows the happy hero over its four lines, a failed unit turns it sad, and the ssh-tier tests pass
there.
