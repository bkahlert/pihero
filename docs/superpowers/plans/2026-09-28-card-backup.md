# Card Backup and Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `make backup` images an SD card into `backups/<host>-<date>.img.xz` with a sidecar, and `make restore` writes such an image back onto a card of the same size or larger and verifies it.

**Architecture:** Two Python modules in the testkit next to `flash.py`, launched through `make` like `flash`. The raw-disk helpers of `flash.py` (diskutil lookups, `authopen`, mount, unmount, eject) move into a new `disk.py` that also lists the cards present; a tiny `prompt.py` asks on the terminal for what `make` was not given. Backup reads the card read-only into an xz stream while hashing; restore is `flash.write_image` plus `flash.read_back` on a backup image, with a size check from the sidecar before anything is written.

**Tech Stack:** Python 3.13 standard library (`lzma`, `hashlib`, `plistlib`, `tomllib`, `argparse`), macOS `diskutil` and `/usr/libexec/authopen`, pytest, GNU make.

**Spec:** [docs/superpowers/specs/2026-09-28-card-backup-design.md](../specs/2026-09-28-card-backup-design.md)

## Global Constraints

- Testkit code is Python 3.13+ standard library; no new dependency in `testkit/pyproject.toml` or the `Brewfile`.
- The commands run on macOS only and say so on any other platform; the tests never call `diskutil` or `authopen`, because CI runs on Linux.
- Names: image `backups/<host>-<YYYY-MM-DD>.img.xz`, sidecar `backups/<host>-<YYYY-MM-DD>.toml` with exactly the keys `size` (int, decompressed bytes) and `sha256` (hex of the decompressed image). `backups/` is gitignored.
- Backup opens the card with `os.O_RDONLY` and never writes to it. Restore refuses a card whose `TotalSize` is below the sidecar's `size` before opening it.
- Prompts appear only for arguments `make` did not pass; the restore confirmation is skipped when both `IMAGE` and `DISK` were given. Errors are `SystemExit` with a message, as everywhere in the testkit.
- `flash.py` keeps `write_image`, `read_back`, `say`, `CHUNK`, `SECTOR`, and its behaviour; only the disk helpers move.
- Tests: one class per subject, names are claims, tests first and helpers last in every file, the result stored before asserting (`~/.config/agents/rules/testing.md`). Comments say only what the code cannot. Markdown references to files are links.
- Work on branch `feat/card-backup`, never on `main`. Every commit ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Commands run from the repository root. Run single test files with `uv run pytest testkit/tests/<file>.py -q`; `make test-tier0` additionally runs the static checks, which need the podman machine.

## Review Focus

1. Backup must open the card read-only; a wrong flag turns the insurance tool into the thing that destroys the card (Task 3, `TestBackup.test_opens_the_card_read_only`).
2. A replacement card a few megabytes smaller than the image must be refused before the card is opened, not fail halfway through a write (Task 4, `TestRestore.test_refuses_a_smaller_card_before_opening_it`).
3. Ctrl-C during a backup must leave no half-written image that a later restore could pick from the list (Task 3, `TestBackup.test_removes_the_partial_image_on_interrupt`).
4. `NAME=../x` or a name with a slash must be refused, never turned into a path outside `backups/` (Task 3, `TestImageName.test_refuses_a_name_that_is_not_a_file_name`).
5. Under `make`, `--disk=""` arrives as an empty string and must mean "ask", never "a disk called empty string" (Task 2, `TestCard.test_asks_when_the_identifier_is_empty`).

---

### Task 1: `prompt.py`, terminal questions

**Files:**
- Create: `testkit/src/pihero_testkit/prompt.py`
- Create: `testkit/tests/test_prompt.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `prompt.choose(title: str, options: list[str], read=input) -> int` (index into `options`), `prompt.confirm(question: str, read=input) -> bool`, `prompt.ask(question: str, read=input) -> str` (first non-empty answer). `read` is any callable taking the prompt string and returning the line typed.

- [ ] **Step 1: Write the failing tests**

Create `testkit/tests/test_prompt.py`:

```python
import pytest

from pihero_testkit import prompt

pytestmark = pytest.mark.tier0


class TestChoose:
    def test_returns_the_index_of_the_number_entered(self):
        index = prompt.choose("Card:", ["a", "b", "c"], read=answers("3"))

        assert index == 2

    def test_returns_the_first_on_enter(self):
        index = prompt.choose("Card:", ["a", "b"], read=answers(""))

        assert index == 0

    def test_asks_again_on_a_line_that_is_not_a_listed_number(self):
        index = prompt.choose("Card:", ["a", "b"], read=answers("x", "9", "0", "2"))

        assert index == 1

    def test_prints_the_title_and_numbered_options(self, capsys):
        prompt.choose("Card:", ["disk9  SD  31.9 GB", "disk10  SD  63.9 GB"], read=answers("1"))

        out = capsys.readouterr().out
        assert out == "Card:\n  1) disk9  SD  31.9 GB\n  2) disk10  SD  63.9 GB\n"


class TestConfirm:
    def test_accepts_y(self):
        result = prompt.confirm("Go?", read=answers("y"))

        assert result is True

    def test_accepts_yes_in_any_case(self):
        result = prompt.confirm("Go?", read=answers("YES"))

        assert result is True

    def test_rejects_enter(self):
        result = prompt.confirm("Go?", read=answers(""))

        assert result is False

    def test_rejects_anything_else(self):
        result = prompt.confirm("Go?", read=answers("n"))

        assert result is False


class TestAsk:
    def test_returns_the_first_non_empty_answer(self):
        answer = prompt.ask("Name", read=answers("", "   ", "mypi"))

        assert answer == "mypi"


def answers(*lines: str):
    it = iter(lines)
    return lambda _prompt: next(it)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest testkit/tests/test_prompt.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'pihero_testkit.prompt'`

- [ ] **Step 3: Write the module**

Create `testkit/src/pihero_testkit/prompt.py`:

```python
"""Questions on the terminal for what make was not given."""

from collections.abc import Callable

Reader = Callable[[str], str]


def choose(title: str, options: list[str], read: Reader = input) -> int:
    """Prints the numbered options and returns the index of the one chosen; Enter picks the first."""
    print(title)
    for number, option in enumerate(options, 1):
        print(f"  {number}) {option}")
    while True:
        answer = read(f"[1-{len(options)}] (1): ").strip()
        if answer == "":
            return 0
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1


def confirm(question: str, read: Reader = input) -> bool:
    return read(f"{question} [y/N]: ").strip().lower() in ("y", "yes")


def ask(question: str, read: Reader = input) -> str:
    while not (answer := read(f"{question}: ").strip()):
        pass
    return answer
```

The spec says `confirm` accepts only `y`; accepting `yes` as well is the same decision read generously, since a person who types the word must not be told no at the moment they restore.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest testkit/tests/test_prompt.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/prompt.py testkit/tests/test_prompt.py
git commit -m "$(cat <<'EOF'
testkit: prompt.py asks on the terminal for what make was not given

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `disk.py`, raw-disk helpers out of `flash.py` plus the card list

**Files:**
- Create: `testkit/src/pihero_testkit/disk.py`
- Modify: `testkit/src/pihero_testkit/flash.py` (whole file shown below)
- Create: `testkit/tests/test_disk.py`
- Modify: `testkit/tests/test_flash.py` (remove `CARD` and `TestCheckRemovable`)

**Interfaces:**
- Consumes: `prompt.choose` from Task 1.
- Produces: `disk.disk_info(disk: str) -> dict`, `disk.is_card(info: dict) -> bool`, `disk.check_removable(info: dict) -> None`, `disk.cards() -> list[dict]`, `disk.describe(info: dict) -> str`, `disk.card(ident: str) -> dict`, `disk.open_raw(disk: str, flags: int) -> int`, `disk.unmount(disk: str) -> None` (always forced), `disk.eject(disk: str) -> None`, `disk.mount_partition(disk: str, number: int = 1, timeout: float = 60) -> tuple[Path, str]` (mount point and volume name). `flash.mount_bootfs(disk: str) -> Path` stays and keeps its label check.

- [ ] **Step 1: Write the failing tests**

Create `testkit/tests/test_disk.py`:

```python
import pytest

from pihero_testkit import disk

pytestmark = pytest.mark.tier0

CARD = {"DeviceIdentifier": "disk9", "WholeDisk": True, "Internal": False, "RemovableMedia": True, "MediaName": "USB3.0 CRW   -SD", "TotalSize": 31914983424}
BIG_CARD = {**CARD, "DeviceIdentifier": "disk10", "MediaName": "SD Card Reader", "TotalSize": 63864569856}


class TestIsCard:
    def test_accepts_an_external_removable_whole_disk(self):
        result = disk.is_card(CARD)

        assert result is True

    def test_rejects_a_partition(self):
        result = disk.is_card({**CARD, "DeviceIdentifier": "disk9s1", "WholeDisk": False})

        assert result is False

    def test_rejects_the_internal_disk(self):
        result = disk.is_card({**CARD, "DeviceIdentifier": "disk0", "Internal": True, "RemovableMedia": False})

        assert result is False

    def test_rejects_an_external_drive_with_fixed_media(self):
        result = disk.is_card({**CARD, "RemovableMedia": False, "MediaName": "Samsung T7"})

        assert result is False


class TestCheckRemovable:
    def test_accepts_an_external_removable_whole_disk(self):
        result = disk.check_removable(CARD)

        assert result is None

    def test_rejects_the_internal_disk(self):
        with pytest.raises(SystemExit, match="disk0 .* not a removable disk"):
            disk.check_removable({**CARD, "DeviceIdentifier": "disk0", "Internal": True, "RemovableMedia": False, "MediaName": "APPLE SSD"})

    def test_rejects_an_external_drive_with_fixed_media(self):
        with pytest.raises(SystemExit, match="not a removable disk"):
            disk.check_removable({**CARD, "RemovableMedia": False})

    def test_rejects_a_partition(self):
        with pytest.raises(SystemExit, match="disk9s1 is a partition"):
            disk.check_removable({**CARD, "DeviceIdentifier": "disk9s1", "WholeDisk": False})


class TestDescribe:
    def test_names_identifier_media_and_size(self):
        line = disk.describe(CARD)

        assert line == "disk9  USB3.0 CRW   -SD  31.9 GB"


class TestCard:
    def test_returns_the_named_disk_after_the_removable_check(self, monkeypatch):
        monkeypatch.setattr(disk, "disk_info", lambda ident: {**CARD, "DeviceIdentifier": ident})

        info = disk.card("disk9")

        assert info["DeviceIdentifier"] == "disk9"

    def test_rejects_a_named_disk_that_is_no_card(self, monkeypatch):
        monkeypatch.setattr(disk, "disk_info", lambda ident: {**CARD, "DeviceIdentifier": ident, "Internal": True, "RemovableMedia": False})

        with pytest.raises(SystemExit, match="not a removable disk"):
            disk.card("disk0")

    def test_asks_when_the_identifier_is_empty(self, monkeypatch):
        monkeypatch.setattr(disk, "cards", lambda: [CARD, BIG_CARD])
        monkeypatch.setattr(disk.prompt, "choose", lambda title, options: 1)

        info = disk.card("")

        assert info is BIG_CARD

    def test_exits_without_a_card_present(self, monkeypatch):
        monkeypatch.setattr(disk, "cards", lambda: [])

        with pytest.raises(SystemExit, match="no SD card found"):
            disk.card("")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest testkit/tests/test_disk.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'pihero_testkit.disk'`

- [ ] **Step 3: Write `disk.py`**

Create `testkit/src/pihero_testkit/disk.py`:

```python
"""Raw access to SD cards on macOS.

The raw disk is opened through authopen, which asks for authorization and hands the descriptor back over a socket, the way
Raspberry Pi Imager does; a plain open is refused even for root.
"""

import plistlib
import socket
import subprocess
import time
from pathlib import Path

from . import prompt

AUTHOPEN = "/usr/libexec/authopen"


def disk_info(disk: str) -> dict:
    out = subprocess.run(["diskutil", "info", "-plist", disk], capture_output=True, check=True).stdout
    return plistlib.loads(out)


def is_card(info: dict) -> bool:
    return bool(info.get("WholeDisk")) and bool(info.get("RemovableMedia")) and not info.get("Internal")


def check_removable(info: dict) -> None:
    ident = info.get("DeviceIdentifier", "?")
    if not info.get("WholeDisk"):
        raise SystemExit(f"{ident} is a partition; name the whole disk")
    if info.get("Internal") or not info.get("RemovableMedia"):
        raise SystemExit(f"{ident} ({info.get('MediaName', 'unknown media')}) is not a removable disk")


def cards() -> list[dict]:
    """Returns the info of every external, physical, removable whole disk, in diskutil's order."""
    out = subprocess.run(["diskutil", "list", "-plist", "external", "physical"], capture_output=True, check=True).stdout
    infos = (disk_info(ident) for ident in plistlib.loads(out).get("WholeDisks", []))
    return [info for info in infos if is_card(info)]


def describe(info: dict) -> str:
    return f"{info.get('DeviceIdentifier', '?')}  {info.get('MediaName', 'unknown media').strip()}  {info.get('TotalSize', 0) / 1e9:.1f} GB"


def card(ident: str) -> dict:
    """Returns the info of the named card, or of the one chosen from the cards present when ident is empty."""
    if ident:
        info = disk_info(ident)
        check_removable(info)
        return info
    found = cards()
    if not found:
        raise SystemExit("no SD card found; insert one and check with: diskutil list external")
    return found[prompt.choose("Card:", [describe(info) for info in found])]


def open_raw(disk: str, flags: int) -> int:
    dev = f"/dev/r{disk}"
    parent, child = socket.socketpair()
    with subprocess.Popen([AUTHOPEN, "-stdoutpipe", "-o", str(flags), dev], stdout=child.fileno()) as proc:
        child.close()
        _, fds, _, _ = socket.recv_fds(parent, 1024, 1)
        parent.close()
    if not fds:
        raise SystemExit(f"authopen did not open {dev} (exit {proc.returncode}); authorization denied?")
    return fds[0]


def unmount(disk: str) -> None:
    subprocess.run(["diskutil", "unmountDisk", "force", disk], check=True, capture_output=True)


def eject(disk: str) -> None:
    subprocess.run(["diskutil", "eject", disk], check=True, capture_output=True)


def mount_partition(disk: str, number: int = 1, timeout: float = 60) -> tuple[Path, str]:
    """Mounts the disk and returns the partition's mount point and volume name."""
    subprocess.run(["diskutil", "mountDisk", disk], capture_output=True, check=False)
    deadline = time.monotonic() + timeout
    while True:
        info = disk_info(f"{disk}s{number}")
        if info.get("MountPoint"):
            return Path(info["MountPoint"]), info.get("VolumeName", "")
        if time.monotonic() > deadline:
            raise SystemExit(f"{disk}s{number} did not mount")
        time.sleep(1)
```

- [ ] **Step 4: Rewrite `flash.py` on top of `disk.py`**

Replace the whole of `testkit/src/pihero_testkit/flash.py` with:

```python
"""Writes Raspberry Pi OS Lite onto an SD card and puts a device's cloud-init files on its boot partition.

macOS only. Writes are sector aligned and read back for verification.
"""

import hashlib
import lzma
import os
import re
import shutil
import sys
import time
from pathlib import Path

from . import prepare
from .disk import check_removable, disk_info, eject, mount_partition, open_raw, unmount

CHUNK = 4 << 20
SECTOR = 512
BOOT_LABEL = "bootfs"
DEVICE_FILES = ("user-data", "network-config", "meta-data")
REGULATORY_DOMAIN = re.compile(r"""^\s*regulatory-domain:\s*["']?(?P<code>[A-Z]{2})["']?\s*$""", re.MULTILINE)
CMDLINE_REGDOM = re.compile(r"\s*cfg80211\.ieee80211_regdom=\S*")


def device_dir(name: str) -> Path:
    path = Path(name) if Path(name).is_dir() else Path.cwd() / "devices" / name
    if not (path / "user-data").is_file():
        raise SystemExit(f"{path} has no user-data")
    return path


def write_image(fd: int, image: Path, report=lambda message: None) -> tuple[int, str]:
    """Streams the xz image onto fd in sector-aligned chunks. Returns size and sha256 of the uncompressed image."""
    digest = hashlib.sha256()
    total = 0
    started = time.monotonic()
    next_report = 256 << 20
    with lzma.open(image, "rb") as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
            total += len(chunk)
            chunk += b"\0" * (-len(chunk) % SECTOR)
            view = memoryview(chunk)
            while view:
                view = view[os.write(fd, view) :]
            if total >= next_report:
                report(f"written {total >> 20} MiB ({total / (time.monotonic() - started) / 1e6:.0f} MB/s)")
                next_report += 256 << 20
    return total, digest.hexdigest()


def read_back(fd: int, size: int) -> str:
    """Returns the sha256 of the first size bytes on fd, reading whole sectors as raw disks require."""
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    remaining = size + (-size % SECTOR)
    hashed = 0
    while remaining:
        data = os.read(fd, min(CHUNK, remaining))
        if not data:
            raise SystemExit(f"short read while verifying: {remaining} bytes left")
        remaining -= len(data)
        take = min(len(data), size - hashed)
        digest.update(data[:take])
        hashed += take
    return digest.hexdigest()


def mount_bootfs(disk: str) -> Path:
    mount_point, label = mount_partition(disk)
    if label != BOOT_LABEL:
        raise SystemExit(f"{disk}s1 is {label!r}, expected {BOOT_LABEL!r}")
    return mount_point


def copy_device_files(device: Path, bootfs: Path) -> list[str]:
    copied = []
    for name in DEVICE_FILES:
        if (device / name).is_file():
            shutil.copyfile(device / name, bootfs / name)
            copied.append(name)
    return copied


def regulatory_domain(network_config: str) -> str | None:
    match = REGULATORY_DOMAIN.search(network_config)
    return match["code"] if match else None


def with_regulatory_domain(cmdline: str, code: str) -> str:
    """Returns the one-line cmdline with cfg80211.ieee80211_regdom=<code> as its last word, replacing an earlier one."""
    return CMDLINE_REGDOM.sub("", cmdline.strip()) + f" cfg80211.ieee80211_regdom={code}\n"


def flash(device: Path, disk: str) -> None:
    info = disk_info(disk)
    check_removable(info)
    say(f"{disk}: {info.get('MediaName', '').strip()} {info.get('TotalSize', 0) / 1e9:.1f} GB")
    config = prepare.lock()["raspios"]
    image = prepare.download(config["url"], config["sha256"])
    unmount(disk)
    fd = open_raw(disk, os.O_RDWR)
    try:
        say(f"writing {image.name} ...")
        size, expected = write_image(fd, image, say)
        say(f"verifying {size >> 20} MiB ...")
        actual = read_back(fd, size)
    finally:
        os.close(fd)
    if actual != expected:
        raise SystemExit(f"verification failed: wrote {expected}, read {actual}")
    bootfs = mount_bootfs(disk)
    copied = copy_device_files(device, bootfs)
    say(f"copied {', '.join(copied)} from {device} to {bootfs}")
    # Raspberry Pi OS brings Wi-Fi up on the first boot only when the regulatory domain is already on the kernel command line;
    # netplan writes it there during that boot, too late. Imager does the same at flash time.
    code = regulatory_domain((device / "network-config").read_text()) if "network-config" in copied else None
    if code:
        cmdline = bootfs / "cmdline.txt"
        cmdline.write_text(with_regulatory_domain(cmdline.read_text(), code))
        say(f"set the Wi-Fi regulatory domain {code} in cmdline.txt")
    eject(disk)
    say(f"ejected {disk}; insert the card into the Raspberry Pi and power it on")


def say(message: str) -> None:
    print(f"  {message}", file=sys.stderr, flush=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m pihero_testkit.flash DEVICE DISK   (e.g. checkpoint disk9; see: diskutil list external)", file=sys.stderr)
        return 2
    if sys.platform != "darwin":
        print("flash is macOS only", file=sys.stderr)
        return 2
    flash(device_dir(argv[0]), argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

What changed against the previous file: the imports `plistlib`, `socket`, `subprocess`, and the `AUTHOPEN` constant are gone; `disk_info`, `check_removable`, `open_raw` were removed and are imported; `mount_bootfs` now wraps `mount_partition` and keeps the label check; `flash()` calls `unmount(disk)`, `open_raw(disk, os.O_RDWR)`, and `eject(disk)` instead of inline `subprocess.run` calls. Everything else is byte-identical.

- [ ] **Step 5: Move the removable-check tests out of `test_flash.py`**

In `testkit/tests/test_flash.py`, delete the line

```python
CARD = {"DeviceIdentifier": "disk9", "WholeDisk": True, "Internal": False, "RemovableMedia": True, "MediaName": "USB3.0 CRW   -SD"}
```

and the whole `class TestCheckRemovable:` block (four tests). They live in `test_disk.py` now. Leave the blank lines tidy: two between top-level definitions.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest testkit/tests/test_disk.py testkit/tests/test_flash.py testkit/tests/test_prompt.py -q`
Expected: all pass; `test_flash.py` runs its remaining classes (`TestWriteImage`, `TestReadBack`, `TestDeviceDir`, `TestRegulatoryDomain`, `TestWithRegulatoryDomain`, `TestCopyDeviceFiles`).

Also run: `uv run python -c "from pihero_testkit import flash, disk; print(flash.mount_bootfs, disk.card)"`
Expected: prints two function reprs, no import error.

- [ ] **Step 7: Commit**

```bash
git add testkit/src/pihero_testkit/disk.py testkit/src/pihero_testkit/flash.py testkit/tests/test_disk.py testkit/tests/test_flash.py
git commit -m "$(cat <<'EOF'
testkit: move the raw-disk helpers out of flash.py into disk.py, list the cards present

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `backup.py`, `make backup`, and `backups/` ignored

**Files:**
- Create: `testkit/src/pihero_testkit/backup.py`
- Create: `testkit/tests/test_backup.py`
- Modify: `Makefile` (after the `flash` target)
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `disk.card`, `disk.mount_partition`, `disk.unmount`, `disk.open_raw`, `disk.eject` (Task 2); `prompt.ask` (Task 1); `flash.CHUNK`, `flash.say`.
- Produces: `backup.BACKUPS: Path` (`Path("backups")`), `backup.hostname(user_data: str) -> str | None`, `backup.card_hostname(ident: str) -> str | None`, `backup.image_name(host: str, day: date) -> str`, `backup.sidecar_for(image: Path) -> Path`, `backup.dump(fd: int, image: Path, total: int, report=...) -> tuple[int, str]`, `backup.write_sidecar(image: Path, size: int, sha256: str) -> Path`, `backup.backup(info: dict, host: str, day: date, backups: Path = BACKUPS) -> Path`, `backup.main(argv: list[str]) -> int`. Task 4 imports `BACKUPS`, `sidecar_for`, and `write_sidecar` (the last in tests).

- [ ] **Step 1: Write the failing tests**

Create `testkit/tests/test_backup.py`:

```python
import hashlib
import lzma
import os
import tomllib
from datetime import date
from pathlib import Path

import pytest

from pihero_testkit import backup, flash

pytestmark = pytest.mark.tier0

CARD = {"DeviceIdentifier": "disk9", "WholeDisk": True, "Internal": False, "RemovableMedia": True, "MediaName": "USB3.0 CRW   -SD", "TotalSize": 31914983424}
DAY = date(2026, 9, 28)
SAMPLE = Path("devices/sample/user-data")


class TestHostname:
    def test_reads_an_unquoted_hostname(self):
        host = backup.hostname("#cloud-config\nhostname: mypi\nmanage_etc_hosts: true\n")

        assert host == "mypi"

    def test_reads_a_quoted_hostname(self):
        host = backup.hostname('hostname: "my-pi"\n')

        assert host == "my-pi"

    def test_ignores_an_indented_key(self):
        host = backup.hostname("users:\n  - name: pi\n    hostname: nope\n")

        assert host is None

    def test_ignores_a_commented_key(self):
        host = backup.hostname("# hostname: nope\ntimezone: Europe/Berlin\n")

        assert host is None

    def test_is_none_without_a_hostname(self):
        host = backup.hostname("#cloud-config\ntimezone: Europe/Berlin\n")

        assert host is None

    def test_reads_the_sample_device_file(self):
        host = backup.hostname(SAMPLE.read_text())

        assert host == "sample"


class TestImageName:
    def test_joins_host_and_iso_date(self):
        name = backup.image_name("mypi", DAY)

        assert name == "mypi-2026-09-28.img.xz"

    def test_refuses_a_name_that_is_not_a_file_name(self):
        with pytest.raises(SystemExit, match="not a valid name"):
            backup.image_name("../mypi", DAY)

    def test_refuses_a_name_with_spaces(self):
        with pytest.raises(SystemExit, match="not a valid name"):
            backup.image_name("my pi", DAY)


class TestSidecarFor:
    def test_replaces_the_image_suffixes_with_toml(self):
        sidecar = backup.sidecar_for(Path("backups/mypi-2026-09-28.img.xz"))

        assert sidecar == Path("backups/mypi-2026-09-28.toml")


class TestDump:
    def test_round_trips_through_write_image(self, tmp_path):
        payload = os.urandom(flash.CHUNK + 4096) + bytes(flash.CHUNK) + b"tail"
        card = tmp_path / "card"
        card.write_bytes(payload)
        image = tmp_path / "pi.img.xz"

        fd = os.open(card, os.O_RDONLY)
        try:
            size, digest = backup.dump(fd, image, len(payload))
        finally:
            os.close(fd)

        assert size == len(payload)
        assert digest == hashlib.sha256(payload).hexdigest()
        restored = tmp_path / "restored"
        fd = os.open(restored, os.O_RDWR | os.O_CREAT)
        try:
            written = flash.write_image(fd, image)
        finally:
            os.close(fd)
        assert written == (size, digest)
        assert restored.read_bytes()[: len(payload)] == payload

    def test_compresses_zeros_to_almost_nothing(self, tmp_path):
        card = tmp_path / "card"
        card.write_bytes(bytes(8 * flash.CHUNK))
        image = tmp_path / "pi.img.xz"

        fd = os.open(card, os.O_RDONLY)
        try:
            backup.dump(fd, image, 8 * flash.CHUNK)
        finally:
            os.close(fd)

        assert image.stat().st_size < 64 << 10


class TestWriteSidecar:
    def test_writes_size_and_sha256_as_toml(self, tmp_path):
        image = tmp_path / "mypi-2026-09-28.img.xz"

        sidecar = backup.write_sidecar(image, 31914983424, "ab" * 32)

        assert sidecar == tmp_path / "mypi-2026-09-28.toml"
        assert tomllib.loads(sidecar.read_text()) == {"size": 31914983424, "sha256": "ab" * 32}


class TestBackup:
    def test_writes_image_and_sidecar_then_ejects(self, tmp_path, monkeypatch):
        payload = os.urandom(3 * flash.SECTOR)
        card = fake_card(tmp_path, payload, monkeypatch)
        ejected = []
        monkeypatch.setattr(backup.disk, "eject", ejected.append)

        image = backup.backup({**CARD, "TotalSize": len(payload)}, "mypi", DAY, tmp_path / "backups")

        assert image == tmp_path / "backups" / "mypi-2026-09-28.img.xz"
        with lzma.open(image) as stream:
            assert stream.read() == payload
        assert tomllib.loads(backup.sidecar_for(image).read_text()) == {"size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        assert ejected == ["disk9"]
        assert card.read_bytes() == payload

    def test_opens_the_card_read_only(self, tmp_path, monkeypatch):
        fake_card(tmp_path, bytes(flash.SECTOR), monkeypatch)
        opened = []
        monkeypatch.setattr(backup.disk, "open_raw", lambda ident, flags: opened.append(flags) or os.open(tmp_path / "card", flags))

        backup.backup({**CARD, "TotalSize": flash.SECTOR}, "mypi", DAY, tmp_path / "backups")

        assert opened == [os.O_RDONLY]

    def test_refuses_an_existing_image_untouched(self, tmp_path):
        backups = tmp_path / "backups"
        backups.mkdir()
        existing = backups / "mypi-2026-09-28.img.xz"
        existing.write_bytes(b"old")

        with pytest.raises(SystemExit, match="exists"):
            backup.backup(CARD, "mypi", DAY, backups)

        assert existing.read_bytes() == b"old"

    def test_removes_the_partial_image_on_interrupt(self, tmp_path, monkeypatch):
        fake_card(tmp_path, bytes(flash.SECTOR), monkeypatch)
        monkeypatch.setattr(backup, "dump", interrupting_dump)

        with pytest.raises(KeyboardInterrupt):
            backup.backup({**CARD, "TotalSize": flash.SECTOR}, "mypi", DAY, tmp_path / "backups")

        assert list((tmp_path / "backups").iterdir()) == []


def fake_card(tmp_path, payload: bytes, monkeypatch) -> Path:
    card = tmp_path / "card"
    card.write_bytes(payload)
    monkeypatch.setattr(backup.disk, "unmount", lambda ident: None)
    monkeypatch.setattr(backup.disk, "open_raw", lambda ident, flags: os.open(card, flags))
    monkeypatch.setattr(backup.disk, "eject", lambda ident: None)
    return card


def interrupting_dump(fd, image, total, report=None):
    image.write_bytes(b"partial")
    raise KeyboardInterrupt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest testkit/tests/test_backup.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'pihero_testkit.backup'`

- [ ] **Step 3: Write `backup.py`**

Create `testkit/src/pihero_testkit/backup.py`:

```python
"""Images an SD card into backups/<host>-<date>.img.xz with a sidecar naming the image's size and sha256.

macOS only. The card is opened read-only and never written.
"""

import argparse
import hashlib
import lzma
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

from . import disk, prompt
from .flash import CHUNK, say

BACKUPS = Path("backups")
HOSTNAME = re.compile(r"""^hostname:\s*["']?(?P<name>[A-Za-z0-9][A-Za-z0-9.-]*)["']?\s*$""", re.MULTILINE)
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PRESET = 0
REPORT_EVERY = 256 << 20


def hostname(user_data: str) -> str | None:
    match = HOSTNAME.search(user_data)
    return match["name"] if match else None


def card_hostname(ident: str) -> str | None:
    """Returns the hostname from the cloud-init user-data on the card's first partition, if there is one."""
    mount_point, _ = disk.mount_partition(ident)
    user_data = mount_point / "user-data"
    return hostname(user_data.read_text()) if user_data.is_file() else None


def image_name(host: str, day: date) -> str:
    if not NAME.match(host):
        raise SystemExit(f"{host!r} is not a valid name; use letters, digits, '.', '_', and '-'")
    return f"{host}-{day:%Y-%m-%d}.img.xz"


def sidecar_for(image: Path) -> Path:
    return image.with_name(image.name.removesuffix(".img.xz") + ".toml")


def dump(fd: int, image: Path, total: int, report=lambda message: None) -> tuple[int, str]:
    """Reads fd to its end into the xz image. Returns size and sha256 of the bytes read."""
    digest = hashlib.sha256()
    size = 0
    started = time.monotonic()
    next_report = REPORT_EVERY
    with lzma.open(image, "wb", preset=PRESET) as out:
        while chunk := os.read(fd, CHUNK):
            digest.update(chunk)
            out.write(chunk)
            size += len(chunk)
            if size >= next_report:
                report(f"read {size >> 20} MiB of {total >> 20} ({100 * size // total}%, {size / (time.monotonic() - started) / 1e6:.0f} MB/s)")
                next_report += REPORT_EVERY
    return size, digest.hexdigest()


def write_sidecar(image: Path, size: int, sha256: str) -> Path:
    sidecar = sidecar_for(image)
    sidecar.write_text(f"# Decompressed size and sha256 of {image.name}.\nsize = {size}\nsha256 = \"{sha256}\"\n")
    return sidecar


def backup(info: dict, host: str, day: date, backups: Path = BACKUPS) -> Path:
    ident = info["DeviceIdentifier"]
    image = backups / image_name(host, day)
    if image.exists():
        raise SystemExit(f"{image} exists; move it away or pass NAME=")
    backups.mkdir(exist_ok=True)
    total = info["TotalSize"]
    say(f"{ident}: {info.get('MediaName', '').strip()} {total / 1e9:.1f} GB")
    disk.unmount(ident)
    fd = disk.open_raw(ident, os.O_RDONLY)
    try:
        say(f"reading {ident} into {image} ...")
        size, sha256 = dump(fd, image, total, say)
    except BaseException:
        image.unlink(missing_ok=True)
        raise
    finally:
        os.close(fd)
    write_sidecar(image, size, sha256)
    disk.eject(ident)
    say(f"ejected {ident}; {image} restores onto a card of at least {size / 1e9:.1f} GB")
    return image


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Image an SD card into backups/<host>-<date>.img.xz.")
    parser.add_argument("--disk", default="", help="disk identifier such as disk9; asked when empty")
    parser.add_argument("--name", default="", help="name of the Pi; read from the card's user-data when empty")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("backup is macOS only", file=sys.stderr)
        return 2
    info = disk.card(args.disk)
    host = args.name or card_hostname(info["DeviceIdentifier"]) or prompt.ask("Name for this backup")
    backup(info, host, date.today())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest testkit/tests/test_backup.py -q`
Expected: `17 passed`

- [ ] **Step 5: Add the make target and ignore `backups/`**

In `Makefile`, directly after the `flash` target's last recipe line and before `clean:`, insert:

```makefile
.PHONY: backup
backup: ## image an SD card into backups/<host>-<date>.img.xz (make backup [DISK=disk9] [NAME=host])
	@$(UV) python -m pihero_testkit.backup --disk="$(DISK)" --name="$(NAME)"
```

The recipe line starts with a tab, as every recipe in this file does. Add `NAME ?=` under `DISK ?=` at the top of the file so `make -p` shows the variable next to its siblings.

Append to `.gitignore`:

```
backups/
```

- [ ] **Step 6: Verify the target is wired**

Run: `make help | grep backup`
Expected: one line `  backup         image an SD card into backups/<host>-<date>.img.xz (make backup [DISK=disk9] [NAME=host])`

Run: `make -n backup DISK=disk9 NAME=mypi`
Expected: prints `uv run --frozen python -m pihero_testkit.backup --disk="disk9" --name="mypi"`

Run: `uv run python -m pihero_testkit.backup --help`
Expected: argparse help listing `--disk` and `--name`, exit 0.

Run: `mkdir -p backups && git status --short backups; rmdir backups`
Expected: `git status` prints nothing for `backups`.

- [ ] **Step 7: Commit**

```bash
git add testkit/src/pihero_testkit/backup.py testkit/tests/test_backup.py Makefile .gitignore
git commit -m "$(cat <<'EOF'
testkit: make backup images an SD card into backups/<host>-<date>.img.xz

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `restore.py` and `make restore`

**Files:**
- Create: `testkit/src/pihero_testkit/restore.py`
- Create: `testkit/tests/test_restore.py`
- Modify: `Makefile` (after the `backup` target)

**Interfaces:**
- Consumes: `disk.card`, `disk.describe`, `disk.unmount`, `disk.open_raw`, `disk.eject` (Task 2); `prompt.choose`, `prompt.confirm` (Task 1); `flash.write_image`, `flash.read_back`, `flash.say`; `backup.BACKUPS`, `backup.sidecar_for`, and in tests `backup.write_sidecar` (Task 3).
- Produces: `restore.sidecar(image: Path) -> dict | None`, `restore.images(backups: Path = BACKUPS) -> list[Path]` (newest first), `restore.describe(image: Path) -> str`, `restore.image_for(path: str, backups: Path = BACKUPS) -> Path`, `restore.check_fits(info: dict, size: int) -> None`, `restore.restore(image: Path, info: dict) -> None`, `restore.main(argv: list[str]) -> int`.

- [ ] **Step 1: Write the failing tests**

Create `testkit/tests/test_restore.py`:

```python
import hashlib
import lzma
import os
from pathlib import Path

import pytest

from pihero_testkit import backup, flash, restore

pytestmark = pytest.mark.tier0

CARD = {"DeviceIdentifier": "disk9", "WholeDisk": True, "Internal": False, "RemovableMedia": True, "MediaName": "USB3.0 CRW   -SD", "TotalSize": 31914983424}


class TestCheckFits:
    def test_refuses_a_smaller_card_naming_both_sizes(self):
        with pytest.raises(SystemExit, match=r"disk9 holds 31\.9 GB, the image needs 32\.0 GB"):
            restore.check_fits(CARD, 32_000_000_000)

    def test_accepts_an_equal_card(self):
        result = restore.check_fits(CARD, CARD["TotalSize"])

        assert result is None

    def test_accepts_a_larger_card(self):
        result = restore.check_fits(CARD, 16_000_000_000)

        assert result is None


class TestSidecar:
    def test_reads_size_and_sha256(self, tmp_path):
        image = tmp_path / "mypi-2026-09-28.img.xz"
        backup.write_sidecar(image, 1234, "cd" * 32)

        meta = restore.sidecar(image)

        assert meta == {"size": 1234, "sha256": "cd" * 32}

    def test_is_none_without_a_sidecar(self, tmp_path):
        meta = restore.sidecar(tmp_path / "mypi-2026-09-28.img.xz")

        assert meta is None


class TestImages:
    def test_lists_images_newest_first(self, tmp_path):
        older = tmp_path / "mypi-2026-09-01.img.xz"
        newer = tmp_path / "other-2026-09-28.img.xz"
        older.write_bytes(b"")
        newer.write_bytes(b"")
        os.utime(older, (1_700_000_000, 1_700_000_000))
        os.utime(newer, (1_800_000_000, 1_800_000_000))

        found = restore.images(tmp_path)

        assert found == [newer, older]

    def test_ignores_files_that_are_no_images(self, tmp_path):
        (tmp_path / "mypi-2026-09-28.toml").write_text("size = 1\n")
        (tmp_path / "notes.txt").write_text("")

        found = restore.images(tmp_path)

        assert found == []


class TestDescribe:
    def test_names_the_card_size_the_image_needs(self, tmp_path):
        image = tmp_path / "mypi-2026-09-28.img.xz"
        backup.write_sidecar(image, 31914983424, "ab" * 32)

        line = restore.describe(image)

        assert line == "mypi-2026-09-28.img.xz  needs a 31.9 GB card"

    def test_says_so_without_a_sidecar(self, tmp_path):
        line = restore.describe(tmp_path / "mypi-2026-09-28.img.xz")

        assert line == "mypi-2026-09-28.img.xz  (no sidecar)"


class TestImageFor:
    def test_returns_the_given_path(self, tmp_path):
        given = tmp_path / "mypi-2026-09-28.img.xz"
        given.write_bytes(b"")

        image = restore.image_for(str(given))

        assert image == given

    def test_refuses_a_missing_path(self, tmp_path):
        with pytest.raises(SystemExit, match="not found"):
            restore.image_for(str(tmp_path / "gone.img.xz"))

    def test_asks_when_the_path_is_empty(self, tmp_path, monkeypatch):
        first = tmp_path / "a-2026-09-28.img.xz"
        second = tmp_path / "b-2026-09-01.img.xz"
        first.write_bytes(b"")
        second.write_bytes(b"")
        os.utime(first, (1_800_000_000, 1_800_000_000))
        os.utime(second, (1_700_000_000, 1_700_000_000))
        monkeypatch.setattr(restore.prompt, "choose", lambda title, options: 1)

        image = restore.image_for("", tmp_path)

        assert image == second

    def test_exits_without_images(self, tmp_path):
        with pytest.raises(SystemExit, match="no images"):
            restore.image_for("", tmp_path)


class TestRestore:
    def test_writes_verifies_and_ejects(self, tmp_path, monkeypatch, capsys):
        payload = os.urandom(3 * flash.SECTOR + 100)
        image = backup_image(tmp_path, payload)
        card = fake_card(tmp_path, bytes(len(payload) + 4096), monkeypatch)
        ejected = []
        monkeypatch.setattr(restore.disk, "eject", ejected.append)

        restore.restore(image, {**CARD, "TotalSize": len(payload) + 4096})

        assert card.read_bytes()[: len(payload)] == payload
        assert ejected == ["disk9"]
        assert "raspi-config --expand-rootfs" in capsys.readouterr().err

    def test_does_not_mention_expanding_on_an_equal_card(self, tmp_path, monkeypatch, capsys):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        fake_card(tmp_path, bytes(len(payload)), monkeypatch)

        restore.restore(image, {**CARD, "TotalSize": len(payload)})

        assert "expand-rootfs" not in capsys.readouterr().err

    def test_refuses_a_smaller_card_before_opening_it(self, tmp_path, monkeypatch):
        payload = os.urandom(4 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        fake_card(tmp_path, bytes(len(payload)), monkeypatch)
        opened = []
        monkeypatch.setattr(restore.disk, "open_raw", lambda ident, flags: opened.append(flags))

        with pytest.raises(SystemExit, match="use a larger card"):
            restore.restore(image, {**CARD, "TotalSize": len(payload) - flash.SECTOR})

        assert opened == []

    def test_reports_a_damaged_image(self, tmp_path, monkeypatch):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        backup.write_sidecar(image, len(payload), "00" * 32)
        fake_card(tmp_path, bytes(len(payload)), monkeypatch)

        with pytest.raises(SystemExit, match="damaged"):
            restore.restore(image, {**CARD, "TotalSize": len(payload)})

    def test_restores_without_a_sidecar_and_says_so(self, tmp_path, monkeypatch, capsys):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        backup.sidecar_for(image).unlink()
        card = fake_card(tmp_path, bytes(len(payload)), monkeypatch)

        restore.restore(image, {**CARD, "TotalSize": len(payload)})

        assert card.read_bytes() == payload
        assert "skipping the size and integrity checks" in capsys.readouterr().err


def backup_image(tmp_path, payload: bytes) -> Path:
    image = tmp_path / "mypi-2026-09-28.img.xz"
    with lzma.open(image, "wb") as out:
        out.write(payload)
    backup.write_sidecar(image, len(payload), hashlib.sha256(payload).hexdigest())
    return image


def fake_card(tmp_path, contents: bytes, monkeypatch) -> Path:
    card = tmp_path / "card"
    card.write_bytes(contents)
    monkeypatch.setattr(restore.disk, "unmount", lambda ident: None)
    monkeypatch.setattr(restore.disk, "open_raw", lambda ident, flags: os.open(card, flags))
    monkeypatch.setattr(restore.disk, "eject", lambda ident: None)
    return card
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest testkit/tests/test_restore.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'pihero_testkit.restore'`

- [ ] **Step 3: Write `restore.py`**

Create `testkit/src/pihero_testkit/restore.py`:

```python
"""Writes a backup image onto an SD card and verifies it.

macOS only. Restore is flash without the device files: the same authopen route, the same sector-aligned write, the same
read-back.
"""

import argparse
import os
import sys
import tomllib
from pathlib import Path

from . import disk, prompt
from .backup import BACKUPS, sidecar_for
from .flash import read_back, say, write_image


def sidecar(image: Path) -> dict | None:
    path = sidecar_for(image)
    return tomllib.loads(path.read_text()) if path.is_file() else None


def images(backups: Path = BACKUPS) -> list[Path]:
    """Returns the backup images, newest first."""
    return sorted(backups.glob("*.img.xz"), key=lambda path: path.stat().st_mtime, reverse=True)


def describe(image: Path) -> str:
    meta = sidecar(image)
    return f"{image.name}  needs a {meta['size'] / 1e9:.1f} GB card" if meta else f"{image.name}  (no sidecar)"


def image_for(path: str, backups: Path = BACKUPS) -> Path:
    """Returns the given image, or the one chosen from the images in backups when path is empty."""
    if path:
        image = Path(path)
        if not image.is_file():
            raise SystemExit(f"{image} not found")
        return image
    found = images(backups)
    if not found:
        raise SystemExit(f"no images in {backups}/; run make backup first")
    return found[prompt.choose("Image:", [describe(image) for image in found])]


def check_fits(info: dict, size: int) -> None:
    total = info.get("TotalSize", 0)
    if total < size:
        raise SystemExit(f"{info.get('DeviceIdentifier', '?')} holds {total / 1e9:.1f} GB, the image needs {size / 1e9:.1f} GB; use a larger card")


def restore(image: Path, info: dict) -> None:
    ident = info["DeviceIdentifier"]
    total = info.get("TotalSize", 0)
    meta = sidecar(image)
    if meta:
        check_fits(info, meta["size"])
    else:
        say(f"no {sidecar_for(image).name} next to the image; skipping the size and integrity checks")
    say(f"{ident}: {info.get('MediaName', '').strip()} {total / 1e9:.1f} GB")
    disk.unmount(ident)
    fd = disk.open_raw(ident, os.O_RDWR)
    try:
        say(f"writing {image.name} ...")
        size, written = write_image(fd, image, say)
        if meta and written != meta["sha256"]:
            raise SystemExit(f"{image.name} is damaged: its content hashes to {written}, the sidecar says {meta['sha256']}")
        say(f"verifying {size >> 20} MiB ...")
        read = read_back(fd, size)
    finally:
        os.close(fd)
    if read != written:
        raise SystemExit(f"verification failed: wrote {written}, read {read}")
    disk.eject(ident)
    say(f"ejected {ident}; insert the card into the Raspberry Pi and power it on")
    if total > size:
        say("the card is larger than the image, so the root filesystem keeps its old size; on the Pi run: sudo raspi-config --expand-rootfs && sudo reboot")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Write a backup image onto an SD card and verify it.")
    parser.add_argument("--image", default="", help="path of the .img.xz; asked when empty")
    parser.add_argument("--disk", default="", help="disk identifier such as disk9; asked when empty")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("restore is macOS only", file=sys.stderr)
        return 2
    image = image_for(args.image)
    info = disk.card(args.disk)
    if not (args.image and args.disk) and not prompt.confirm(f"Restore {image.name} onto {disk.describe(info)}?"):
        print("cancelled", file=sys.stderr)
        return 1
    restore(image, info)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest testkit/tests/test_restore.py -q`
Expected: `18 passed`

- [ ] **Step 5: Add the make target**

In `Makefile`, directly after the `backup` target's recipe line, insert:

```makefile
.PHONY: restore
restore: ## write a backup image onto an SD card (make restore [IMAGE=backups/x.img.xz] [DISK=disk9])
	@$(UV) python -m pihero_testkit.restore --image="$(IMAGE)" --disk="$(DISK)"
```

Add `IMAGE ?=` under `NAME ?=` at the top of the file.

- [ ] **Step 6: Verify the target is wired and the whole tier passes**

Run: `make help | grep -E 'backup|restore'`
Expected: two lines, `backup` and `restore`, each with its description.

Run: `make -n restore IMAGE=backups/x.img.xz DISK=disk9`
Expected: prints `uv run --frozen python -m pihero_testkit.restore --image="backups/x.img.xz" --disk="disk9"`

Run: `uv run pytest testkit/tests -m tier0 -q --ignore=testkit/tests/test_static.py`
Expected: all pass. If the podman machine is running, run `make test-tier0` instead and expect green including the static checks.

- [ ] **Step 7: Commit**

```bash
git add testkit/src/pihero_testkit/restore.py testkit/tests/test_restore.py Makefile
git commit -m "$(cat <<'EOF'
testkit: make restore writes a backup image onto an SD card and verifies it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Documentation

**Files:**
- Modify: `docs/workflows.md` (new section between "Update devices" and "Change a package")
- Modify: `docs/design.md` (goals bullet line 23, decisions table after line 38, layout tree after line 87, operations list after the "Rollback is a version pin" bullet)

**Interfaces:** none.

- [ ] **Step 1: Add the workflow**

In `docs/workflows.md`, insert before the line `## Change a package`:

````markdown
## Back up a device

Before a risky change, or once a device holds state its device file cannot recreate, image its card. Power the Pi off, put the
card into the Mac, and:

```shell
make backup                       # asks which card; the image is named after the Pi and the day
make restore                      # asks which image and which card, confirms, writes, verifies, ejects
```

Images land in `backups/<hostname>-<date>.img.xz`, gitignored, next to a `.toml` with the size and checksum a restore checks
first. The hostname comes from the card's `user-data`; `NAME=` overrides it, and `DISK=` and `IMAGE=` skip the questions.
A 32 GB card takes about ten minutes each way. Restore needs a card at least as large as the one imaged, and a nominally equal
card from another maker can be a few megabytes short, so when replacing a card buy the next size up. On a larger card the root
filesystem keeps its old size until `sudo raspi-config --expand-rootfs` and a reboot.

````

- [ ] **Step 2: Record the decision in the design doc**

In `docs/design.md`:

Replace the goals bullet

```markdown
- The interactive CLI and `gum` are gone: too slow on old boards, and the tests replace the diagnostics.
```

with

```markdown
- The interactive CLI and `gum` are gone from the device: too slow on old boards, and the tests replace the diagnostics. Mac-side
  commands ask for what `make` was not given, with nothing beyond `input()`.
```

After the decisions-table row `| Device files that share content | Standalone copies | Simpler than a merge step |` add:

```markdown
| Card backup | `make backup` and `make restore`: a full raw xz image taken on the Mac through `authopen`, restored onto a card of the same size or larger | Brings back state no device file holds; the format is that of Raspberry Pi OS images, so `flash`'s writer and verifier restore it; shrinking so a nominally equal card fits is the planned follow-up |
```

In the layout tree, after the line starting with `devices/`, add (align the comment with the lines above):

```
backups/                                                    # card images and their sidecars, gitignored
```

In the Operations list, after the **Rollback is a version pin** bullet, add:

```markdown
- **Backup is a card image.** `make backup` reads the whole card into `backups/<host>-<date>.img.xz` with a sidecar naming
  size and sha256; `make restore` refuses a smaller card before writing, verifies by reading back, and points at
  `raspi-config --expand-rootfs` on a larger one. Shrinking the image so a nominally equal card fits is the planned follow-up.
```

- [ ] **Step 3: Check the Markdown**

Run: `grep -n 'Back up a device\|Card backup\|Backup is a card image\|^backups/' docs/workflows.md docs/design.md`
Expected: four hits, one per insertion.

Run: `uv run pytest testkit/tests -m tier0 -q --ignore=testkit/tests/test_static.py`
Expected: still green (documentation cannot break it, but this is the gate before the commit).

- [ ] **Step 4: Commit**

```bash
git add docs/workflows.md docs/design.md
git commit -m "$(cat <<'EOF'
docs: back up and restore a device's card

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Verification with a card (needs a Mac, an SD card reader, and a card that holds a Pi)

**Files:** none. This task produces evidence, not code. Use a card you can afford to overwrite for the restore half, such as the `gadget-test` device's card, or a spare.

- [ ] **Step 1: Interactive backup**

Insert a Pi card. Run `make backup`. Expected: the card list shows only the card (no external SSD), Enter picks it, macOS asks for authorization once, progress lines report MiB, percentage, and MB/s every 256 MiB, and the run ends with `ejected diskN; backups/<host>-<today>.img.xz restores onto a card of at least X GB`. Check `ls -la backups/` shows the `.img.xz` and the `.toml`, and `cat backups/<host>-<today>.toml` shows `size` and `sha256`. Note the wall time.

- [ ] **Step 2: Refused repeat**

Reinsert the card and run `make backup DISK=diskN` with the same name. Expected: exits non-zero with `… exists; move it away or pass NAME=` and touches nothing.

- [ ] **Step 3: Interactive restore onto the same card**

Run `make restore`. Expected: the image list shows the new image first with the card size it needs, the card list shows the card, the confirmation names both, `n` cancels with exit 1. Run again and answer `y`. Expected: write and verify progress, `ejected diskN`, no expand-rootfs line because the card is the one imaged. Boot the Pi from it and confirm `ssh pi@<host>.local` works as before.

- [ ] **Step 4: Refused smaller card, if one is at hand**

With a smaller card inserted: `make restore IMAGE=backups/<host>-<today>.img.xz DISK=diskM`. Expected: immediate `diskM holds A GB, the image needs B GB; use a larger card`, no authorization prompt, card untouched.

- [ ] **Step 5: Record**

Append the measured backup and restore durations for the card size used to the "Back up a device" section of `docs/workflows.md` if they differ from "about ten minutes" by more than a few minutes, and commit:

```bash
git add docs/workflows.md
git commit -m "$(cat <<'EOF'
docs: measured backup and restore times

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

Skip the commit if nothing changed.
