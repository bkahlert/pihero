# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Gemini CLI, and others) when working with code in this
repository. `CLAUDE.md` and `GEMINI.md` are symlinks to it; edit this file only.

Pi Hero 2 turns a Raspberry Pi into a discoverable, reachable device with Debian packages, one cloud-init file per device,
and a Mac-side harness that proves every package before a Pi is involved. The [README](README.md) is the entry point and the
documents its Development section links are the source of truth. This file says which one answers what and holds only what
is written nowhere else.

## Where to look

- Setup, the change loop, contributing (pull requests, commit messages), and releasing:
  [README.md](README.md) "Development", then [docs/operations.md](docs/operations.md) "Set up the Mac once",
  "Change a package", and "Release".
- Tiers, targets, pytest options, and how to write a test (markers, fixtures, `load_script`, what differs between a
  container, the VM, and a Pi): [docs/testing.md](docs/testing.md) "Tiers" and "Writing tests".
- Package anatomy, names and paths, how a `.deb` and its maintainer scripts are generated, the version scheme:
  [docs/design.md](docs/design.md) "Repository layout and package anatomy".
- The rules every package keeps (tests come first, hardware floor, stdlib-only Python, defaults never share a file with
  overrides, render at boot, reboots requested never taken, symmetric removal, no dependency on app units):
  [docs/design.md](docs/design.md) "Goals and constraints", "Configuration contract", and "Operations". A change that
  breaks one needs a decision recorded there, not a workaround.
- A boot-time symptom on a Pi: [docs/raspberry-pi-os.md](docs/raspberry-pi-os.md) before concluding it is a Pi Hero bug.
- Device-file keys: [devices/README.md](devices/README.md). Apps built on top:
  [docs/app-conventions.md](docs/app-conventions.md).

## Everything has tests

Every change to behaviour ships with automated tests in the same change; without them, it is not done. Pick the lightest
tier that exercises the behaviour: pure logic in a tier-0 unit test, install and systemd unit behaviour in tier 1, only
what needs a real boot in tier 2; tests of the harness's own modules go in [testkit/tests](testkit/tests), marked `tier0`.
Lightweight is not shallow: a dropped assertion, a mocked subject, or a unit test that cannot fail for the real defect is
a quality cut, not an optimisation. Where a behaviour cannot be tested below real hardware, record the gap and the manual
check in [docs/testing.md](docs/testing.md) "Real devices", as the gadget's postinst and purge are.

## Keeping the docs true

Design specs go to [docs/superpowers/specs](docs/superpowers/specs) and implementation plans to
[docs/superpowers/plans](docs/superpowers/plans), named `YYYY-MM-DD-<topic>[-design].md`; once shipped, the decision and
its reason move into [docs/design.md](docs/design.md). Each package has a section in [docs/design.md](docs/design.md); a change to what it does, why, or what was measured goes
there in the same change. A new or changed command updates [docs/operations.md](docs/operations.md); a new or changed
device-file key updates [devices/README.md](devices/README.md). Apps in other repositories depend on `pihero-testkit`
pinned to a tag, so its fixtures, markers, CLI options, and `load_script` are an API, and changing them breaks those
repositories.
