# Checkpoints: the real boards a release is proven on

Date: 2026-10-02. Status: approved design, ready for planning. Implements the handover "pihero owns the hardware
checkpoints" from the fleet repository (2026-10-01).

## Intent

Two real boards, one per image, are the release's hardware step: a 64-bit Raspberry Pi Zero 2 W on Wi-Fi with the USB
gadget, and a 32-bit Raspberry Pi Zero, the hardware floor, on a USB Ethernet hub. The fleet repository keeps what the
boards are (runbooks, device templates, secrets, ssh keys); this repository owns the process: when they are reflashed and
tested, and what a release requires of them. Their device directories live outside this checkout.

Today three things get in the way. A session that wants to flash one of them has to invent a device directory under
`devices/`, which is how `devices/gadget-test` once came to exist. The ssh target runs every package's installed tests, so
a board without `pihero-kiosk` or `pihero-usb-gadget` fails those with "not installed" unless the package directories are
listed by hand. And nothing runs the tier against both boards and says which one is unreachable.

Success looks like this: a gitignored `.env` names the directory of device directories and the two boards;
`make flash DEVICE=checkpoint32 DISK=disk9` finds the directory there; `uv run pytest -m installed --target=ssh
--target-uri=pi@checkpoint32.local` is green without listing packages, the kiosk's and the gadget's tests skipped as
"not installed on pi@checkpoint32.local"; `make checkpoint` runs the ssh tier against both boards, prints one line per
board, and exits non-zero when one failed or was unreachable; and `docs/testing.md` says all of this generically, so the
public documentation stays self-contained.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Where local paths live | `.env` at the repository root, gitignored, included by the Makefile (`-include .env`) and exported; two keys, `PIHERO_DEVICES=<directory of device directories>` and `CHECKPOINTS=<device names>` | One file a fresh session can find by reading the Makefile; the Makefile already is the operator's entry point; environment variables keep the Python side free of a config parser |
| Name resolution | `flash.device_dir(name)` tries, in order: `name` as a path, `devices/<name>`, `$PIHERO_DEVICES/<name>` (`~` expanded); the error names every place it looked | `devices/` keeps working for the quick start; a name in `.env` beats a path on the command line because the handover's boards are reflashed by name for the rest of their lives |
| What the ssh tier runs | At collection, `--target=ssh` asks the device once for its dpkg status and skips the installed tests of every package the device does not have, reason `<package> is not installed on <uri>`; a test's package is the nearest ancestor directory `build.discover()` would list, whose name is the package's, as `build()` names the `.deb` | The same question `make deploy` asks since #26, so the two agree on what a board has; a skip with the package in its reason tells the release checklist what was not proven, which a deselect would hide |
| The checkpoint command | `python -m pihero_testkit.checkpoint [name...]`, names defaulting to `$CHECKPOINTS`; for each name: `pi@<name>.local`, a reachability probe (`ssh -o BatchMode=yes -o ConnectTimeout=5 … true`), then the ssh tier in a subprocess; one summary line per board; exit 1 when any board failed or was unreachable; `make checkpoint` runs it | The release checklist wants one command and one verdict; the probe separates "the board is off" from "a test failed"; `pi` is the user every device file and runbook uses; the name is the hostname because a device directory is named after its device, and reading `hostname:` from `user-data` would fail whenever the directory holds only the template the fleet renders before a flash and deletes after it |
| Release | `docs/testing.md` "Release" gains the hardware step: reflash both checkpoints from their device directories, wait for the first boot, forget the old host keys, `make checkpoint`; `make release` stays as it is | Flashing swaps cards by hand, so it cannot sit inside `make release`; the doc is the checklist |
| How the boards are described | Generically: a 64-bit Zero 2 W on Wi-Fi with the gadget; a 32-bit Zero on a USB Ethernet hub, which never takes the gadget | The public docs must not depend on the fleet repository; the rule about the gadget is a property of the Zero's one USB controller, not of a host name |

## Components

- `.env` (new, gitignored; `.gitignore` gains `.env`), [Makefile](../../../Makefile): `-include .env`, `export PIHERO_DEVICES CHECKPOINTS`,
  a `checkpoint` target.
- [flash.py](../../../testkit/src/pihero_testkit/flash.py): `device_dir` with the third place to look and the fuller error.
- [build.py](../../../testkit/src/pihero_testkit/build.py): `is_package(directory) -> bool`, what `discover()` tests.
- [ssh.py](../../../testkit/src/pihero_testkit/ssh.py): `installed_packages(uri) -> set[str]` over the status query
  `deploy.STATUS_QUERY` parses with `deploy.installed`.
- [plugin.py](../../../testkit/src/pihero_testkit/plugin.py): `package_of(path) -> str | None`; `pytest_collection_modifyitems`
  skips for `--target=ssh`.
- `checkpoint.py` (new): `boards(argv)`, `uri_for(name)`, `reachable(uri)`, `run_tier(uri)`, `main(argv)`.
- Tests, all tier 0: `testkit/tests/test_flash.py` (`TestDeviceDir` grows), `testkit/tests/test_build.py` (`TestIsPackage`),
  `testkit/tests/test_ssh.py` (new), `testkit/tests/test_plugin.py` (new, pytester in process with a fake
  `installed_packages`), `testkit/tests/test_checkpoint.py` (new, fake `subprocess.run`).
- Docs: [testing.md](../../testing.md) (tiers table's ssh row, "Real devices", "Release"), [README.md](../../../README.md)
  (Development: `.env`, `make checkpoint`, Release), [devices/README.md](../../../devices/README.md) (Flash: the third form of
  `DEVICE=`), [design.md](../../design.md) (Operations: "Release is a tag", "Development loop").

## Failure modes

- `.env` missing: `make flash DEVICE=checkpoint` fails with the three places it looked, `make checkpoint` with the usage
  line naming `CHECKPOINTS`; nothing else changes, since every other target ignores both variables.
- A board is reachable but `pihero` is not installed: the probe passes, the tier exits non-zero on the version fixture's
  `SystemExit`, the board is reported as failed. Right: a checkpoint without `pihero` is a flash that went wrong.
- A package's tests under a directory `discover()` does not list, such as the testkit's own: never skipped by the filter,
  as before.
- `ssh` cannot reach the device at collection: the same `SystemExit` the version fixture raises today, only earlier.

## Follow-ups

1. The first reflash of both checkpoints under this process is the next release; record the measured first-boot times
   in the fleet runbooks, not here.
2. Letting the device file name its user instead of assuming `pi`, if a device file ever does.
