# Kiosk Preview Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move netmon's kiosk preview (browser, VM, board) into `pihero_testkit.preview` behind a `KioskApp` protocol, so netmon and busy-screen each keep a thin `tests/preview.py` and can preview at the same time on one Mac.

**Architecture:** A subpackage `pihero_testkit/preview/` with one module per concern (api, process, record, kiosk, dev_server, window, layer, vm, board, flavors, session), a top-level `pihero_testkit/device_file.py` for the device-file rendering both apps copy, and a `locks.py` used by the layer and base-image builds. Every module has pure functions with injectable collaborators (`run`, `sleep`, `clock`) so tier 0 covers it without QEMU; one `preview`-marked, Mac-only test runs a real VM session with a reference app.

**Tech Stack:** Python 3.13 stdlib, pytest, the existing testkit (`vm.Vm`, `vm.provisioned_vm`, `prepare`, `ssh`, `repo`), QEMU with HVF, `osascript`, `ssh`.

**Spec:** [docs/superpowers/specs/2026-10-03-kiosk-preview-design.md](../specs/2026-10-03-kiosk-preview-design.md)

## Global Constraints

- Python 3.13, stdlib only in the testkit (`pyproject.toml` lists `pytest` and `pytest-testinfra` only).
- Tests in `testkit/tests/test_*.py`, `pytestmark = pytest.mark.tier0`, one class per subject named `TestSubject`, test names as sentences, tests first and helpers last in a file, no comments in tests.
- Run tests with `uv run --frozen pytest <file> -q` from the repository root (`make test-tier0` runs them all).
- Commits: Conventional Commits with scope `testkit` (`feat(testkit): …`, `test(testkit): …`, `docs(testkit): …`), header at most 72 characters, imperative, lowercase, no period. One change per commit.
- Public functions get a one-line docstring stating the contract (`Return …`, PEP 257 imperative); comments only for what the code cannot say.
- The inspector port in the guest and on the board is `2999`; the Mac side is a free port per session.
- The board rule for a Mac port `P` is `10000 + P`, refused above 55535.
- The kiosk's contract: unit `pihero-kiosk`, file `/etc/pihero/kiosk.conf`, cog's `Loaded successfully` line, package `pihero-kiosk`.
- Version 2.8.0 in `testkit/pyproject.toml`.

## Review Focus

- A record written by netmon's current preview (`{"owner": 1234, "gradle": 5678, "broker": true}`, pids as plain integers) is read by the new code on its first run: `alive()` must treat anything that is not a `[pid, started]` list as gone, and the `broker` key must be ignored without a crash. Test in Task 6.
- A corrupt `session.json` (half-written when the session was killed) must be treated as an empty record, not end the start. Test in Task 6.
- `INSPECT` names an application `open` cannot find: `open` exits non-zero and the session must go on, not end. Test in Task 13.
- `user_data()` without `pihero-kiosk` builds a layer whose kiosk never loads and fails after 90 s with a misleading message: `layer.ensure` must refuse it up front. Test in Task 9.
- `TARGET=pi@host:2222`: the `-p 2222` must reach both the board's `ssh` commands and the tunnel. Test in Task 11.

## File Structure

| File | Responsibility |
|---|---|
| `testkit/src/pihero_testkit/locks.py` | `held(path)`: an exclusive `flock` for builds two runs must not do at once |
| `testkit/src/pihero_testkit/prepare.py` | takes the lock around the base image build |
| `testkit/src/pihero_testkit/device_file.py` | `block`, `drop`, `with_user`, `with_source`, `write`, `USER`, `PUBLIC_KEY` |
| `testkit/src/pihero_testkit/preview/__init__.py` | re-exports `KioskApp`, `Backend`, `DevServer`, `Served`, `Settings`, `main` |
| `testkit/src/pihero_testkit/preview/api.py` | the protocols and `Settings` |
| `testkit/src/pihero_testkit/preview/process.py` | ports, `ps`, signals, waiting |
| `testkit/src/pihero_testkit/preview/record.py` | the record file, stale actions, claim, forget |
| `testkit/src/pihero_testkit/preview/kiosk.py` | pure: kiosk.conf rewrite and parse, inspector URL, journal commands, the kiosk's constants |
| `testkit/src/pihero_testkit/preview/dev_server.py` | start, wait, stop the app's dev server |
| `testkit/src/pihero_testkit/preview/window.py` | place QEMU's window by pid, cascade |
| `testkit/src/pihero_testkit/preview/layer.py` | the provisioned layer cache |
| `testkit/src/pihero_testkit/preview/vm.py` | one VM session |
| `testkit/src/pihero_testkit/preview/board.py` | one board session |
| `testkit/src/pihero_testkit/preview/flavors.py` | `Shown`, the `Served` rules, `Browser`, `Vm`, `Device` |
| `testkit/src/pihero_testkit/preview/session.py` | `run`, `main`, the ready message |
| `testkit/src/pihero_testkit/plugin.py` | the `preview` marker |
| `testkit/tests/test_locks.py`, `test_prepare.py`, `test_device_file.py`, `test_preview_api.py`, `test_preview_process.py`, `test_preview_record.py`, `test_preview_kiosk.py`, `test_preview_contract.py`, `test_preview_dev_server.py`, `test_preview_window.py`, `test_preview_layer.py`, `test_preview_vm.py`, `test_preview_board.py`, `test_preview_flavors.py`, `test_preview_session.py`, `test_preview_live.py` | one test file per module, plus the kiosk contract and the live session |
| `Makefile`, `README.md`, `docs/testing.md`, `docs/app-conventions.md`, `docs/design.md`, `testkit/pyproject.toml` | `make test-preview`, docs, version |

Tasks 1 to 15 are in this repository on the branch `feat/kiosk-preview`. Tasks 16 to 18 are the downstream work in netmon and busy-screen and the release.

---

### Task 1: The lock, and the base image build under it

**Files:**
- Create: `testkit/src/pihero_testkit/locks.py`
- Modify: `testkit/src/pihero_testkit/prepare.py:361-375`
- Test: `testkit/tests/test_locks.py`, `testkit/tests/test_prepare.py`

**Interfaces:**
- Produces: `locks.held(path: Path)` context manager; `prepare.prepare()` unchanged in signature.

- [ ] **Step 1: Write the failing lock test**

```python
# testkit/tests/test_locks.py
import threading

import pytest

from pihero_testkit import locks

pytestmark = pytest.mark.tier0


class TestHeld:
    def test_creates_the_lock_file_and_its_directory(self, tmp_path):
        path = tmp_path / "cache" / "a.lock"

        with locks.held(path):
            pass

        assert path.exists()

    def test_makes_a_second_holder_wait_until_the_first_leaves(self, tmp_path):
        path = tmp_path / "a.lock"
        order = []
        first_inside, release_first = threading.Event(), threading.Event()

        def first():
            with locks.held(path):
                order.append("first in")
                first_inside.set()
                release_first.wait(5)
                order.append("first out")

        def second():
            with locks.held(path):
                order.append("second in")

        a = threading.Thread(target=first)
        a.start()
        first_inside.wait(5)
        b = threading.Thread(target=second)
        b.start()
        b.join(0.3)
        assert order == ["first in"]
        release_first.set()
        a.join(5)
        b.join(5)

        assert order == ["first in", "first out", "second in"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --frozen pytest testkit/tests/test_locks.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'pihero_testkit.locks'`

- [ ] **Step 3: Write locks.py**

```python
# testkit/src/pihero_testkit/locks.py
"""A file lock for the builds two runs must not do at once: the base image and a preview layer."""

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def held(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on `path`, creating it and its directory, until the block ends; a second holder waits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
```

- [ ] **Step 4: Run the lock test to verify it passes**

Run: `uv run --frozen pytest testkit/tests/test_locks.py -q`
Expected: 2 passed

- [ ] **Step 5: Write the failing prepare test**

Append to `testkit/tests/test_prepare.py`:

```python
import fcntl
from pathlib import Path

from pihero_testkit import tools


class TestPrepare:
    def test_builds_under_the_lock_of_its_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prepare, "CACHE", tmp_path)
        monkeypatch.setattr(prepare, "download", lambda url, sha256: Path("/downloads/image.img.xz"))
        seen = []

        def fake_run(args, **kwargs):
            lock = next(tmp_path.joinpath("base").glob("*.lock"))
            with lock.open("w") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    seen.append("free")
                except BlockingIOError:
                    seen.append("held")

        monkeypatch.setattr(tools, "run", fake_run)

        base = prepare.prepare()

        assert seen == ["held"]
        assert (base.rootfs.parent / "done").exists()

    def test_skips_the_build_of_a_prepared_image(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prepare, "CACHE", tmp_path)
        monkeypatch.setattr(tools, "run", lambda *args, **kwargs: pytest.fail("built again"))
        out = tmp_path / "base" / prepare.key()
        out.mkdir(parents=True)
        (out / "done").touch()

        base = prepare.prepare()

        assert base.rootfs == out / "rootfs.qcow2"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run --frozen pytest testkit/tests/test_prepare.py -q`
Expected: FAIL with `AttributeError: module 'pihero_testkit.prepare' has no attribute 'key'` and, for the first test, `seen == ["free"]`.

- [ ] **Step 7: Change prepare.py**

Replace `prepare()`:

```python
def key() -> str:
    """Return the cache key of the tier-2 base image: the image checksum, the kernel package and the prepare script."""
    config = lock()
    return hashlib.sha256((config[TIER2_IMAGE]["sha256"] + config["kernel"]["package"] + SCRIPT.read_text()).encode()).hexdigest()[:12]


def prepare(force: bool = False) -> BaseImage:
    """Return the cached base image, building it under a lock when it is missing or `force` is set."""
    config = lock()
    raspios = config[TIER2_IMAGE]
    name = key()
    out = CACHE / "base" / name
    if force or not (out / "done").exists():
        with locks.held(CACHE / "base" / f"{name}.lock"):
            if force or not (out / "done").exists():
                image = download(raspios["url"], raspios["sha256"])
                out.mkdir(parents=True, exist_ok=True)
                tools.run(
                    ["/testkit/prepare-rootfs", "--image", f"/cache/downloads/{image.name}", "--out", f"/cache/base/{name}", "--kernel-package", config["kernel"]["package"]],
                    privileged=True,
                    mounts=[f"{CACHE}:/cache", f"{PACKAGE_DIR}:/testkit:ro"],
                )
                (out / "done").touch()
    return BaseImage(out / "rootfs.qcow2", out / "vmlinuz", out / "initrd.img", out / "boot")
```

Add `from . import locks, tools` to the imports (replacing `from . import tools`).

- [ ] **Step 8: Run both test files**

Run: `uv run --frozen pytest testkit/tests/test_locks.py testkit/tests/test_prepare.py -q`
Expected: 6 passed

- [ ] **Step 9: Commit**

```bash
git add testkit/src/pihero_testkit/locks.py testkit/src/pihero_testkit/prepare.py testkit/tests/test_locks.py testkit/tests/test_prepare.py
git commit -m "feat(testkit): build the base image under a lock"
```

---

### Task 2: `device_file`, the rendering both apps copy

**Files:**
- Create: `testkit/src/pihero_testkit/device_file.py`
- Test: `testkit/tests/test_device_file.py`

**Interfaces:**
- Produces: `USER = "pihero"`, `PUBLIC_KEY: Path`, `block(text, start) -> str`, `drop(text, start) -> str`, `with_user(text, key, user=USER) -> str`, `with_source(text, path, url=repo.URL) -> str`, `write(directory, user_data) -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_device_file.py
import pytest

from pihero_testkit import device_file, repo

pytestmark = pytest.mark.tier0

KEY = "ssh-ed25519 AAAATEST pihero-testkit"
SAMPLE = """\
#cloud-config
hostname: sample
users:
  - name: pi
    groups: users,sudo
    # the login shell
    shell: /bin/bash

    ssh_authorized_keys:
      - ssh-ed25519 AAAA...your public key... you@mac
packages:
  - pihero
  - myapp
write_files:
  - path: /etc/apt/sources.list.d/pihero.sources
    content: |
      Types: deb
      URIs: https://bkahlert.github.io/pihero/apt
      Suites: ./
  # the app's own repository
  - path: /etc/apt/sources.list.d/myapp.sources
    content: |
      Types: deb
      URIs: https://example.org/apt
      Suites: ./
  - path: /etc/pihero/kiosk.conf
    content: |
      URL=http://localhost/
runcmd:
  - echo done
"""


class TestBlock:
    def test_is_the_line_and_what_is_indented_under_it(self):
        text = device_file.block(SAMPLE, "  - path: /etc/pihero/kiosk.conf")

        assert text == "  - path: /etc/pihero/kiosk.conf\n    content: |\n      URL=http://localhost/\n"

    def test_keeps_blank_and_comment_lines_inside_the_block(self):
        text = device_file.block(SAMPLE, "users:")

        assert "    # the login shell\n" in text
        assert "\n\n    ssh_authorized_keys:\n" in text

    def test_leaves_a_comment_before_the_next_sibling_to_what_follows(self):
        text = device_file.block(SAMPLE, "  - path: /etc/apt/sources.list.d/pihero.sources")

        assert not text.endswith("  # the app's own repository\n")
        assert text.endswith("      Suites: ./\n")

    def test_on_a_missing_line_raises(self):
        with pytest.raises(ValueError, match="no line 'nope:'"):
            device_file.block(SAMPLE, "nope:")


class TestDrop:
    def test_removes_the_block_and_nothing_else(self):
        text = device_file.drop(SAMPLE, "  - path: /etc/pihero/kiosk.conf")

        assert "kiosk.conf" not in text
        assert text.count("\n") == SAMPLE.count("\n") - 3


class TestWithUser:
    def test_renames_the_user_and_sets_the_key(self):
        text = device_file.with_user(SAMPLE, KEY)

        assert "  - name: pihero\n" in text
        assert "  - name: pi\n" not in text
        assert f"    ssh_authorized_keys:\n      - {KEY}\n" in text

    def test_takes_another_user_name(self):
        text = device_file.with_user(SAMPLE, KEY, user="tester")

        assert "  - name: tester\n" in text

    def test_changes_nothing_else(self):
        expected = SAMPLE.replace("  - name: pi\n", "  - name: pihero\n").replace("      - ssh-ed25519 AAAA...your public key... you@mac\n", f"      - {KEY}\n")

        text = device_file.with_user(SAMPLE, KEY)

        assert text == expected

    def test_sets_the_key_under_ssh_authorized_keys_and_not_an_earlier_list(self):
        imported = SAMPLE.replace("    ssh_authorized_keys:\n", "    ssh_import_id:\n      - gh:someone\n    ssh_authorized_keys:\n")

        text = device_file.with_user(imported, KEY)

        assert "    ssh_import_id:\n      - gh:someone\n" in text
        assert f"    ssh_authorized_keys:\n      - {KEY}\n" in text

    def test_on_a_file_without_a_users_block_raises(self):
        with pytest.raises(ValueError, match="users:"):
            device_file.with_user("#cloud-config\nhostname: x\n", KEY)

    def test_on_two_users_raises(self):
        two = SAMPLE.replace("packages:\n", "  - name: second\n    ssh_authorized_keys:\n      - ssh-ed25519 BBBB second\npackages:\n")

        with pytest.raises(ValueError, match="one user"):
            device_file.with_user(two, KEY)

    def test_on_a_users_block_without_a_key_raises(self):
        keyless = SAMPLE.replace("    ssh_authorized_keys:\n      - ssh-ed25519 AAAA...your public key... you@mac\n", "")

        with pytest.raises(ValueError, match="ssh_authorized_keys"):
            device_file.with_user(keyless, KEY)


class TestWithSource:
    def test_replaces_the_entry_with_a_trusted_source_at_the_harness_url(self):
        text = device_file.with_source(SAMPLE, "/etc/apt/sources.list.d/myapp.sources")

        assert "  - path: /etc/apt/sources.list.d/myapp.sources\n    content: |\n      Types: deb\n      URIs: http://10.0.2.2:8000/\n      Suites: ./\n      Trusted: yes\n" in text
        assert "example.org" not in text
        assert "https://bkahlert.github.io/pihero/apt" in text

    def test_takes_another_url(self):
        text = device_file.with_source(SAMPLE, "/etc/apt/sources.list.d/myapp.sources", url="http://10.0.2.2:9000/")

        assert "      URIs: http://10.0.2.2:9000/\n" in text

    def test_uses_the_repositorys_conventional_url(self):
        assert repo.URL == "http://10.0.2.2:8000/"


class TestWrite:
    def test_writes_user_data_into_the_directory_and_returns_it(self, tmp_path):
        out = device_file.write(tmp_path / "device", "#cloud-config\n")

        assert out == tmp_path / "device"
        assert [p.name for p in out.iterdir()] == ["user-data"]
        assert (out / "user-data").read_text() == "#cloud-config\n"


class TestConstants:
    def test_the_public_key_is_the_testkits(self):
        assert device_file.PUBLIC_KEY.read_text().strip().endswith(" pihero-testkit")

    def test_the_user_is_pihero(self):
        assert device_file.USER == "pihero"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_device_file.py -q`
Expected: FAIL with `ImportError: cannot import name 'device_file'`

- [ ] **Step 3: Write device_file.py**

```python
# testkit/src/pihero_testkit/device_file.py
"""Renders a device file for the tier-2 VM: the testkit's user and key, and the harness repository in place of a published source."""

import re
from importlib.resources import files
from pathlib import Path

from . import repo

USER = "pihero"
PUBLIC_KEY = Path(str(files("pihero_testkit") / "keys" / "pihero-testkit.pub"))
SOURCE = """\
  - path: {path}
    content: |
      Types: deb
      URIs: {url}
      Suites: ./
      Trusted: yes
"""


def block(text: str, start: str) -> str:
    """Return the line equal to `start` and every following line indented deeper than it, with the blank and comment lines
    between them; blank and comment lines after the last such line belong to what follows. Raise ValueError without the line."""
    lines = text.splitlines(keepends=True)
    try:
        begin = next(i for i, line in enumerate(lines) if line.rstrip("\n") == start)
    except StopIteration:
        raise ValueError(f"the device file has no line {start!r}") from None
    indent = len(start) - len(start.lstrip(" "))
    end = begin + 1
    for i in range(begin + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(lines[i]) - len(lines[i].lstrip(" ")) <= indent:
            break
        end = i + 1
    return "".join(lines[begin:end])


def drop(text: str, start: str) -> str:
    """Return `text` without the block that starts at `start`."""
    return text.replace(block(text, start), "", 1)


def with_user(text: str, key: str, user: str = USER) -> str:
    """Return `text` with its one user renamed to `user` and that user's first authorized key replaced by `key`.

    Raise ValueError without a users block, with more or fewer than one user, or without an ssh_authorized_keys entry.
    """
    users = block(text, "users:")
    if users.count("  - name: ") != 1:
        raise ValueError("expected one user in the device file")
    renamed = re.sub(r"^(?P<prefix>  - name: ).*$", lambda m: m["prefix"] + user, users, count=1, flags=re.M)
    rekeyed, keys = re.subn(r"^(?P<prefix>    ssh_authorized_keys:\n      - ).*$", lambda m: m["prefix"] + key, renamed, count=1, flags=re.M)
    if keys == 0:
        raise ValueError("expected an ssh_authorized_keys entry in the device file")
    return text.replace(users, rekeyed, 1)


def with_source(text: str, path: str, url: str = repo.URL) -> str:
    """Return `text` with the write_files entry at `path` replaced by a trusted deb822 source for `url`."""
    return text.replace(block(text, f"  - path: {path}"), SOURCE.format(path=path, url=url), 1)


def write(directory: Path, user_data: str) -> Path:
    """Write `user_data` as `directory/user-data`, creating the directory, and return the directory."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "user-data").write_text(user_data)
    return directory
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_device_file.py -q`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/device_file.py testkit/tests/test_device_file.py
git commit -m "feat(testkit): render a device file for the VM from the testkit"
```

---

### Task 3: The API: protocols and `Settings`

**Files:**
- Create: `testkit/src/pihero_testkit/preview/__init__.py`, `testkit/src/pihero_testkit/preview/api.py`
- Test: `testkit/tests/test_preview_api.py`

**Interfaces:**
- Produces: `FLAVORS`, `Settings(flavor, target, inspect, environ)` with `Settings.from_environ(flavor, environ)`, `inspect_app(value)`, `DevServer(argv, port, env)`, protocols `Backend` (`managed`, `mac_port`, `start()`, `stop()`, `describe()`), `Served` (`flavor`, `address(mac_port)`), `KioskApp` (`name`, `root`, `display`, `user_data()`, `dev_server(settings)`, `backend(settings)`, `page_url(backend, served)`). `main` is re-exported from `session` in Task 13.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_api.py
import pytest

from pihero_testkit.preview import api

pytestmark = pytest.mark.tier0


class TestSettingsFromEnviron:
    def test_takes_the_flavor_and_defaults_to_safari(self):
        settings = api.Settings.from_environ("vm", {})

        assert (settings.flavor, settings.target, settings.inspect) == ("vm", None, "Safari")

    def test_keeps_the_environment_for_the_apps_own_variables(self):
        settings = api.Settings.from_environ("browser", {"BROKER": "fake"})

        assert settings.environ["BROKER"] == "fake"

    def test_on_the_device_takes_target(self):
        settings = api.Settings.from_environ("device", {"TARGET": "pi@host"})

        assert settings.target == "pi@host"

    def test_on_the_device_without_target_raises(self):
        with pytest.raises(ValueError, match="preview-device needs TARGET=user@host"):
            api.Settings.from_environ("device", {})

    @pytest.mark.parametrize("flavor", ["browser", "vm"])
    def test_refuses_target_elsewhere(self, flavor):
        with pytest.raises(ValueError, match="TARGET is only for preview-device"):
            api.Settings.from_environ(flavor, {"TARGET": "pi@host"})

    def test_refuses_an_unknown_flavor(self):
        with pytest.raises(ValueError, match="browser, vm or device"):
            api.Settings.from_environ("tv", {})

    @pytest.mark.parametrize("value", ["", "0"])
    def test_opens_nothing_for_inspect_zero_or_empty(self, value):
        settings = api.Settings.from_environ("vm", {"INSPECT": value})

        assert settings.inspect is None

    def test_takes_any_application_name(self):
        settings = api.Settings.from_environ("vm", {"INSPECT": "Google Chrome"})

        assert settings.inspect == "Google Chrome"


class TestDevServer:
    def test_has_no_environment_additions_by_default(self):
        server = api.DevServer(["./gradlew", "run"], 8081)

        assert server.env == {}


class TestFlavors:
    def test_are_browser_vm_and_device(self):
        assert api.FLAVORS == ("browser", "vm", "device")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_api.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'pihero_testkit.preview'`

- [ ] **Step 3: Write api.py and the package init**

```python
# testkit/src/pihero_testkit/preview/api.py
"""The preview's API: what an app that shows a page in pihero-kiosk implements, and what one session hands it."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

FLAVORS = ("browser", "vm", "device")


def inspect_app(value: str) -> str | None:
    """Return the application INSPECT names, or None for "0" or an empty value."""
    return None if value in ("", "0") else value


@dataclass(frozen=True)
class Settings:
    """What every flavor takes: the flavor, TARGET for the device, INSPECT, and the environment the app's own variables come from."""

    flavor: str
    target: str | None
    inspect: str | None
    environ: Mapping[str, str]

    @staticmethod
    def from_environ(flavor: str, environ: Mapping[str, str]) -> "Settings":
        """Return the settings for `flavor` from `environ`; raise ValueError for an unknown flavor or a TARGET that does not fit it."""
        if flavor not in FLAVORS:
            raise ValueError(f"flavor must be browser, vm or device, not {flavor!r}")
        target = environ.get("TARGET") or None
        if flavor == "device" and not target:
            raise ValueError("preview-device needs TARGET=user@host")
        if flavor != "device" and target:
            raise ValueError("TARGET is only for preview-device")
        return Settings(flavor, target, inspect_app(environ.get("INSPECT", "Safari")), environ)


@dataclass(frozen=True)
class DevServer:
    """The app's dev server: `argv` run in the app's root with `env` added to the environment, ready once `port` answers on 127.0.0.1."""

    argv: list[str]
    port: int
    env: dict[str, str] = field(default_factory=dict)


class Backend(Protocol):
    """The app's backend as one session sees it: a fake the session starts, the device's own, or an address given."""

    managed: bool
    """Whether start() starts something the session must stop."""
    mac_port: int | None
    """The Mac port the kiosk must reach, None when the backend is not on the Mac."""

    def start(self) -> None:
        """Start the fake; raise RuntimeError with the reason when it cannot."""

    def stop(self) -> None:
        """End the app's fake wherever a session left it; idempotent, and works from a fresh process."""

    def describe(self) -> str:
        """Return one line for the ready message, such as "fake on localhost:8080"."""


class Served(Protocol):
    """How the kiosk of one flavor reaches the Mac."""

    flavor: str

    def address(self, mac_port: int) -> str:
        """Return "host:port" as the kiosk reaches the Mac's `mac_port`."""


class KioskApp(Protocol):
    """What the preview needs from an app that shows a page in pihero-kiosk."""

    name: str
    """Scopes the record, the board's /run directory and its drop-in; "netmon"."""
    root: Path
    """The repository: the record lives under root/dist/preview and the dev server runs there."""
    display: tuple[int, int]
    """The VM's display and the window's size in points; (800, 480)."""

    def user_data(self) -> str:
        """Return the VM's device file: the sample minus what the Mac serves, with pihero-kiosk."""

    def dev_server(self, settings: Settings) -> DevServer:
        """Return the dev server for `settings`."""

    def backend(self, settings: Settings) -> Backend:
        """Return the backend `settings` ask for; raise ValueError naming the grammar for a bad variable."""

    def page_url(self, backend: Backend, served: Served) -> str:
        """Return the URL the kiosk or browser loads, every Mac port through `served.address`."""
```

```python
# testkit/src/pihero_testkit/preview/__init__.py
"""A kiosk app's page from the Mac's dev server in a browser, a VM's kiosk or a board's kiosk; see docs/app-conventions.md."""

from .api import Backend, DevServer, KioskApp, Served, Settings

__all__ = ["Backend", "DevServer", "KioskApp", "Served", "Settings"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_api.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview testkit/tests/test_preview_api.py
git commit -m "feat(testkit): define the kiosk preview's KioskApp protocol"
```

---

### Task 4: `process`: ports, `ps`, signals, waiting

**Files:**
- Create: `testkit/src/pihero_testkit/preview/process.py`
- Test: `testkit/tests/test_preview_process.py`

**Interfaces:**
- Produces: `answers(host, port, timeout=1.0) -> bool`, `info(pid, run=subprocess.run) -> tuple[str, str] | None`, `entry(pid, info=info) -> list | None`, `alive(entry, info=info) -> bool`, `wait_until_gone(pids, info=info, timeout=30, sleep, clock)`, `raise_on_sigterm()`, `until_interrupted(watch=None, interval=1.0, sleep=time.sleep)`, `free_port() -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_process.py
import signal
import socket
from subprocess import CompletedProcess

import pytest

from pihero_testkit.preview import process

pytestmark = pytest.mark.tier0
STARTED = "Fri Oct  3 10:11:12 2026"


class TestAnswers:
    def test_is_true_for_a_listening_port(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()

            assert process.answers("127.0.0.1", sock.getsockname()[1])

    def test_is_false_for_a_closed_port(self):
        assert not process.answers("127.0.0.1", process.free_port(), timeout=0.2)


class TestInfo:
    def test_is_the_start_time_and_state_of_a_running_process(self):
        started, state = process.info(42, run=ps(f"{STARTED} S+\n"))

        assert (started, state) == (STARTED, "S+")

    def test_asks_ps_for_the_start_time_and_state_of_the_pid(self):
        calls = []
        process.info(42, run=ps("", calls))

        assert calls == [["ps", "-p", "42", "-o", "lstart=,stat="]]

    def test_is_none_for_a_process_that_is_gone(self):
        assert process.info(42, run=ps("")) is None

    def test_is_none_for_a_zombie(self):
        assert process.info(42, run=ps(f"{STARTED} Z\n")) is None


class TestEntry:
    def test_is_the_pid_and_its_start_time(self):
        assert process.entry(42, info=lambda pid: (STARTED, "S")) == [42, STARTED]

    def test_is_none_for_a_process_that_is_gone(self):
        assert process.entry(42, info=lambda pid: None) is None


class TestAlive:
    def test_is_true_while_the_pid_runs_with_the_recorded_start_time(self):
        assert process.alive([42, STARTED], info=lambda pid: (STARTED, "S"))

    def test_is_false_for_a_pid_reused_by_a_process_started_later(self):
        assert not process.alive([42, STARTED], info=lambda pid: ("Sat Oct  4 00:00:00 2026", "S"))

    def test_is_false_for_a_pid_that_is_gone(self):
        assert not process.alive([42, STARTED], info=lambda pid: None)

    @pytest.mark.parametrize("entry", [None, 42, "42", [42], {"pid": 42}])
    def test_is_false_for_anything_but_a_pid_and_start_time(self, entry):
        assert not process.alive(entry, info=lambda pid: (STARTED, "S"))


class TestWaitUntilGone:
    def test_returns_once_every_pid_is_gone(self):
        remaining = {1: 2, 2: 1}

        def info(pid):
            remaining[pid] -= 1
            return (STARTED, "S") if remaining[pid] > 0 else None

        process.wait_until_gone([1, 2], info=info, sleep=lambda s: None, clock=counter())

        assert remaining == {1: 0, 2: 0}

    def test_raises_when_a_pid_outlives_the_timeout(self):
        with pytest.raises(TimeoutError, match="process 7 of a killed preview did not end within 30 s"):
            process.wait_until_gone([7], info=lambda pid: (STARTED, "S"), sleep=lambda s: None, clock=counter(step=20))


class TestUntilInterrupted:
    def test_returns_on_keyboard_interrupt_from_the_watch(self):
        def watch():
            raise KeyboardInterrupt

        process.until_interrupted(watch, sleep=lambda s: None)

    def test_raises_the_problem_the_watch_reports(self):
        answers = iter([None, "the tunnel ended"])

        with pytest.raises(RuntimeError, match="the tunnel ended"):
            process.until_interrupted(lambda: next(answers), sleep=lambda s: None)


class TestRaiseOnSigterm:
    def test_makes_sigterm_a_keyboard_interrupt(self):
        before = signal.getsignal(signal.SIGTERM)
        try:
            process.raise_on_sigterm()

            with pytest.raises(KeyboardInterrupt):
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        finally:
            signal.signal(signal.SIGTERM, before)


def ps(stdout: str, calls: list | None = None):
    def run(args, **kwargs):
        if calls is not None:
            calls.append(args)
        return CompletedProcess(args, 0, stdout=stdout, stderr="")

    return run


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_process.py -q`
Expected: FAIL with `ImportError: cannot import name 'process'`

- [ ] **Step 3: Write process.py**

```python
# testkit/src/pihero_testkit/preview/process.py
"""Helpers for the preview's processes: probing a port, a process's start time, ending on Ctrl-C or SIGTERM, waiting."""

import signal
import socket
import subprocess
import time
from collections.abc import Callable


def answers(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return whether something accepts a TCP connection at host:port within `timeout` seconds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def info(pid: int, run=subprocess.run) -> tuple[str, str] | None:
    """Return the start time and state of the running process `pid` as `ps` prints them, or None when it is gone or a zombie."""
    result = run(["ps", "-p", str(pid), "-o", "lstart=,stat="], capture_output=True, text=True, check=False)
    line = result.stdout.strip()
    if not line:
        return None
    started, _, state = line.rpartition(" ")
    if state.startswith("Z"):
        return None
    return started.strip(), state


def entry(pid: int, info=info) -> list | None:
    """Return `[pid, start time]` for the record, or None when the process is gone."""
    found = info(pid)
    return [pid, found[0]] if found else None


def alive(entry, info=info) -> bool:
    """Return whether the record entry `[pid, start time]` still names a running process; False for any other value."""
    if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], int):
        return False
    found = info(entry[0])
    return bool(found) and found[0] == entry[1]


def wait_until_gone(pids: list[int], info=info, timeout: float = 30, sleep=time.sleep, clock=time.monotonic) -> None:
    """Return once none of `pids` runs any more; raise TimeoutError after `timeout` seconds."""
    deadline = clock() + timeout
    running = [pid for pid in pids if info(pid)]
    while running:
        if clock() >= deadline:
            raise TimeoutError(f"process {running[0]} of a killed preview did not end within {timeout:g} s")
        sleep(0.5)
        running = [pid for pid in running if info(pid)]


def raise_on_sigterm() -> None:
    """Make SIGTERM end the program the way Ctrl-C does, so exit stacks run."""

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)


def until_interrupted(watch: Callable[[], str | None] | None = None, interval: float = 1.0, sleep=time.sleep) -> None:
    """Wait for Ctrl-C; with a `watch`, ask it every `interval` seconds and raise RuntimeError with the problem it reports."""
    try:
        if watch is None:
            signal.pause()
        while True:
            problem = watch()
            if problem:
                raise RuntimeError(problem)
            sleep(interval)
    except KeyboardInterrupt:
        pass


def free_port() -> int:
    """Return a TCP port that was free on 127.0.0.1 a moment ago."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_process.py -q`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/process.py testkit/tests/test_preview_process.py
git commit -m "feat(testkit): add the preview's process helpers"
```

---

### Task 5: `kiosk`: the pure helpers, and the contract with the package

**Files:**
- Create: `testkit/src/pihero_testkit/preview/kiosk.py`
- Test: `testkit/tests/test_preview_kiosk.py`, `testkit/tests/test_preview_contract.py`

**Interfaces:**
- Produces: `UNIT = "pihero-kiosk"`, `PACKAGE = "pihero-kiosk"`, `CONF = "/etc/pihero/kiosk.conf"`, `INSPECTOR_PORT = 2999`, `LOADED = "Loaded successfully"`, `DEVELOPER_EXTRAS`, `session_conf(current, url, inspector_port=INSPECTOR_PORT) -> str`, `unquote(value) -> str`, `parse_conf(text) -> dict[str, str]`, `inspector_url(listing, address) -> str | None`, `open_command(app, url) -> list[str]`, `since_command() -> str`, `loaded_command(since) -> str`, `loaded(output) -> bool`, `fetch_listing(address) -> str`, `wait_for_inspector(address, timeout=30, fetch, sleep, clock) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_kiosk.py
import pytest

from pihero_testkit.preview import kiosk

pytestmark = pytest.mark.tier0
URL = "http://10.0.2.2:8081/?broker.host=10.0.2.2&broker.port=8080"
QUOTED = 'URL=http://localhost/\nCOG_PLATFORM_DRM_VIDEO_MODE=800x480\nCOG_ARGS="--doc-viewer --web-mem-limit=200"\nJSC_useJIT=false\n'
LISTING = """<html><body><ul><li><a href="javascript:void(0)" onclick="window.open('Main.html?ws=' + window.location.host + '/socket/1/1/WebPage', '_blank')">Inspect</a></li></ul></body></html>"""


class TestSessionConf:
    def test_replaces_the_url_and_keeps_the_other_lines(self):
        text = kiosk.session_conf(QUOTED, URL)

        assert text.startswith(f"URL={URL}\nCOG_PLATFORM_DRM_VIDEO_MODE=800x480\n")
        assert "JSC_useJIT=false\n" in text

    def test_puts_developer_extras_in_front_of_quoted_cog_args(self):
        text = kiosk.session_conf(QUOTED, URL)

        assert 'COG_ARGS="--enable-developer-extras=true --doc-viewer --web-mem-limit=200"\n' in text

    def test_quotes_unquoted_cog_args(self):
        text = kiosk.session_conf("URL=http://localhost/\nCOG_ARGS=--platform-params=renderer=gles\n", URL)

        assert 'COG_ARGS="--enable-developer-extras=true --platform-params=renderer=gles"\n' in text

    def test_takes_single_quoted_cog_args(self):
        text = kiosk.session_conf("URL=http://localhost/\nCOG_ARGS='--doc-viewer'\n", URL)

        assert 'COG_ARGS="--enable-developer-extras=true --doc-viewer"\n' in text

    def test_adds_cog_args_when_absent(self):
        text = kiosk.session_conf("URL=http://localhost/\n", URL)

        assert 'COG_ARGS="--enable-developer-extras=true"\n' in text

    def test_adds_the_url_when_absent(self):
        text = kiosk.session_conf("", URL)

        assert text.startswith(f"URL={URL}\n")

    def test_ends_with_the_inspector_and_the_memory_settings_backend(self):
        text = kiosk.session_conf(QUOTED, URL)

        assert text.endswith("WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:2999\nGSETTINGS_BACKEND=memory\n")

    def test_takes_another_inspector_port(self):
        text = kiosk.session_conf(QUOTED, URL, inspector_port=3999)

        assert "WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:3999\n" in text

    def test_replaces_session_lines_already_present(self):
        once = kiosk.session_conf(QUOTED, URL)

        twice = kiosk.session_conf(once, URL)

        assert twice.count("WEBKIT_INSPECTOR_HTTP_SERVER=") == 1
        assert twice.count("GSETTINGS_BACKEND=") == 1
        assert twice.count("--enable-developer-extras=true") == 2

    def test_keeps_comments_and_blank_lines(self):
        text = kiosk.session_conf("# the kiosk\n\nURL=http://localhost/\n", URL)

        assert text.startswith(f"# the kiosk\n\nURL={URL}\n")


class TestUnquote:
    @pytest.mark.parametrize("value, expected", [('"a b"', "a b"), ("'a b'", "a b"), ("a b", "a b"), ('"', '"'), ("", "")])
    def test_strips_one_pair_of_matching_quotes(self, value, expected):
        assert kiosk.unquote(value) == expected


class TestParseConf:
    def test_reads_assignments_without_quotes_and_skips_comments_and_blanks(self):
        conf = kiosk.parse_conf("# note\n\nURL=http://x/\nCOG_ARGS=\"--a --b\"\nbroken line\n")

        assert conf == {"URL": "http://x/", "COG_ARGS": "--a --b"}


class TestInspectorUrl:
    def test_is_the_inspector_of_the_first_target(self):
        url = kiosk.inspector_url(LISTING, "127.0.0.1:2999")

        assert url == "http://127.0.0.1:2999/Main.html?ws=127.0.0.1:2999/socket/1/1/WebPage"

    def test_is_none_without_a_target(self):
        assert kiosk.inspector_url("<html></html>", "127.0.0.1:2999") is None


class TestWaitForInspector:
    def test_returns_the_inspector_once_the_list_names_a_target(self):
        listings = iter(["<html></html>", LISTING])

        url = kiosk.wait_for_inspector("127.0.0.1:2999", fetch=lambda address: next(listings), sleep=lambda s: None, clock=counter())

        assert url.endswith("/socket/1/1/WebPage")

    def test_falls_back_to_the_list_after_the_timeout(self):
        url = kiosk.wait_for_inspector("127.0.0.1:2999", timeout=3, fetch=lambda address: "", sleep=lambda s: None, clock=counter())

        assert url == "http://127.0.0.1:2999/"


class TestOpenCommand:
    def test_opens_the_url_in_the_application(self):
        assert kiosk.open_command("Safari", "http://127.0.0.1:2999/") == ["open", "-a", "Safari", "http://127.0.0.1:2999/"]


class TestJournal:
    def test_counts_the_loaded_lines_of_the_kiosk_since_a_time(self):
        command = kiosk.loaded_command("2026-10-03 10:00:00")

        assert command == "sudo journalctl -u pihero-kiosk --since '2026-10-03 10:00:00' --no-pager | grep -c 'Loaded successfully'"

    @pytest.mark.parametrize("output, expected", [("", False), ("0\n", False), ("1\n", True), ("3\n", True)])
    def test_loaded_reads_the_count(self, output, expected):
        assert kiosk.loaded(output) is expected

    def test_since_is_the_guests_clock_in_journalctl_form(self):
        assert kiosk.since_command() == "date '+%Y-%m-%d %H:%M:%S'"


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
```

```python
# testkit/tests/test_preview_contract.py
from pathlib import Path

import pytest

from pihero_testkit.preview import kiosk
from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0
PACKAGE = Path(__file__).resolve().parents[2] / "packages" / "pihero-kiosk"
UNIT_FILE = PACKAGE / "root" / "usr" / "lib" / "systemd" / "system" / f"{kiosk.UNIT}.service"
SCRIPT = PACKAGE / "root" / "usr" / "lib" / "pihero" / "kiosk"


class TestKioskContract:
    def test_the_unit_the_preview_restarts_exists(self):
        assert UNIT_FILE.exists()

    def test_the_unit_reads_the_file_the_preview_rewrites(self):
        assert f"EnvironmentFile=-{kiosk.CONF}\n" in UNIT_FILE.read_text()

    def test_the_package_the_preview_installs_is_this_one(self):
        assert f"name: {kiosk.PACKAGE}\n" in (PACKAGE / "nfpm.yaml").read_text()

    def test_the_script_hands_cog_the_variables_the_session_writes(self):
        script = load_script(SCRIPT)
        script.reachable = lambda url, timeout=5.0: True
        environ = kiosk.parse_conf(kiosk.session_conf('COG_ARGS="--doc-viewer"\n', "http://10.0.2.2:8081/"))
        argv = []

        script.main([], environ=environ, execvp=lambda file, args: argv.extend(args))

        assert argv == ["cog", "--platform=drm", "--enable-developer-extras=true", "--doc-viewer", "http://10.0.2.2:8081/"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_kiosk.py testkit/tests/test_preview_contract.py -q`
Expected: FAIL with `ImportError: cannot import name 'kiosk'`

- [ ] **Step 3: Write kiosk.py**

```python
# testkit/src/pihero_testkit/preview/kiosk.py
"""Pure helpers for the kiosk a preview drives: its settings file, its journal, the Web Inspector's address, and the package's names."""

import re
import time
import urllib.request

UNIT = "pihero-kiosk"
PACKAGE = "pihero-kiosk"
CONF = "/etc/pihero/kiosk.conf"
INSPECTOR_PORT = 2999
LOADED = "Loaded successfully"
DEVELOPER_EXTRAS = "--enable-developer-extras=true"
SESSION_KEYS = ("WEBKIT_INSPECTOR_HTTP_SERVER", "GSETTINGS_BACKEND")
INSPECTOR = re.compile(r"window\.open\('Main\.html\?ws=' \+ window\.location\.host \+ '(?P<path>/socket/[^']+)'")


def unquote(value: str) -> str:
    """Return `value` without one pair of matching double or single quotes around it."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def session_conf(current: str, url: str, inspector_port: int = INSPECTOR_PORT) -> str:
    """Return the kiosk.conf `current` for a session: URL set to `url` (added when absent), developer extras in front of
    COG_ARGS (quoted, unquoted or absent), and the inspector address and GSETTINGS_BACKEND=memory replacing any such lines."""
    lines, has_url, has_args = [], False, False
    for line in current.splitlines():
        name, separator, value = line.partition("=")
        name = name.strip()
        if separator and name == "URL":
            line, has_url = f"URL={url}", True
        elif separator and name == "COG_ARGS":
            words = " ".join(word for word in (DEVELOPER_EXTRAS, unquote(value)) if word)
            line, has_args = f'COG_ARGS="{words}"', True
        elif separator and name in SESSION_KEYS:
            continue
        lines.append(line)
    if not has_url:
        lines.insert(0, f"URL={url}")
    if not has_args:
        lines.append(f'COG_ARGS="{DEVELOPER_EXTRAS}"')
    lines += [f"WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:{inspector_port}", "GSETTINGS_BACKEND=memory"]
    return "\n".join(lines) + "\n"


def parse_conf(text: str) -> dict[str, str]:
    """Return the assignments of an EnvironmentFile, quotes stripped, comments, blanks and lines without = skipped."""
    result = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        result[name.strip()] = unquote(value)
    return result


def inspector_url(listing: str, address: str) -> str | None:
    """Return the Web Inspector's URL for the first target in the inspector's page list at `address`, or None without one."""
    match = INSPECTOR.search(listing)
    return f"http://{address}/Main.html?ws={address}{match['path']}" if match else None


def fetch_listing(address: str) -> str:
    """Return the inspector's page list at `address`, or an empty string when it does not answer."""
    try:
        return urllib.request.urlopen(f"http://{address}/", timeout=2).read().decode()
    except OSError:
        return ""


def wait_for_inspector(address: str, timeout: float = 30, fetch=fetch_listing, sleep=time.sleep, clock=time.monotonic) -> str:
    """Return the Web Inspector's URL once its page list names a target, or the list's own URL after `timeout` seconds."""
    deadline = clock() + timeout
    while clock() < deadline:
        found = inspector_url(fetch(address), address)
        if found:
            return found
        sleep(1)
    return f"http://{address}/"


def open_command(app: str, url: str) -> list[str]:
    """Return the command that opens `url` in the macOS application `app`."""
    return ["open", "-a", app, url]


def since_command() -> str:
    """Return the command printing the target's clock in the form journalctl's --since takes."""
    return "date '+%Y-%m-%d %H:%M:%S'"


def loaded_command(since: str) -> str:
    """Return the command counting the kiosk's page loads since `since`."""
    return f"sudo journalctl -u {UNIT} --since '{since}' --no-pager | grep -c '{LOADED}'"


def loaded(output: str) -> bool:
    """Return whether the output of `loaded_command` counts at least one load."""
    return output.strip() not in ("", "0")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_kiosk.py testkit/tests/test_preview_contract.py -q`
Expected: 29 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/kiosk.py testkit/tests/test_preview_kiosk.py testkit/tests/test_preview_contract.py
git commit -m "feat(testkit): rewrite kiosk.conf for a preview session"
```

---

### Task 6: `record`: the session record, stale actions, claim and forget

**Files:**
- Create: `testkit/src/pihero_testkit/preview/record.py`
- Test: `testkit/tests/test_preview_record.py`

**Interfaces:**
- Consumes: `process.alive`, `process.info`, `process.entry`, `process.wait_until_gone`.
- Produces: `AlreadyRunning(RuntimeError)`, `stale_actions(record, alive=process.alive) -> list[tuple[str, object]]`, `carry_out(actions, stop_backend, restore_board, *, kill, killpg, getpgid, info, sleep, clock)`, `class Record(directory)` with `path`, `session_dir`, `read() -> dict`, `claim(stop_backend, restore_board, **injectables)`, `update(**fields)`, `forget()`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_record.py
import json
import signal

import pytest

from pihero_testkit.preview import record

pytestmark = pytest.mark.tier0
STARTED = "Fri Oct  3 10:11:12 2026"


class TestStaleActions:
    def test_refuses_to_start_next_to_a_running_preview(self):
        with pytest.raises(record.AlreadyRunning, match=r"a preview is already running \(process 100\)"):
            record.stale_actions({"owner": [100, STARTED]}, alive=lambda entry: entry[0] == 100)

    def test_ends_what_a_killed_preview_left_behind(self):
        stale = {"owner": [100, STARTED], "qemu": [200, STARTED], "dev_server": [300, STARTED], "tunnel": [400, STARTED], "device": "pi@host", "backend": True}

        actions = record.stale_actions(stale, alive=lambda entry: entry[0] != 100)

        assert actions == [("terminate", 200), ("terminate-group", 300), ("terminate", 400), ("restore-device", "pi@host"), ("stop-backend", None)]

    def test_leaves_alone_a_process_that_reuses_the_recorded_id(self):
        actions = record.stale_actions({"owner": [100, STARTED], "qemu": [200, STARTED]}, alive=lambda entry: False)

        assert actions == []

    def test_does_nothing_for_an_empty_record(self):
        assert record.stale_actions({}, alive=lambda entry: True) == []

    def test_reads_a_record_of_the_older_format_without_crashing(self):
        older = {"owner": 1234, "gradle": 5678, "broker": True}

        actions = record.stale_actions(older, alive=lambda entry: isinstance(entry, list))

        assert actions == []


class TestCarryOut:
    def test_terminates_processes_and_groups_and_waits_for_them(self):
        calls = []
        gone = {200: 1, 300: 1}

        def info(pid):
            gone[pid] -= 1
            return (STARTED, "S") if gone[pid] >= 0 else None

        record.carry_out(
            [("terminate", 200), ("terminate-group", 300)], stop_backend=lambda: calls.append("stop"), restore_board=lambda t: calls.append(t),
            kill=lambda pid, sig: calls.append(("kill", pid, sig)), killpg=lambda pgid, sig: calls.append(("killpg", pgid, sig)), getpgid=lambda pid: pid + 1,
            info=info, sleep=lambda s: None, clock=counter(),
        )

        assert calls == [("kill", 200, signal.SIGTERM), ("killpg", 301, signal.SIGTERM)]
        assert gone == {200: -1, 300: -1}

    def test_restores_the_board_and_stops_the_backend(self):
        calls = []

        record.carry_out([("restore-device", "pi@host"), ("stop-backend", None)], stop_backend=lambda: calls.append("stop"), restore_board=calls.append, info=lambda pid: None)

        assert calls == ["pi@host", "stop"]

    def test_skips_a_process_that_ended_meanwhile(self):
        def kill(pid, sig):
            raise ProcessLookupError

        record.carry_out([("terminate", 200)], stop_backend=lambda: None, restore_board=lambda t: None, kill=kill, info=lambda pid: None)


class TestRecord:
    def test_claim_records_this_process_as_the_owner(self, tmp_path):
        rec = record.Record(tmp_path)

        rec.claim(stop_backend=lambda: None, restore_board=lambda t: None, alive=lambda entry: False)

        assert rec.read()["owner"][0] == __import__("os").getpid()

    def test_claim_ends_the_stale_session_and_removes_its_directory(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED], "backend": True}))
        rec.session_dir.mkdir()
        stopped = []

        rec.claim(stop_backend=lambda: stopped.append(True), restore_board=lambda t: None, alive=lambda entry: False)

        assert stopped == [True]
        assert not rec.session_dir.exists()

    def test_claim_treats_a_corrupt_record_as_empty(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text('{"owner": [1, "Fri')

        rec.claim(stop_backend=lambda: None, restore_board=lambda t: None, alive=lambda entry: pytest.fail("asked"))

        assert "owner" in rec.read()

    def test_claim_raises_next_to_a_live_owner_and_changes_nothing(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED]}))

        with pytest.raises(record.AlreadyRunning):
            rec.claim(stop_backend=lambda: None, restore_board=lambda t: None, alive=lambda entry: True)

        assert rec.read() == {"owner": [1, STARTED]}

    def test_update_adds_fields(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED]}))

        rec.update(qemu=[2, STARTED], inspector=54321)

        assert rec.read() == {"owner": [1, STARTED], "qemu": [2, STARTED], "inspector": 54321}

    def test_forget_deletes_the_record(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED], "dev_server": [2, STARTED]}))

        rec.forget()

        assert not rec.path.exists()

    def test_forget_keeps_only_a_board_that_still_runs_the_session(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED], "device": "pi@host"}))

        rec.forget()

        assert rec.read() == {"device": "pi@host"}

    def test_forget_is_done_on_a_missing_record(self, tmp_path):
        record.Record(tmp_path).forget()

    def test_read_is_empty_without_a_record(self, tmp_path):
        assert record.Record(tmp_path).read() == {}


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_record.py -q`
Expected: FAIL with `ImportError: cannot import name 'record'`

- [ ] **Step 3: Write record.py**

```python
# testkit/src/pihero_testkit/preview/record.py
"""The session record: what a preview started, so a killed one is cleaned up by the next and a second one is refused."""

import json
import os
import shutil
import signal
import time
from collections.abc import Callable
from pathlib import Path

from . import process

ENDED_BY = (("qemu", "terminate"), ("dev_server", "terminate-group"), ("tunnel", "terminate"))


class AlreadyRunning(RuntimeError):
    pass


def stale_actions(record: dict, alive=process.alive) -> list[tuple[str, object]]:
    """Return what a killed preview left behind that must be ended; raise AlreadyRunning while its owner still runs."""
    owner = record.get("owner")
    if owner and alive(owner):
        raise AlreadyRunning(f"a preview is already running (process {owner[0]}); end it with Ctrl-C first")
    actions: list[tuple[str, object]] = []
    for key, action in ENDED_BY:
        entry = record.get(key)
        if entry and alive(entry):
            actions.append((action, entry[0]))
    if record.get("device"):
        actions.append(("restore-device", record["device"]))
    if record.get("backend"):
        actions.append(("stop-backend", None))
    return actions


def carry_out(actions, stop_backend: Callable[[], None], restore_board: Callable[[str], None], *, kill=os.kill, killpg=os.killpg, getpgid=os.getpgid, info=process.info, sleep=time.sleep, clock=time.monotonic) -> None:
    """Carry out `actions` and wait until the ended processes are gone; a process that ended meanwhile is skipped."""
    ended = []
    for action, subject in actions:
        try:
            if action == "terminate":
                kill(subject, signal.SIGTERM)
                ended.append(subject)
            elif action == "terminate-group":
                killpg(getpgid(subject), signal.SIGTERM)
                ended.append(subject)
            elif action == "restore-device":
                restore_board(subject)
            elif action == "stop-backend":
                stop_backend()
        except ProcessLookupError:
            pass
    process.wait_until_gone(ended, info, sleep=sleep, clock=clock)


class Record:
    """The record under one app's state directory: `session.json`, and the session directory next to it."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "session.json"
        self.session_dir = directory / "session"

    def read(self) -> dict:
        """Return the record, empty when missing or unreadable."""
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def claim(self, stop_backend: Callable[[], None], restore_board: Callable[[str], None], *, alive=process.alive, info=process.info, kill=os.kill, killpg=os.killpg, getpgid=os.getpgid, sleep=time.sleep, clock=time.monotonic) -> None:
        """End what a killed preview left behind, delete its session directory, and record this process as the owner; raise AlreadyRunning next to a live one."""
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            carry_out(stale_actions(self.read(), alive), stop_backend, restore_board, kill=kill, killpg=killpg, getpgid=getpgid, info=info, sleep=sleep, clock=clock)
            shutil.rmtree(self.session_dir, ignore_errors=True)
        self.path.write_text(json.dumps({"owner": process.entry(os.getpid(), info)}))

    def update(self, **fields) -> None:
        """Add `fields` to the record."""
        self.path.write_text(json.dumps({**self.read(), **fields}))

    def forget(self) -> None:
        """Delete the record, keeping only a board that still runs the session so the next start retries its restore."""
        device = self.read().get("device")
        if device:
            self.path.write_text(json.dumps({"device": device}))
        else:
            self.path.unlink(missing_ok=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_record.py -q`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/record.py testkit/tests/test_preview_record.py
git commit -m "feat(testkit): record a preview session and recover a killed one"
```

---

### Task 7: `dev_server`: start, wait for, and stop the app's dev server

**Files:**
- Create: `testkit/src/pihero_testkit/preview/dev_server.py`
- Test: `testkit/tests/test_preview_dev_server.py`

**Interfaces:**
- Consumes: `api.DevServer`, `process.answers`.
- Produces: `LOG_NAME = "dev-server.log"`, `start(server, root, log, environ=os.environ, popen=subprocess.Popen) -> Popen`, `wait_until_serving(proc, port, log, timeout=900, answers, sleep, clock)`, `ensure(server, root, log, *, answers, start, wait, stop) -> Popen`, `stop(proc, killpg=os.killpg, timeout=30)`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_dev_server.py
import signal
import subprocess
from types import SimpleNamespace

import pytest

from pihero_testkit.preview import dev_server
from pihero_testkit.preview.api import DevServer

pytestmark = pytest.mark.tier0
SERVER = DevServer(["./gradlew", "--console=plain", "jsBrowserDevelopmentRun", "--continuous"], 8081, {"NETMON_STATS_PROXY": "http://netmon.local"})


class TestStart:
    def test_runs_the_command_in_the_root_in_its_own_session_with_the_env_added(self, tmp_path):
        calls = []

        dev_server.start(SERVER, tmp_path, tmp_path / "dist" / "preview" / "dev-server.log", environ={"PATH": "/bin"}, popen=lambda argv, **kw: calls.append((argv, kw)))

        argv, kw = calls[0]
        assert argv == SERVER.argv
        assert kw["cwd"] == tmp_path
        assert kw["env"] == {"PATH": "/bin", "NETMON_STATS_PROXY": "http://netmon.local"}
        assert kw["start_new_session"] is True
        assert kw["stderr"] is subprocess.STDOUT
        assert (tmp_path / "dist" / "preview").is_dir()


class TestWaitUntilServing:
    def test_returns_once_the_port_answers(self, tmp_path):
        answers = iter([False, False, True])

        dev_server.wait_until_serving(SimpleNamespace(poll=lambda: None), 8081, tmp_path / "log", answers=lambda h, p: next(answers), sleep=lambda s: None, clock=counter())

    def test_fails_early_when_the_process_ends(self, tmp_path):
        with pytest.raises(RuntimeError, match=f"dev server exited with status 1; see {tmp_path / 'log'}"):
            dev_server.wait_until_serving(SimpleNamespace(poll=lambda: 1, returncode=1), 8081, tmp_path / "log", answers=lambda h, p: False, sleep=lambda s: None, clock=counter())

    def test_times_out_naming_the_log(self, tmp_path):
        with pytest.raises(TimeoutError, match="nothing answers on port 8081 after 900 s"):
            dev_server.wait_until_serving(SimpleNamespace(poll=lambda: None), 8081, tmp_path / "log", answers=lambda h, p: False, sleep=lambda s: None, clock=counter(step=500))


class TestEnsure:
    def test_refuses_a_port_something_already_answers_on(self, tmp_path):
        with pytest.raises(RuntimeError, match="something already answers on port 8081; end it first"):
            dev_server.ensure(SERVER, tmp_path, tmp_path / "log", answers=lambda h, p: True, start=lambda *a, **k: pytest.fail("started"))

    def test_starts_and_waits(self, tmp_path):
        proc = SimpleNamespace(poll=lambda: None)
        waited = []

        result = dev_server.ensure(SERVER, tmp_path, tmp_path / "log", answers=lambda h, p: False, start=lambda *a, **k: proc, wait=lambda p, port, log: waited.append(port))

        assert result is proc
        assert waited == [8081]

    def test_stops_the_process_when_the_wait_fails(self, tmp_path):
        proc = SimpleNamespace(poll=lambda: None)
        stopped = []

        def wait(p, port, log):
            raise TimeoutError("no")

        with pytest.raises(TimeoutError):
            dev_server.ensure(SERVER, tmp_path, tmp_path / "log", answers=lambda h, p: False, start=lambda *a, **k: proc, wait=wait, stop=stopped.append)

        assert stopped == [proc]


class TestStop:
    def test_terminates_the_process_group(self):
        calls = []
        proc = SimpleNamespace(pid=77, poll=lambda: None, wait=lambda t: None)

        dev_server.stop(proc, killpg=lambda pgid, sig: calls.append((pgid, sig)))

        assert calls == [(77, signal.SIGTERM)]

    def test_kills_the_group_when_it_does_not_end(self):
        calls = []

        def wait(timeout):
            raise subprocess.TimeoutExpired("gradle", timeout)

        dev_server.stop(SimpleNamespace(pid=77, poll=lambda: None, wait=wait), killpg=lambda pgid, sig: calls.append(sig))

        assert calls == [signal.SIGTERM, signal.SIGKILL]

    def test_does_nothing_for_an_ended_process(self):
        dev_server.stop(SimpleNamespace(pid=77, poll=lambda: 0), killpg=lambda pgid, sig: pytest.fail("killed"))


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_dev_server.py -q`
Expected: FAIL with `ImportError: cannot import name 'dev_server'`

- [ ] **Step 3: Write dev_server.py**

```python
# testkit/src/pihero_testkit/preview/dev_server.py
"""The app's dev server for a session: started in its own process group, waited for on its port, ended as a group."""

import os
import signal
import subprocess
import time
from pathlib import Path

from . import process
from .api import DevServer

LOG_NAME = "dev-server.log"


def start(server: DevServer, root: Path, log: Path, environ=os.environ, popen=subprocess.Popen) -> subprocess.Popen:
    """Start `server` in `root` with its env added, output to `log`, in a new session so its whole group can be ended."""
    log.parent.mkdir(parents=True, exist_ok=True)
    return popen(server.argv, cwd=root, env={**environ, **server.env}, stdout=log.open("w"), stderr=subprocess.STDOUT, start_new_session=True)


def wait_until_serving(proc, port: int, log: Path, timeout: float = 900, answers=process.answers, sleep=time.sleep, clock=time.monotonic) -> None:
    """Return once `port` answers; raise RuntimeError when the process ends first, TimeoutError after `timeout` seconds."""
    deadline = clock() + timeout
    while clock() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"the dev server exited with status {proc.returncode}; see {log}")
        if answers("127.0.0.1", port):
            return
        sleep(1)
    raise TimeoutError(f"nothing answers on port {port} after {timeout:g} s; see {log}")


def stop(proc: subprocess.Popen, killpg=os.killpg, timeout: float = 30) -> None:
    """End the process group of `proc` with SIGTERM, then SIGKILL after `timeout` seconds; nothing for an ended process."""
    if proc.poll() is not None:
        return
    killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        killpg(proc.pid, signal.SIGKILL)


def ensure(server: DevServer, root: Path, log: Path, *, answers=process.answers, start=start, wait=wait_until_serving, stop=stop) -> subprocess.Popen:
    """Start `server` and return its process once it serves; raise RuntimeError when something already answers on its port."""
    if answers("127.0.0.1", server.port):
        raise RuntimeError(f"something already answers on port {server.port}; end it first")
    proc = start(server, root, log)
    try:
        wait(proc, server.port, log)
    except BaseException:
        stop(proc)
        raise
    return proc
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_dev_server.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/dev_server.py testkit/tests/test_preview_dev_server.py
git commit -m "feat(testkit): run an app's dev server for a preview"
```

---

### Task 8: `window`: place QEMU's window by pid, cascaded

**Files:**
- Create: `testkit/src/pihero_testkit/preview/window.py`
- Test: `testkit/tests/test_preview_window.py`

**Interfaces:**
- Produces: `TITLE_BAR = 32`, `ORIGIN = (120, 80)`, `STEP = 40`, `PROCESS = "qemu-system-aarch64"`, `points(display) -> tuple[int, int]`, `origin(others) -> tuple[int, int]`, `other_windows(pid, listing) -> int`, `listing(run) -> str`, `script(pid, size, origin) -> list[str]`, `place(pid, display, attempts=20, run, sleep, report) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_window.py
from subprocess import CompletedProcess

import pytest

from pihero_testkit.preview import window

pytestmark = pytest.mark.tier0
PS = """\
  501 /opt/homebrew/bin/qemu-system-aarch64 -M virt -display cocoa,zoom-to-fit=on -m 1024
  502 /opt/homebrew/bin/qemu-system-aarch64 -M virt -display none -m 1024
  503 /opt/homebrew/bin/qemu-system-aarch64 -M virt -display cocoa,zoom-to-fit=on -m 1024
  504 vim notes.txt
"""


class TestPoints:
    def test_is_the_display_plus_the_title_bar(self):
        assert window.points((800, 480)) == (800, 512)
        assert window.points((480, 320)) == (480, 352)


class TestOrigin:
    def test_starts_at_the_default_and_steps_per_other_window(self):
        assert window.origin(0) == (120, 80)
        assert window.origin(2) == (200, 160)


class TestOtherWindows:
    def test_counts_qemu_processes_with_a_cocoa_display_other_than_the_pid(self):
        assert window.other_windows(501, PS) == 1

    def test_is_zero_when_this_vm_is_the_only_one(self):
        assert window.other_windows(501, PS.replace("  503", "  599 other")) == 0


class TestScript:
    def test_targets_the_process_by_its_unix_id_and_sets_position_then_size(self):
        argv = window.script(501, (800, 512), (120, 80))

        target = 'tell application "System Events" to tell (first process whose unix id is 501)'
        assert argv == ["osascript", "-e", f"{target} to set position of window 1 to {{120, 80}}", "-e", f"{target} to set size of window 1 to {{800, 512}}"]


class TestPlace:
    def test_places_the_window_once_system_events_accepts(self):
        results = iter([1, 1, 0])
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return CompletedProcess(argv, next(results), "", "")

        placed = window.place(501, (800, 480), run=run, sleep=lambda s: None, report=lambda m: pytest.fail(m))

        assert placed is True
        assert len(calls) == 4
        assert calls[0] == ["ps", "-axo", "pid=,command="]
        assert "set size of window 1 to {800, 512}" in calls[-1][-1]

    def test_reports_the_accessibility_hint_and_gives_up_after_the_attempts(self):
        reported = []

        placed = window.place(501, (800, 480), attempts=2, run=lambda argv, **kw: CompletedProcess(argv, 1, "", ""), sleep=lambda s: None, report=reported.append)

        assert placed is False
        assert reported == ["could not place the VM's window; allow your terminal under Privacy & Security > Accessibility"]

    def test_cascades_behind_the_other_vm_windows(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return CompletedProcess(argv, 0, PS if argv[0] == "ps" else "", "")

        window.place(501, (800, 480), run=run, sleep=lambda s: None, report=lambda m: None)

        assert "set position of window 1 to {160, 120}" in calls[-1][2]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_window.py -q`
Expected: FAIL with `ImportError: cannot import name 'window'`

- [ ] **Step 3: Write window.py**

```python
# testkit/src/pihero_testkit/preview/window.py
"""Places a session's QEMU window: found by its process id, sized to the display, cascaded behind the other VM windows."""

import subprocess
import sys
import time
from collections.abc import Callable

TITLE_BAR = 32
ORIGIN = (120, 80)
STEP = 40
PROCESS = "qemu-system-aarch64"
HINT = "could not place the VM's window; allow your terminal under Privacy & Security > Accessibility"


def points(display: tuple[int, int]) -> tuple[int, int]:
    """Return the window's size in points for `display`: one point per pixel plus the title bar."""
    return display[0], display[1] + TITLE_BAR


def origin(others: int) -> tuple[int, int]:
    """Return the window's origin with `others` VM windows already open, one step down and right per window."""
    return ORIGIN[0] + STEP * others, ORIGIN[1] + STEP * others


def listing(run=subprocess.run) -> str:
    """Return every process as `pid command`, one per line."""
    return run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=False).stdout


def other_windows(pid: int, listing: str) -> int:
    """Return how many QEMU processes other than `pid` show a cocoa window in `listing`."""
    count = 0
    for line in listing.splitlines():
        words = line.split(None, 1)
        if len(words) == 2 and PROCESS in words[1] and "-display cocoa" in words[1] and int(words[0]) != pid:
            count += 1
    return count


def script(pid: int, size: tuple[int, int], origin: tuple[int, int]) -> list[str]:
    """Return the osascript command that moves and sizes the first window of the process `pid`."""
    target = f'tell application "System Events" to tell (first process whose unix id is {pid})'
    return [
        "osascript",
        "-e", f"{target} to set position of window 1 to {{{origin[0]}, {origin[1]}}}",
        "-e", f"{target} to set size of window 1 to {{{size[0]}, {size[1]}}}",
    ]


def place(pid: int, display: tuple[int, int], attempts: int = 20, run=subprocess.run, sleep=time.sleep, report: Callable[[str], None] = lambda message: print(message, file=sys.stderr)) -> bool:
    """Place the window of the QEMU process `pid` for `display`, trying once a second; return whether macOS allowed it, reporting the hint when not."""
    at = origin(other_windows(pid, listing(run)))
    for _ in range(attempts):
        if run(script(pid, points(display), at), capture_output=True, text=True, check=False).returncode == 0:
            return True
        sleep(1)
    report(HINT)
    return False
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_window.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/window.py testkit/tests/test_preview_window.py
git commit -m "feat(testkit): place a preview's VM window by its process"
```

---

### Task 9: `layer`: the provisioned disk layer, cached and built under a lock

**Files:**
- Create: `testkit/src/pihero_testkit/preview/layer.py`
- Test: `testkit/tests/test_preview_layer.py`

**Interfaces:**
- Consumes: `prepare.prepare`, `prepare.BaseImage`, `vm.provisioned_vm`, `device_file.write`, `locks.held`, `kiosk.PACKAGE`.
- Produces: `CACHE`, `Layer(rootfs, bootfs)`, `name(base_id, user_data) -> str`, `layer_for(base, user_data, cache) -> Layer`, `build_layer(device, accel, display, into)`, `ensure(app, cache=CACHE, accel="hvf", *, build=build_layer, prepare_base=prepare.prepare, report) -> Layer`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_layer.py
from pathlib import Path
from types import SimpleNamespace

import pytest

from pihero_testkit import prepare
from pihero_testkit.preview import layer

pytestmark = pytest.mark.tier0
BASE = prepare.BaseImage(Path("/cache/base/aa0c21373d89/rootfs.qcow2"), Path("/b/vmlinuz"), Path("/b/initrd.img"), Path("/b/boot"))
USER_DATA = "#cloud-config\npackages:\n  - pihero-kiosk\n"


class TestName:
    def test_is_twelve_hex_digits(self):
        name = layer.name("aa0c21373d89", USER_DATA)

        assert len(name) == 12 and int(name, 16) >= 0

    def test_is_stable(self):
        assert layer.name("a", "b") == layer.name("a", "b")

    @pytest.mark.parametrize("other", [("x", "b"), ("a", "x")])
    def test_changes_with_the_base_image_and_with_the_user_data(self, other):
        assert layer.name(*other) != layer.name("a", "b")

    def test_does_not_confuse_where_the_two_parts_meet(self):
        assert layer.name("ab", "c") != layer.name("a", "bc")


class TestLayerFor:
    def test_lives_under_the_cache_in_a_directory_of_its_name(self, tmp_path):
        found = layer.layer_for(BASE, USER_DATA, cache=tmp_path)

        name = layer.name("aa0c21373d89", USER_DATA)
        assert found == layer.Layer(tmp_path / name / "rootfs.qcow2", tmp_path / name / "bootfs.img")


class TestEnsure:
    def test_returns_an_existing_layer_without_building(self, tmp_path):
        existing = layer.layer_for(BASE, USER_DATA, tmp_path)
        existing.rootfs.parent.mkdir()
        existing.rootfs.touch()
        existing.bootfs.touch()

        found = layer.ensure(app(tmp_path), cache=tmp_path, build=lambda *a: pytest.fail("built"), prepare_base=lambda: BASE, report=lambda m: None)

        assert found == existing

    def test_builds_into_a_building_directory_then_renames_it_read_only(self, tmp_path):
        seen = {}

        def build(device, accel, display, into):
            seen.update(device=device, accel=accel, display=display, into=into)
            (into / "rootfs.qcow2").write_text("disk")
            (into / "bootfs.img").write_text("boot")

        found = layer.ensure(app(tmp_path), cache=tmp_path, build=build, prepare_base=lambda: BASE, report=lambda m: None)

        assert seen["into"] == tmp_path / f"{found.rootfs.parent.name}.building"
        assert (seen["device"], seen["accel"], seen["display"]) == (tmp_path / "dist" / "preview" / "preview-device", "hvf", (800, 480))
        assert (seen["device"] / "user-data").read_text() == USER_DATA
        assert found.rootfs.read_text() == "disk" and found.bootfs.read_text() == "boot"
        assert not seen["into"].exists()
        assert oct(found.rootfs.stat().st_mode)[-3:] == "444"

    def test_removes_a_building_directory_a_dead_build_left(self, tmp_path):
        name = layer.name("aa0c21373d89", USER_DATA)
        stale = tmp_path / f"{name}.building"
        stale.mkdir(parents=True)
        (stale / "rootfs.qcow2").write_text("half")

        def build(device, accel, display, into):
            assert not (into / "rootfs.qcow2").exists()
            (into / "rootfs.qcow2").touch()
            (into / "bootfs.img").touch()

        layer.ensure(app(tmp_path), cache=tmp_path, build=build, prepare_base=lambda: BASE, report=lambda m: None)

    def test_takes_the_lock_of_the_layer_while_building(self, tmp_path):
        name = layer.name("aa0c21373d89", USER_DATA)

        def build(device, accel, display, into):
            import fcntl
            with (tmp_path / f"{name}.lock").open("w") as handle:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            (into / "rootfs.qcow2").touch()
            (into / "bootfs.img").touch()

        layer.ensure(app(tmp_path), cache=tmp_path, build=build, prepare_base=lambda: BASE, report=lambda m: None)

    def test_announces_the_build(self, tmp_path):
        reported = []

        def build(device, accel, display, into):
            (into / "rootfs.qcow2").touch()
            (into / "bootfs.img").touch()

        layer.ensure(app(tmp_path), cache=tmp_path, build=build, prepare_base=lambda: BASE, report=reported.append)

        assert reported == ["building the preview's base layer, once per base image and device file (about 2.5 minutes)"]

    def test_refuses_a_device_file_without_the_kiosk(self, tmp_path):
        with pytest.raises(ValueError, match="must install pihero-kiosk"):
            layer.ensure(app(tmp_path, user_data="#cloud-config\npackages:\n  - pihero\n"), cache=tmp_path, build=lambda *a: pytest.fail("built"), prepare_base=lambda: BASE, report=lambda m: None)


def app(root: Path, user_data: str = USER_DATA):
    return SimpleNamespace(name="probe", root=root, display=(800, 480), user_data=lambda: user_data)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_layer.py -q`
Expected: FAIL with `ImportError: cannot import name 'layer'`

- [ ] **Step 3: Write layer.py**

```python
# testkit/src/pihero_testkit/preview/layer.py
"""The disk a preview's VM boots from: the app's device file provisioned once per base image and kept as a read-only layer."""

import hashlib
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import device_file, locks, prepare
from ..vm import provisioned_vm
from . import kiosk
from .api import KioskApp

CACHE = Path.home() / ".cache" / "pihero" / "preview"
DEVICE_DIR = "preview-device"


@dataclass(frozen=True)
class Layer:
    rootfs: Path
    bootfs: Path


def name(base_id: str, user_data: str) -> str:
    """Return the layer's name: twelve hex digits of the base image's id and the rendered user-data."""
    return hashlib.sha256(f"{base_id}\0{user_data}".encode()).hexdigest()[:12]


def layer_for(base: prepare.BaseImage, user_data: str, cache: Path) -> Layer:
    """Return where the layer for `base` and `user_data` lives under `cache`."""
    directory = cache / name(base.rootfs.parent.name, user_data)
    return Layer(directory / "rootfs.qcow2", directory / "bootfs.img")


def build_layer(device: Path, accel: str, display: tuple[int, int], into: Path) -> None:
    """Provision the device directory `device` in a VM, power it off, and copy its disk and boot image into `into`."""
    with provisioned_vm([], device, accel, keep=False, display=f"{display[0]}x{display[1]}") as vm:
        vm.ssh("sudo poweroff", timeout=30)
        vm.wait_exit()
        shutil.copy(vm.overlay, into / "rootfs.qcow2")
        shutil.copy(vm.bootfs, into / "bootfs.img")


def ensure(app: KioskApp, cache: Path = CACHE, accel: str = "hvf", *, build: Callable[[Path, str, tuple[int, int], Path], None] = build_layer, prepare_base=prepare.prepare, report: Callable[[str], None] = lambda message: print(message, file=sys.stderr, flush=True)) -> Layer:
    """Return the layer for the current base image and the app's device file, building it under a lock when the cache has none.

    Raise ValueError when the device file does not install pihero-kiosk.
    """
    user_data = app.user_data()
    if kiosk.PACKAGE not in user_data:
        raise ValueError(f"the preview's device file must install {kiosk.PACKAGE}; add it to its packages")
    base = prepare_base()
    device = device_file.write(app.root / "dist" / "preview" / DEVICE_DIR, user_data)
    layer = layer_for(base, user_data, cache)
    if layer.rootfs.exists() and layer.bootfs.exists():
        return layer
    directory = layer.rootfs.parent
    with locks.held(cache / f"{directory.name}.lock"):
        if layer.rootfs.exists() and layer.bootfs.exists():
            return layer
        report("building the preview's base layer, once per base image and device file (about 2.5 minutes)")
        building = cache / f"{directory.name}.building"
        shutil.rmtree(building, ignore_errors=True)
        building.mkdir(parents=True)
        build(device, accel, app.display, building)
        for artifact in building.iterdir():
            artifact.chmod(0o444)
        os.replace(building, directory)
    return layer
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_layer.py -q`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/layer.py testkit/tests/test_preview_layer.py
git commit -m "feat(testkit): cache a preview's provisioned layer under a lock"
```

---

### Task 10: `vm`: one VM session on an overlay of the layer

**Files:**
- Create: `testkit/src/pihero_testkit/preview/vm.py`
- Test: `testkit/tests/test_preview_vm.py`

**Interfaces:**
- Consumes: `pihero_testkit.vm.Vm`, `pihero_testkit.vm.SSH_OPTS`, `prepare.prepare`, `layer.Layer`, `kiosk.*`, `window.place`.
- Produces: `class Session(layer, directory, display, accel="hvf", *, make_vm=Vm, prepare_base=prepare.prepare, place=window.place, run=subprocess.run, popen=subprocess.Popen, sleep, clock)` with `start(on_qemu=None) -> Vm`, `place_window() -> bool`, `configure_kiosk(url)`, `restart_kiosk(timeout=90)`, `keep_serial_log() -> Path`, `open_tunnel(local_port)`, `stop()`, `ssh_argv(command, *options) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_vm.py
import re
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from pihero_testkit.preview import kiosk, layer
from pihero_testkit.preview import vm as preview_vm

pytestmark = pytest.mark.tier0
LAYER = layer.Layer(Path("/cache/preview/abc/rootfs.qcow2"), Path("/cache/preview/abc/bootfs.img"))


class TestStart:
    def test_boots_a_windowed_vm_on_an_overlay_of_the_layer_at_the_apps_display(self, tmp_path):
        (tmp_path / "layer").mkdir()
        bootfs = tmp_path / "layer" / "bootfs.img"
        bootfs.write_bytes(b"boot")
        made = {}
        fake = FakeVm()

        def make_vm(base, bootfs_copy, workdir, **kwargs):
            made.update(base=base, bootfs=bootfs_copy, workdir=workdir, **kwargs)
            return fake

        session = preview_vm.Session(layer.Layer(tmp_path / "layer" / "rootfs.qcow2", bootfs), tmp_path / "session", (480, 320), make_vm=make_vm, prepare_base=lambda: "BASE")
        pids = []

        started = session.start(on_qemu=pids.append)

        assert started is fake
        assert made["base"] == "BASE"
        assert made["bootfs"] == tmp_path / "session" / "bootfs.img" and made["bootfs"].read_bytes() == b"boot"
        assert (made["accel"], made["display"], made["window"], made["backing"], made["repo_port"]) == ("hvf", "480x320", True, tmp_path / "layer" / "rootfs.qcow2", 0)
        assert pids == [4242]
        assert fake.waited_ssh

    def test_keeps_the_serial_log_when_ssh_never_answers(self, tmp_path):
        (tmp_path / "layer").mkdir()
        (tmp_path / "layer" / "bootfs.img").write_bytes(b"boot")
        fake = FakeVm(ssh_fails=True)
        fake.serial_log = tmp_path / "session" / "serial.log"
        fake.serial_log.parent.mkdir()
        fake.serial_log.write_text("boot messages")
        session = preview_vm.Session(layer.Layer(tmp_path / "layer" / "rootfs.qcow2", tmp_path / "layer" / "bootfs.img"), tmp_path / "session", (800, 480), make_vm=lambda *a, **k: fake, prepare_base=lambda: "BASE")

        with pytest.raises(RuntimeError, match=re.escape(str(tmp_path / "serial.log"))):
            session.start()

        assert (tmp_path / "serial.log").read_text() == "boot messages"


class TestConfigureKiosk:
    def test_writes_the_session_conf_over_the_guests_and_restarts_the_kiosk(self, tmp_path):
        fake = FakeVm(conf='URL=http://localhost/\nCOG_ARGS="--doc-viewer"\n')
        runs = []
        session = session_with(fake, tmp_path, run=lambda argv, **kw: runs.append((argv, kw)) or CompletedProcess(argv, 0, "", ""))

        session.configure_kiosk("http://10.0.2.2:8081/")

        argv, kw = runs[0]
        assert argv[-1] == f"sudo tee {kiosk.CONF} >/dev/null"
        assert kw["input"] == kiosk.session_conf('URL=http://localhost/\nCOG_ARGS="--doc-viewer"\n', "http://10.0.2.2:8081/")
        assert f"sudo systemctl restart {kiosk.UNIT}" in fake.commands


class TestRestartKiosk:
    def test_returns_once_the_journal_shows_the_page_loaded(self, tmp_path):
        fake = FakeVm(loaded=iter(["0\n", "0\n", "1\n"]))
        session = session_with(fake, tmp_path)

        session.restart_kiosk()

        assert fake.commands[0] == kiosk.since_command()
        assert fake.commands[1] == f"sudo systemctl restart {kiosk.UNIT}"
        assert fake.commands[2] == kiosk.loaded_command("2026-10-03 10:00:00")

    def test_raises_naming_the_kept_serial_log_when_the_page_never_loads(self, tmp_path):
        fake = FakeVm(loaded=iter(["0\n"] * 100))
        fake.serial_log.parent.mkdir(parents=True)
        fake.serial_log.write_text("boot messages")
        session = session_with(fake, tmp_path, clock=counter(step=50))

        with pytest.raises(TimeoutError, match=re.escape(f"did not load its page within 90 s; see {tmp_path / 'serial.log'}")):
            session.restart_kiosk()

        assert (tmp_path / "serial.log").read_text() == "boot messages"


class TestOpenTunnel:
    def test_forwards_the_local_port_to_the_guests_inspector(self, tmp_path):
        fake = FakeVm()
        opened = []
        session = session_with(fake, tmp_path, popen=lambda argv, **kw: opened.append(argv) or SimpleNamespace(poll=lambda: None, terminate=lambda: None))

        session.open_tunnel(54321)

        argv = opened[0]
        assert argv[:2] == ["ssh", "-i"]
        assert "-N" in argv and argv[argv.index("-L") + 1] == "127.0.0.1:54321:127.0.0.1:2999"
        assert argv[-1] == "pihero@127.0.0.1"


class TestStop:
    def test_removes_the_directory_of_a_session_that_never_started(self, tmp_path):
        directory = tmp_path / "session"
        directory.mkdir()

        preview_vm.Session(LAYER, directory, (800, 480)).stop()

        assert not directory.exists()

    def test_powers_the_guest_off_closes_the_tunnel_and_deletes_the_directory(self, tmp_path):
        fake = FakeVm()
        session = session_with(fake, tmp_path)
        ended = []
        session.tunnel = SimpleNamespace(poll=lambda: None, terminate=lambda: ended.append("tunnel"))
        (tmp_path / "session").mkdir(exist_ok=True)

        session.stop()

        assert ended == ["tunnel"]
        assert fake.commands[-1] == "sudo poweroff"
        assert fake.stopped
        assert not (tmp_path / "session").exists()


class FakeVm:
    def __init__(self, conf: str = "URL=http://localhost/\n", loaded=None, ssh_fails: bool = False):
        self.conf, self.loaded, self.ssh_fails = conf, loaded or iter(["1\n"]), ssh_fails
        self.commands = []
        self.waited_ssh = self.stopped = False
        self.process = SimpleNamespace(pid=4242, poll=lambda: None)
        self.serial_log = Path("/nonexistent/serial.log")
        self.key, self.port, self.user = Path("/k"), 2222, "pihero"

    def start(self):
        return self

    def wait_ssh(self):
        if self.ssh_fails:
            raise TimeoutError("no SSH after 300s")
        self.waited_ssh = True

    def ssh(self, command, timeout=120):
        self.commands.append(command)
        if command == kiosk.since_command():
            return CompletedProcess(command, 0, "2026-10-03 10:00:00\n", "")
        if command.startswith("sudo journalctl"):
            return CompletedProcess(command, 0, next(self.loaded), "")
        if command == f"cat {kiosk.CONF}":
            return CompletedProcess(command, 0, self.conf, "")
        return CompletedProcess(command, 0, "", "")

    def wait_exit(self, timeout=180):
        pass

    def stop(self):
        self.stopped = True


def session_with(fake: FakeVm, tmp_path: Path, **injected) -> preview_vm.Session:
    fake.serial_log = tmp_path / "session" / "serial.log"
    session = preview_vm.Session(LAYER, tmp_path / "session", (800, 480), sleep=lambda s: None, **({"clock": counter()} | injected))
    session.vm = fake
    return session


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_vm.py -q`
Expected: FAIL with `ImportError: cannot import name 'vm' from 'pihero_testkit.preview'`

- [ ] **Step 3: Write vm.py**

```python
# testkit/src/pihero_testkit/preview/vm.py
"""One preview session in a VM: a throwaway overlay of the layer, its window, the kiosk's settings and the inspector's tunnel."""

import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .. import prepare
from ..vm import SSH_OPTS, Vm
from . import kiosk, window
from .layer import Layer


class Session:
    def __init__(self, layer: Layer, directory: Path, display: tuple[int, int], accel: str = "hvf", *, make_vm=Vm, prepare_base=prepare.prepare, place=window.place, run=subprocess.run, popen=subprocess.Popen, sleep=time.sleep, clock=time.monotonic):
        self.layer, self.directory, self.display, self.accel = layer, directory, display, accel
        self._make_vm, self._prepare, self._place, self._run, self._popen, self._sleep, self._clock = make_vm, prepare_base, place, run, popen, sleep, clock
        self.vm: Vm | None = None
        self.tunnel: subprocess.Popen | None = None

    def start(self, on_qemu: Callable[[int], None] | None = None) -> Vm:
        """Boot the VM in a window on a fresh overlay of the layer and wait for ssh; `on_qemu` gets QEMU's pid as soon as it runs."""
        self.directory.mkdir(parents=True, exist_ok=True)
        bootfs = self.directory / "bootfs.img"
        shutil.copy(self.layer.bootfs, bootfs)
        bootfs.chmod(0o644)
        self.vm = self._make_vm(self._prepare(), bootfs, self.directory, accel=self.accel, display=f"{self.display[0]}x{self.display[1]}", window=True, backing=self.layer.rootfs, repo_port=0).start()
        if on_qemu:
            on_qemu(self.vm.process.pid)
        try:
            self.vm.wait_ssh()
        except Exception as error:
            raise RuntimeError(f"{error}\nthe serial log is kept at {self.keep_serial_log()}") from error
        return self.vm

    def place_window(self) -> bool:
        """Place QEMU's window for the display; return whether macOS allowed it."""
        return self._place(self.vm.process.pid, self.display)

    def configure_kiosk(self, url: str) -> None:
        """Write the session's kiosk.conf over the guest's and restart the kiosk until it loads `url`."""
        current = self.vm.ssh(f"cat {kiosk.CONF}").stdout
        updated = kiosk.session_conf(current, url)
        self._run(self.ssh_argv(f"sudo tee {kiosk.CONF} >/dev/null"), input=updated, text=True, check=True, capture_output=True)
        self.restart_kiosk()

    def restart_kiosk(self, timeout: float = 90) -> None:
        """Restart the kiosk and return once its journal shows the page loaded; raise TimeoutError naming the kept serial log."""
        since = self.vm.ssh(kiosk.since_command()).stdout.strip()
        self.vm.ssh(f"sudo systemctl restart {kiosk.UNIT}")
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            if kiosk.loaded(self.vm.ssh(kiosk.loaded_command(since)).stdout):
                return
            self._sleep(1)
        raise TimeoutError(f"the kiosk did not load its page within {timeout:g} s; see {self.keep_serial_log()}")

    def keep_serial_log(self) -> Path:
        """Copy the guest's serial log next to the session directory, which stop() deletes, and return the copy."""
        kept = self.directory.parent / "serial.log"
        kept.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.vm.serial_log, kept)
        return kept

    def open_tunnel(self, local_port: int) -> None:
        """Forward 127.0.0.1:`local_port` on the Mac to the guest's inspector until stop()."""
        forward = f"127.0.0.1:{local_port}:127.0.0.1:{kiosk.INSPECTOR_PORT}"
        self.tunnel = self._popen(self.ssh_argv(None, "-N", "-L", forward), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self) -> None:
        """Close the tunnel, power the guest off (or end QEMU), and delete the session directory."""
        if self.tunnel and self.tunnel.poll() is None:
            self.tunnel.terminate()
        vm = self.vm
        if vm and vm.process and vm.process.poll() is None:
            try:
                vm.ssh("sudo poweroff", timeout=15)
                vm.wait_exit(timeout=30)
            except subprocess.TimeoutExpired:
                pass
            vm.stop()
        shutil.rmtree(self.directory, ignore_errors=True)

    def ssh_argv(self, command: str | None, *options: str) -> list[str]:
        """Return the ssh command for the guest with `options`, running `command` if given."""
        argv = ["ssh", "-i", str(self.vm.key), "-p", str(self.vm.port), *SSH_OPTS, *options, f"{self.vm.user}@127.0.0.1"]
        return argv + [command] if command else argv
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_vm.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/vm.py testkit/tests/test_preview_vm.py
git commit -m "feat(testkit): run a preview session in a windowed VM"
```

---

### Task 11: `board`: one session on a real board

**Files:**
- Create: `testkit/src/pihero_testkit/preview/board.py`
- Test: `testkit/tests/test_preview_board.py`

**Interfaces:**
- Consumes: `pihero_testkit.ssh.command`, `pihero_testkit.ssh.KEEPALIVE`, `kiosk.*`, `process.answers`.
- Produces: `LOG_NAME = "tunnel.log"`, `DROPIN_DIR`, `remote_port(mac_port) -> int`, `forwards(mac_ports, inspector_local) -> list[str]`, `tunnel_command(target, forward_args) -> list[str]`, `class Board(target, name, tunnel_log, *, run=subprocess.run, popen=subprocess.Popen, answers=process.answers, sleep, clock, report)` with `run_dir`, `conf`, `dropin`, `ssh(remote, input=None, timeout=60)`, `check_kiosk()`, `session_conf(url) -> str`, `install_command() -> str`, `restore_command() -> str`, `end_forwards_command(remote_ports) -> str`, `open_tunnel(forward_args, inspector_local, remote_ports) -> Popen`, `install(conf, tunnel, timeout=90)`, `wait_loaded(since, tunnel, timeout)`, `restore() -> bool`, `tunnel_problem(tunnel) -> str | None`, `tunnel_ended(tunnel) -> str`, `close_tunnel(tunnel)`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_board.py
import subprocess
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from pihero_testkit import ssh
from pihero_testkit.preview import board, kiosk

pytestmark = pytest.mark.tier0
TARGET = "pi@netmon.local"
SAMPLE_CONF = 'URL=http://localhost/?broker.host=localhost&broker.port=8080\nCOG_ARGS="--doc-viewer --web-mem-limit=200"\nJSC_useJIT=false\n'


class TestRemotePort:
    @pytest.mark.parametrize("mac_port, expected", [(8081, 18081), (8080, 18080), (1880, 11880), (55535, 65535)])
    def test_is_ten_thousand_above_the_mac_port(self, mac_port, expected):
        assert board.remote_port(mac_port) == expected

    def test_refuses_a_port_that_would_leave_the_range(self):
        with pytest.raises(ValueError, match="55536 .* 55535"):
            board.remote_port(55536)


class TestForwards:
    def test_reverses_every_mac_port_and_forwards_the_inspector(self):
        args = board.forwards([8081, 8080], 54321)

        assert args == ["-R", "127.0.0.1:18081:127.0.0.1:8081", "-R", "127.0.0.1:18080:127.0.0.1:8080", "-L", "127.0.0.1:54321:127.0.0.1:2999"]


class TestTunnelCommand:
    def test_is_a_batch_ipv4_ssh_that_exits_when_a_forward_fails(self):
        argv = board.tunnel_command(TARGET, ["-L", "a"])

        assert argv == ["ssh", "-N", "-4", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=10", *ssh.KEEPALIVE, "-L", "a", TARGET]

    def test_passes_the_targets_port(self):
        argv = board.tunnel_command("pi@netmon.local:2222", [])

        assert argv[-3:] == ["-p", "2222", TARGET]


class TestBoardPaths:
    def test_are_scoped_by_the_apps_name(self, tmp_path):
        b = board.Board(TARGET, "netmon", tmp_path / "tunnel.log")

        assert (b.run_dir, b.conf, b.dropin) == ("/run/netmon-preview", "/run/netmon-preview/kiosk.conf", "/run/systemd/system/pihero-kiosk.service.d/netmon-preview.conf")


class TestCommands:
    def test_install_writes_the_conf_and_the_drop_in_then_restarts(self, tmp_path):
        command = board.Board(TARGET, "netmon", tmp_path / "t").install_command()

        assert command == (
            "sudo install -d /run/netmon-preview /run/systemd/system/pihero-kiosk.service.d && sudo tee /run/netmon-preview/kiosk.conf >/dev/null && "
            "printf '[Service]\\nEnvironmentFile=/run/netmon-preview/kiosk.conf\\n' | sudo tee /run/systemd/system/pihero-kiosk.service.d/netmon-preview.conf >/dev/null && "
            "sudo systemctl daemon-reload && sudo systemctl restart pihero-kiosk"
        )

    def test_restore_removes_both_and_restarts(self, tmp_path):
        command = board.Board(TARGET, "netmon", tmp_path / "t").restore_command()

        assert command == (
            "sudo rm -rf /run/netmon-preview /run/systemd/system/pihero-kiosk.service.d/netmon-preview.conf; "
            "sudo rmdir --ignore-fail-on-non-empty /run/systemd/system/pihero-kiosk.service.d 2>/dev/null; "
            "sudo systemctl daemon-reload && sudo systemctl restart pihero-kiosk"
        )

    def test_end_forwards_kills_the_sshd_listening_on_the_sessions_remote_ports(self, tmp_path):
        command = board.Board(TARGET, "netmon", tmp_path / "t").end_forwards_command([18081, 18080])

        assert command == "sudo ss -ltnpH | grep -E '127\\.0\\.0\\.1:(18081|18080) ' | grep sshd | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u | xargs -r sudo kill"


class TestSsh:
    def test_runs_the_remote_through_the_testkits_ssh_command(self, tmp_path):
        calls = []
        b = board.Board("pi@netmon.local:2222", "netmon", tmp_path / "t", run=lambda argv, **kw: calls.append(argv) or CompletedProcess(argv, 0, "", ""))

        b.ssh("true")

        assert calls == [ssh.command("pi@netmon.local:2222", "true")]
        assert "-p" in calls[0] and "2222" in calls[0]

    def test_turns_a_hanging_connection_into_a_timeout_error(self, tmp_path):
        def run(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

        with pytest.raises(TimeoutError, match="pi@netmon.local did not answer within 60 s"):
            board.Board(TARGET, "netmon", tmp_path / "t", run=run).ssh("true")


class TestCheckKiosk:
    def test_passes_when_the_package_is_installed(self, tmp_path):
        board.Board(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 0, "pihero-kiosk 2.7.0\n", "")).check_kiosk()

    def test_names_the_ssh_error_when_the_board_is_unreachable(self, tmp_path):
        with pytest.raises(RuntimeError, match="cannot reach pi@netmon.local over ssh: Connection refused"):
            board.Board(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 255, "", "Connection refused\n")).check_kiosk()

    def test_asks_for_a_pi_hero_device_file_without_the_kiosk(self, tmp_path):
        with pytest.raises(RuntimeError, match="has no pihero-kiosk; flash a Pi Hero device file first"):
            board.Board(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 1, "", "no packages found\n")).check_kiosk()


class TestSessionConf:
    def test_rewrites_the_boards_own_conf_for_the_session(self, tmp_path):
        b = board.Board(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 0, SAMPLE_CONF, ""))

        conf = b.session_conf("http://127.0.0.1:18081/")

        assert conf == kiosk.session_conf(SAMPLE_CONF, "http://127.0.0.1:18081/")

    def test_fails_when_the_conf_cannot_be_read(self, tmp_path):
        with pytest.raises(RuntimeError, match="cannot read /etc/pihero/kiosk.conf on pi@netmon.local: denied"):
            board.Board(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 1, "", "denied\n")).session_conf("http://x/")


class TestInstall:
    def test_sends_the_conf_and_waits_for_the_page_to_load(self, tmp_path):
        calls = []
        answers = {kiosk.since_command(): "2026-10-03 10:00:00\n"}
        loaded = iter(["0\n", "1\n"])

        def run(argv, **kwargs):
            calls.append((argv[-1], kwargs.get("input")))
            remote = argv[-1]
            out = answers.get(remote, next(loaded) if remote.startswith("sudo journalctl") else "")
            return CompletedProcess(argv, 0, out, "")

        b = board.Board(TARGET, "netmon", tmp_path / "t", run=run, sleep=lambda s: None, clock=counter())

        b.install("CONF", SimpleNamespace(poll=lambda: None))

        assert calls[1] == (b.install_command(), "CONF")
        assert [c[0] for c in calls[2:]] == [kiosk.loaded_command("2026-10-03 10:00:00")] * 2

    def test_fails_early_with_the_tunnels_message_when_it_ends(self, tmp_path):
        log = tmp_path / "tunnel.log"
        log.write_text("channel 3: open failed: connect failed\nremote port forwarding failed for listen port 18081\n")
        b = board.Board(TARGET, "netmon", log, run=lambda argv, **kw: CompletedProcess(argv, 0, "x\n", ""), sleep=lambda s: None, clock=counter())

        with pytest.raises(RuntimeError, match="the ssh tunnel to pi@netmon.local ended: remote port forwarding failed for listen port 18081"):
            b.install("CONF", SimpleNamespace(poll=lambda: 255))

    def test_times_out_asking_about_the_dev_server_and_the_tunnel(self, tmp_path):
        b = board.Board(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 0, "0\n", ""), sleep=lambda s: None, clock=counter(step=50))

        with pytest.raises(TimeoutError, match="did not load its page within 90 s; is the dev server up and the tunnel open"):
            b.install("CONF", SimpleNamespace(poll=lambda: None))


class TestRestore:
    def test_returns_true_when_the_board_answered(self, tmp_path):
        assert board.Board(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 0, "", "")).restore() is True

    def test_warns_and_returns_false_when_it_did_not(self, tmp_path):
        warned = []
        b = board.Board(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 255, "", "no route\n"), report=warned.append)

        assert b.restore() is False
        assert warned == ["could not restore the kiosk on pi@netmon.local: no route; a reboot of the board removes the session's files"]


class TestOpenTunnel:
    def test_ends_stale_forwards_then_opens_the_tunnel_and_waits_for_the_inspector_port(self, tmp_path):
        remotes, popened = [], []
        tunnel = SimpleNamespace(poll=lambda: None, pid=9)
        answers = iter([False, True])
        b = board.Board(TARGET, "netmon", tmp_path / "dist" / "tunnel.log", run=lambda argv, **kw: remotes.append(argv[-1]) or CompletedProcess(argv, 0, "", ""), popen=lambda argv, **kw: popened.append((argv, kw)) or tunnel, answers=lambda h, p: next(answers), sleep=lambda s: None, clock=counter())

        opened = b.open_tunnel(["-L", "a"], 54321, [18081])

        assert opened is tunnel
        assert remotes == [b.end_forwards_command([18081])]
        assert popened[0][0] == board.tunnel_command(TARGET, ["-L", "a"])
        assert (tmp_path / "dist").is_dir()

    def test_closes_the_tunnel_and_raises_when_it_ends_early(self, tmp_path):
        closed = []
        tunnel = SimpleNamespace(poll=lambda: 255, pid=9, terminate=lambda: closed.append(True), wait=lambda t: None)
        b = board.Board(TARGET, "netmon", tmp_path / "tunnel.log", run=lambda argv, **kw: CompletedProcess(argv, 0, "", ""), popen=lambda argv, **kw: tunnel, answers=lambda h, p: False, sleep=lambda s: None, clock=counter())

        with pytest.raises(RuntimeError, match="ended with status 255 and no message"):
            b.open_tunnel([], 54321, [])

    def test_times_out_naming_the_log(self, tmp_path):
        tunnel = SimpleNamespace(poll=lambda: None, pid=9, terminate=lambda: None, wait=lambda t: None)
        b = board.Board(TARGET, "netmon", tmp_path / "tunnel.log", run=lambda argv, **kw: CompletedProcess(argv, 0, "", ""), popen=lambda argv, **kw: tunnel, answers=lambda h, p: False, sleep=lambda s: None, clock=counter(step=10))

        with pytest.raises(TimeoutError, match=f"did not come up within 15 s; see {tmp_path / 'tunnel.log'}"):
            b.open_tunnel([], 54321, [])


class TestTunnelProblem:
    def test_is_none_while_the_tunnel_runs(self, tmp_path):
        assert board.Board(TARGET, "netmon", tmp_path / "t").tunnel_problem(SimpleNamespace(poll=lambda: None)) is None

    def test_is_the_last_line_of_the_log_that_is_not_channel_noise(self, tmp_path):
        log = tmp_path / "tunnel.log"
        log.write_text("Connection to netmon.local closed by remote host.\nchannel 2: open failed: connect failed: Connection refused\n")

        problem = board.Board(TARGET, "netmon", log).tunnel_problem(SimpleNamespace(poll=lambda: 255))

        assert problem == "the ssh tunnel to pi@netmon.local ended: Connection to netmon.local closed by remote host."


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_board.py -q`
Expected: FAIL with `ImportError: cannot import name 'board'`

- [ ] **Step 3: Write board.py**

```python
# testkit/src/pihero_testkit/preview/board.py
"""One preview session on a real board: its kiosk's session files under /run, the ssh tunnel to the Mac, and their removal."""

import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from .. import ssh
from . import kiosk, process

LOG_NAME = "tunnel.log"
DROPIN_DIR = f"/run/systemd/system/{kiosk.UNIT}.service.d"
REMOTE_OFFSET = 10000
CHANNEL_NOISE = re.compile(r"channel \d+: open failed")


def remote_port(mac_port: int) -> int:
    """Return the board's port for the Mac's `mac_port`, ten thousand above it; raise ValueError above 55535."""
    if mac_port > 65535 - REMOTE_OFFSET:
        raise ValueError(f"a Mac port of {mac_port} cannot be forwarded to the board; use one up to {65535 - REMOTE_OFFSET}")
    return mac_port + REMOTE_OFFSET


def forwards(mac_ports: list[int], inspector_local: int) -> list[str]:
    """Return the ssh forwards of a session: a reverse one per Mac port, and the inspector from the Mac's `inspector_local`."""
    args = []
    for port in mac_ports:
        args += ["-R", f"127.0.0.1:{remote_port(port)}:127.0.0.1:{port}"]
    return args + ["-L", f"127.0.0.1:{inspector_local}:127.0.0.1:{kiosk.INSPECTOR_PORT}"]


def tunnel_command(target: str, forward_args: list[str]) -> list[str]:
    """Return the `ssh -N` command carrying `forward_args` to `target` (user@host[:port]) over IPv4, ending when a forward fails."""
    user_host, _, port = target.partition(":")
    return ["ssh", "-N", "-4", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=10", *ssh.KEEPALIVE, *(["-p", port] if port else []), *forward_args, user_host]


class Board:
    def __init__(self, target: str, name: str, tunnel_log: Path, *, run=subprocess.run, popen=subprocess.Popen, answers=process.answers, sleep=time.sleep, clock=time.monotonic, report: Callable[[str], None] = lambda message: print(message, file=sys.stderr)):
        self.target, self.tunnel_log = target, tunnel_log
        self.run_dir = f"/run/{name}-preview"
        self.conf = f"{self.run_dir}/kiosk.conf"
        self.dropin = f"{DROPIN_DIR}/{name}-preview.conf"
        self._run, self._popen, self._answers, self._sleep, self._clock, self._report = run, popen, answers, sleep, clock, report

    def ssh(self, remote: str, input: str | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
        """Run `remote` on the board; raise TimeoutError when it does not answer within `timeout` seconds."""
        try:
            return self._run(ssh.command(self.target, remote), input=input, text=True, capture_output=True, check=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"{self.target} did not answer within {timeout:g} s") from None

    def check_kiosk(self) -> None:
        """Raise RuntimeError when the board cannot be reached or has no pihero-kiosk."""
        result = self.ssh(f"dpkg-query -W {kiosk.PACKAGE}")
        if result.returncode == 255:
            raise RuntimeError(f"cannot reach {self.target} over ssh: {result.stderr.strip()}")
        if result.returncode != 0:
            raise RuntimeError(f"{self.target} has no {kiosk.PACKAGE}; flash a Pi Hero device file first")

    def session_conf(self, url: str) -> str:
        """Return the board's kiosk.conf rewritten for the session, changing nothing on the board."""
        current = self.ssh(f"cat {kiosk.CONF}")
        if current.returncode != 0:
            raise RuntimeError(f"cannot read {kiosk.CONF} on {self.target}: {current.stderr.strip()}")
        return kiosk.session_conf(current.stdout, url)

    def install_command(self) -> str:
        """Return the command that writes stdin as the session's conf, adds the drop-in and restarts the kiosk."""
        return (
            f"sudo install -d {self.run_dir} {DROPIN_DIR} && sudo tee {self.conf} >/dev/null && "
            f"printf '[Service]\\nEnvironmentFile={self.conf}\\n' | sudo tee {self.dropin} >/dev/null && "
            f"sudo systemctl daemon-reload && sudo systemctl restart {kiosk.UNIT}"
        )

    def restore_command(self) -> str:
        """Return the command that removes the session's files and restarts the kiosk."""
        return (
            f"sudo rm -rf {self.run_dir} {self.dropin}; sudo rmdir --ignore-fail-on-non-empty {DROPIN_DIR} 2>/dev/null; "
            f"sudo systemctl daemon-reload && sudo systemctl restart {kiosk.UNIT}"
        )

    def end_forwards_command(self, remote_ports: list[int]) -> str:
        """Return the command ending the board's sshd processes that still listen on `remote_ports` for a dead tunnel."""
        ports = "|".join(str(port) for port in remote_ports)
        return f"sudo ss -ltnpH | grep -E '127\\.0\\.0\\.1:({ports}) ' | grep sshd | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u | xargs -r sudo kill"

    def install(self, conf: str, tunnel: subprocess.Popen, timeout: float = 90) -> None:
        """Put the session on the board and wait for the kiosk to load its page, failing early with the tunnel's message if the tunnel ends."""
        since = self.ssh(kiosk.since_command()).stdout.strip()
        result = self.ssh(self.install_command(), input=conf)
        if result.returncode != 0:
            raise RuntimeError(f"could not put the session on {self.target}: {result.stderr.strip()}")
        self.wait_loaded(since, tunnel, timeout)

    def wait_loaded(self, since: str, tunnel: subprocess.Popen, timeout: float) -> None:
        """Return once the kiosk's journal shows a page load after `since`; raise when the tunnel ends or `timeout` passes."""
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            if tunnel.poll() is not None:
                raise RuntimeError(self.tunnel_ended(tunnel))
            if kiosk.loaded(self.ssh(kiosk.loaded_command(since)).stdout):
                return
            self._sleep(1)
        raise TimeoutError(f"the kiosk on {self.target} did not load its page within {timeout:g} s; is the dev server up and the tunnel open?")

    def restore(self) -> bool:
        """Remove the session's files and restart the kiosk; return whether the board answered, else warn."""
        try:
            result = self.ssh(self.restore_command(), timeout=30)
        except (OSError, TimeoutError) as error:
            self._report(f"could not restore the kiosk on {self.target}: {error}; a reboot of the board removes the session's files")
            return False
        if result.returncode != 0:
            self._report(f"could not restore the kiosk on {self.target}: {result.stderr.strip()}; a reboot of the board removes the session's files")
        return result.returncode == 0

    def open_tunnel(self, forward_args: list[str], inspector_local: int, remote_ports: list[int]) -> subprocess.Popen:
        """Open the tunnel after ending the board's side of a dead one; raise RuntimeError when it ends early, TimeoutError after 15 s."""
        if remote_ports:
            self.ssh(self.end_forwards_command(remote_ports), timeout=30)
        self.tunnel_log.parent.mkdir(parents=True, exist_ok=True)
        with self.tunnel_log.open("w") as log:
            tunnel = self._popen(tunnel_command(self.target, forward_args), stdout=subprocess.DEVNULL, stderr=log, text=True)
        try:
            deadline = self._clock() + 15
            while self._clock() < deadline:
                if tunnel.poll() is not None:
                    raise RuntimeError(self.tunnel_ended(tunnel))
                if self._answers("127.0.0.1", inspector_local):
                    return tunnel
                self._sleep(0.25)
            raise TimeoutError(f"the ssh tunnel to {self.target} did not come up within 15 s; see {self.tunnel_log}")
        except BaseException:
            self.close_tunnel(tunnel)
            raise

    def tunnel_problem(self, tunnel: subprocess.Popen) -> str | None:
        """Return why the tunnel ended, or None while it runs."""
        return self.tunnel_ended(tunnel) if tunnel.poll() is not None else None

    def tunnel_ended(self, tunnel: subprocess.Popen) -> str:
        """Return the tunnel log's last message that is not channel noise, or the exit status and the log's path."""
        lines = self.tunnel_log.read_text(errors="replace").strip().splitlines() if self.tunnel_log.exists() else []
        reasons = [line for line in lines if not CHANNEL_NOISE.match(line)]
        if reasons:
            return f"the ssh tunnel to {self.target} ended: {reasons[-1]}"
        return f"the ssh tunnel to {self.target} ended with status {tunnel.poll()} and no message; see {self.tunnel_log}"

    def close_tunnel(self, tunnel: subprocess.Popen) -> None:
        """End the tunnel, killing it after five seconds."""
        if tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(5)
            except subprocess.TimeoutExpired:
                tunnel.kill()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_board.py -q`
Expected: 27 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/board.py testkit/tests/test_preview_board.py
git commit -m "feat(testkit): run a preview session on a real board"
```

---

### Task 12: `flavors`: `Shown`, the `Served` rules, `Browser`, `Vm`, `Device`

**Files:**
- Create: `testkit/src/pihero_testkit/preview/flavors.py`
- Test: `testkit/tests/test_preview_flavors.py`

**Interfaces:**
- Consumes: `api.*`, `board.Board`, `board.forwards`, `board.remote_port`, `layer.ensure`, `vm.Session`, `process.free_port`, `process.entry`, `record.Record`.
- Produces: `Shown(page, inspector=None, watch=None)`, `BrowserServed`, `VmServed`, `BoardServed`, `served_for(flavor) -> Served`, `mac_ports(dev, backend) -> list[int]`, `Browser`, `Vm`, `Device`, each with `show(app, settings, backend, dev, cleanup, rec) -> Shown`, `flavor_for(flavor)`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_flavors.py
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest

from pihero_testkit.preview import flavors, layer, record
from pihero_testkit.preview.api import DevServer, Settings

pytestmark = pytest.mark.tier0
DEV = DevServer(["serve"], 8081)


class TestServed:
    def test_the_browser_reaches_the_mac_on_localhost(self):
        assert flavors.served_for("browser").address(8081) == "localhost:8081"

    def test_the_vm_reaches_the_mac_at_qemus_host_address(self):
        assert flavors.served_for("vm").address(8081) == "10.0.2.2:8081"

    def test_the_board_reaches_the_mac_through_the_reverse_port(self):
        assert flavors.served_for("device").address(8081) == "127.0.0.1:18081"

    def test_each_names_its_flavor(self):
        assert [flavors.served_for(f).flavor for f in ("browser", "vm", "device")] == ["browser", "vm", "device"]


class TestMacPorts:
    def test_are_the_dev_servers_and_a_backend_on_the_mac(self):
        assert flavors.mac_ports(DEV, backend(mac_port=8080)) == [8081, 8080]

    def test_leave_out_a_backend_elsewhere(self):
        assert flavors.mac_ports(DEV, backend(mac_port=None)) == [8081]


class TestBrowser:
    def test_shows_the_apps_page_url_with_nothing_to_inspect(self, tmp_path):
        shown = flavors.Browser().show(app(), Settings("browser", None, "Safari", {}), backend(), DEV, ExitStack(), record.Record(tmp_path))

        assert shown == flavors.Shown("http://localhost:8081/?x=1")
        assert shown.inspector is None and shown.watch is None


class TestVm:
    def test_builds_the_layer_boots_places_configures_and_tunnels(self, tmp_path):
        session = FakeSession()
        rec = record.Record(tmp_path)
        rec.update()
        made = {}

        def make_session(found_layer, directory, display):
            made.update(layer=found_layer, directory=directory, display=display)
            return session

        with ExitStack() as cleanup:
            shown = flavors.Vm(ensure_layer=lambda a: LAYER, make_session=make_session, free_port=lambda: 54321, entry=lambda pid: [pid, "T"]).show(app(), Settings("vm", None, "Safari", {}), backend(), DEV, cleanup, rec)

            assert made == {"layer": LAYER, "directory": tmp_path / "session", "display": (800, 480)}
            assert session.calls == ["start", "place_window", "configure_kiosk http://10.0.2.2:8081/?x=1", "open_tunnel 54321"]
            assert shown == flavors.Shown("http://localhost:8081/", "127.0.0.1:54321")
            assert rec.read() == {"qemu": [4242, "T"], "inspector": 54321}
        assert session.calls[-1] == "stop"

    def test_stops_the_session_when_the_kiosk_fails_to_load(self, tmp_path):
        session = FakeSession(fail_kiosk=True)

        with pytest.raises(TimeoutError), ExitStack() as cleanup:
            flavors.Vm(ensure_layer=lambda a: LAYER, make_session=lambda *a: session, free_port=lambda: 1, entry=lambda pid: None).show(app(), Settings("vm", None, None, {}), backend(), DEV, cleanup, record.Record(tmp_path))

        assert session.calls[-1] == "stop"


class TestDevice:
    def test_checks_tunnels_installs_and_restores_at_the_end(self, tmp_path):
        b = FakeBoard()
        rec = record.Record(tmp_path)
        rec.update()
        made = {}

        def make_board(target, name, log):
            made.update(target=target, name=name, log=log)
            return b

        with ExitStack() as cleanup:
            shown = flavors.Device(make_board=make_board, free_port=lambda: 54321, entry=lambda pid: [pid, "T"]).show(app(), Settings("device", "pi@host", None, {}), backend(mac_port=8080), DEV, cleanup, rec)

            assert made == {"target": "pi@host", "name": "probe", "log": tmp_path / "tunnel.log"}
            assert b.calls[:3] == ["check_kiosk", "session_conf http://127.0.0.1:18081/?x=1", "open_tunnel ['-R', '127.0.0.1:18081:127.0.0.1:8081', '-R', '127.0.0.1:18080:127.0.0.1:8080', '-L', '127.0.0.1:54321:127.0.0.1:2999'] 54321 [18081, 18080]"]
            assert b.calls[3] == "install CONF"
            assert rec.read() == {"tunnel": [9, "T"], "device": "pi@host", "inspector": 54321}
            assert shown.page == "http://localhost:8081/" and shown.inspector == "127.0.0.1:54321"
            assert shown.watch() == "problem"
        assert b.calls[4:] == ["restore", "close_tunnel"]
        assert rec.read() == {"device": None}

    def test_keeps_the_board_in_the_record_when_restore_fails(self, tmp_path):
        b = FakeBoard(restores=False)
        rec = record.Record(tmp_path)
        rec.update()

        with ExitStack() as cleanup:
            flavors.Device(make_board=lambda *a: b, free_port=lambda: 1, entry=lambda pid: [pid, "T"]).show(app(), Settings("device", "pi@host", None, {}), backend(), DEV, cleanup, rec)

        assert rec.read()["device"] == "pi@host"


class TestFlavorFor:
    @pytest.mark.parametrize("name, cls", [("browser", flavors.Browser), ("vm", flavors.Vm), ("device", flavors.Device)])
    def test_names_the_flavor(self, name, cls):
        assert isinstance(flavors.flavor_for(name), cls)


LAYER = layer.Layer(Path("/l/rootfs.qcow2"), Path("/l/bootfs.img"))


def app():
    return SimpleNamespace(name="probe", root=Path("/repo"), display=(800, 480), page_url=lambda backend, served: f"http://{served.address(8081)}/?x=1")


def backend(mac_port=None):
    return SimpleNamespace(managed=False, mac_port=mac_port, start=lambda: None, stop=lambda: None, describe=lambda: "none")


class FakeSession:
    def __init__(self, fail_kiosk: bool = False):
        self.calls, self.fail_kiosk = [], fail_kiosk
        self.vm = SimpleNamespace(process=SimpleNamespace(pid=4242))

    def start(self, on_qemu=None):
        self.calls.append("start")
        if on_qemu:
            on_qemu(4242)

    def place_window(self):
        self.calls.append("place_window")
        return True

    def configure_kiosk(self, url):
        self.calls.append(f"configure_kiosk {url}")
        if self.fail_kiosk:
            raise TimeoutError("did not load")

    def open_tunnel(self, local_port):
        self.calls.append(f"open_tunnel {local_port}")

    def stop(self):
        self.calls.append("stop")


class FakeBoard:
    def __init__(self, restores: bool = True):
        self.calls, self.restores = [], restores

    def check_kiosk(self):
        self.calls.append("check_kiosk")

    def session_conf(self, url):
        self.calls.append(f"session_conf {url}")
        return "CONF"

    def open_tunnel(self, forward_args, inspector_local, remote_ports):
        self.calls.append(f"open_tunnel {forward_args} {inspector_local} {remote_ports}")
        return SimpleNamespace(pid=9, poll=lambda: None)

    def install(self, conf, tunnel):
        self.calls.append(f"install {conf}")

    def restore(self):
        self.calls.append("restore")
        return self.restores

    def tunnel_problem(self, tunnel):
        return "problem"

    def close_tunnel(self, tunnel):
        self.calls.append("close_tunnel")
```

`record.Record.update()` with no fields creates the file; the tests above use it so `read()` returns a dict without an `owner`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_flavors.py -q`
Expected: FAIL with `ImportError: cannot import name 'flavors'`

- [ ] **Step 3: Write flavors.py**

```python
# testkit/src/pihero_testkit/preview/flavors.py
"""The places a preview shows the page: a browser tab, the kiosk in a VM window, and the kiosk of a real board."""

from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

from . import board, layer, process, vm
from .api import Backend, DevServer, KioskApp, Served, Settings
from .record import Record


@dataclass(frozen=True)
class Shown:
    """What a flavor put up: the page as the Mac's browser loads it, the kiosk's inspector address (None where the page's own tools inspect it), and a check asked while the session runs."""

    page: str
    inspector: str | None = None
    watch: Callable[[], str | None] | None = field(default=None, compare=False)


class BrowserServed:
    flavor = "browser"

    def address(self, mac_port: int) -> str:
        return f"localhost:{mac_port}"


class VmServed:
    flavor = "vm"

    def address(self, mac_port: int) -> str:
        return f"10.0.2.2:{mac_port}"


class BoardServed:
    flavor = "device"

    def address(self, mac_port: int) -> str:
        return f"127.0.0.1:{board.remote_port(mac_port)}"


def served_for(flavor: str) -> Served:
    """Return how the kiosk of `flavor` reaches the Mac."""
    return {"browser": BrowserServed, "vm": VmServed, "device": BoardServed}[flavor]()


def mac_ports(dev: DevServer, backend: Backend) -> list[int]:
    """Return the Mac ports the kiosk must reach: the dev server's, and the backend's when it runs on the Mac."""
    return [dev.port] + ([backend.mac_port] if backend.mac_port is not None else [])


class Browser:
    def show(self, app: KioskApp, settings: Settings, backend: Backend, dev: DevServer, cleanup: ExitStack, rec: Record) -> Shown:
        return Shown(app.page_url(backend, BrowserServed()))


class Vm:
    def __init__(self, ensure_layer=layer.ensure, make_session=vm.Session, free_port=process.free_port, entry=process.entry):
        self._ensure_layer, self._make_session, self._free_port, self._entry = ensure_layer, make_session, free_port, entry

    def show(self, app: KioskApp, settings: Settings, backend: Backend, dev: DevServer, cleanup: ExitStack, rec: Record) -> Shown:
        session = self._make_session(self._ensure_layer(app), rec.session_dir, app.display)
        cleanup.callback(session.stop)
        session.start(on_qemu=lambda pid: rec.update(qemu=self._entry(pid)))
        session.place_window()
        session.configure_kiosk(app.page_url(backend, VmServed()))
        local = self._free_port()
        session.open_tunnel(local)
        rec.update(inspector=local)
        return Shown(f"http://localhost:{dev.port}/", f"127.0.0.1:{local}")


class Device:
    def __init__(self, make_board=board.Board, free_port=process.free_port, entry=process.entry):
        self._make_board, self._free_port, self._entry = make_board, free_port, entry

    def show(self, app: KioskApp, settings: Settings, backend: Backend, dev: DevServer, cleanup: ExitStack, rec: Record) -> Shown:
        target = self._make_board(settings.target, app.name, rec.directory / board.LOG_NAME)
        target.check_kiosk()
        conf = target.session_conf(app.page_url(backend, BoardServed()))
        ports = mac_ports(dev, backend)
        local = self._free_port()
        tunnel = target.open_tunnel(board.forwards(ports, local), local, [board.remote_port(port) for port in ports])
        cleanup.callback(target.close_tunnel, tunnel)
        rec.update(tunnel=self._entry(tunnel.pid), device=settings.target, inspector=local)

        def restore() -> None:
            if target.restore():
                rec.update(device=None)

        cleanup.callback(restore)
        target.install(conf, tunnel)
        return Shown(f"http://localhost:{dev.port}/", f"127.0.0.1:{local}", lambda: target.tunnel_problem(tunnel))


def flavor_for(flavor: str):
    """Return the flavor object for `flavor`."""
    return {"browser": Browser, "vm": Vm, "device": Device}[flavor]()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_flavors.py -q`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/flavors.py testkit/tests/test_preview_flavors.py
git commit -m "feat(testkit): show a preview in a browser, a VM or on a board"
```

---

### Task 13: `session`: `run`, `main`, the ready message

**Files:**
- Create: `testkit/src/pihero_testkit/preview/session.py`
- Modify: `testkit/src/pihero_testkit/preview/__init__.py`
- Test: `testkit/tests/test_preview_session.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `state_dir(app) -> Path`, `ready_message(settings, shown, backend) -> str`, `run(app, settings, *, injectables) -> int`, `main(app, argv=None, environ=None) -> int`; `pihero_testkit.preview.main`.

- [ ] **Step 1: Write the failing tests**

```python
# testkit/tests/test_preview_session.py
import json
from contextlib import ExitStack
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from pihero_testkit.preview import flavors, session
from pihero_testkit.preview.api import DevServer, Settings

pytestmark = pytest.mark.tier0


class TestRun:
    def test_starts_the_backend_and_the_dev_server_shows_the_flavor_and_cleans_up_in_reverse(self, tmp_path):
        log = []
        app = App(tmp_path, log, managed=True)
        harness = Harness(log)

        status = session.run(app, Settings("vm", None, "Safari", {}), **harness.injected)

        assert status == 0
        assert log == [
            "backend", "dev_server", "backend.start", "ensure 8081", "show vm",
            "wait_for_inspector 127.0.0.1:54321", "open Safari http://127.0.0.1:54321/Main.html", "until_interrupted",
            "stop dev server", "backend.stop",
        ]
        assert not (tmp_path / "dist" / "preview" / "session.json").exists()

    def test_leaves_an_unmanaged_backend_alone(self, tmp_path):
        log = []

        session.run(App(tmp_path, log, managed=False), Settings("browser", None, None, {}), **Harness(log).injected)

        assert "backend.start" not in log and "backend.stop" not in log

    def test_records_the_backend_and_the_dev_server_while_running(self, tmp_path):
        log = []
        app = App(tmp_path, log, managed=True)
        seen = {}
        harness = Harness(log, on_wait=lambda: seen.update(json.loads((tmp_path / "dist" / "preview" / "session.json").read_text())))

        session.run(app, Settings("vm", None, None, {}), **harness.injected)

        assert seen["backend"] is True
        assert seen["dev_server"] == [77, "T"]
        assert "owner" in seen

    def test_opens_the_page_itself_in_the_browser_flavor(self, tmp_path):
        log = []

        session.run(App(tmp_path, log), Settings("browser", None, "Safari", {}), **Harness(log, flavor="browser").injected)

        assert "open Safari http://localhost:8081/?x=1" in log

    def test_goes_on_when_the_application_to_open_is_missing(self, tmp_path, capsys):
        log = []
        harness = Harness(log)
        harness.open_status = 1

        status = session.run(App(tmp_path, log), Settings("vm", None, "Nope", {}), **harness.injected)

        assert status == 0 and "until_interrupted" in log

    def test_prints_the_ready_message(self, tmp_path, capsys):
        log = []

        session.run(App(tmp_path, log, managed=True), Settings("vm", None, None, {}), **Harness(log).injected)

        err = capsys.readouterr().err
        assert "preview ready (vm)\n  page       http://localhost:8081/\n  backend    fake on localhost:8080\n  inspector  http://127.0.0.1:54321/\nCtrl-C ends it." in err

    def test_fails_before_claiming_when_the_apps_variables_are_bad(self, tmp_path):
        log = []
        app = App(tmp_path, log)
        app.bad_backend = True

        with pytest.raises(ValueError, match="BROKER must be"):
            session.run(app, Settings("vm", None, None, {}), **Harness(log).injected)

        assert not (tmp_path / "dist" / "preview").exists()

    def test_stops_the_dev_server_and_backend_when_the_flavor_fails(self, tmp_path):
        log = []
        harness = Harness(log)
        harness.show_error = RuntimeError("no kiosk")

        with pytest.raises(RuntimeError, match="no kiosk"):
            session.run(App(tmp_path, log, managed=True), Settings("vm", None, None, {}), **harness.injected)

        assert log[-2:] == ["stop dev server", "backend.stop"]


class TestMain:
    def test_returns_2_with_the_message_for_a_variable_that_does_not_fit(self, tmp_path, capsys):
        status = session.main(App(tmp_path, []), ["--on", "device"], {})

        assert status == 2
        assert "preview-device needs TARGET=user@host" in capsys.readouterr().err

    def test_refuses_an_unknown_flavor(self, tmp_path):
        with pytest.raises(SystemExit) as exit_:
            session.main(App(tmp_path, []), ["--on", "tv"], {})

        assert exit_.value.code == 2

    def test_returns_2_with_the_apps_own_message(self, tmp_path, capsys):
        app = App(tmp_path, [])
        app.bad_backend = True

        status = session.main(app, ["--on", "vm"], {})

        assert status == 2
        assert "BROKER must be" in capsys.readouterr().err

    def test_is_exported_by_the_package(self):
        from pihero_testkit import preview

        assert preview.main is session.main


class TestStateDir:
    def test_is_dist_preview_under_the_apps_root(self):
        assert session.state_dir(SimpleNamespace(root=Path("/repo"))) == Path("/repo/dist/preview")


class App:
    name = "probe"
    display = (800, 480)

    def __init__(self, root: Path, log: list, managed: bool = False):
        self.root, self.log, self.managed, self.bad_backend = root, log, managed, False

    def user_data(self):
        return "#cloud-config\npackages:\n  - pihero-kiosk\n"

    def dev_server(self, settings):
        self.log.append("dev_server")
        return DevServer(["serve"], 8081)

    def backend(self, settings):
        self.log.append("backend")
        if self.bad_backend:
            raise ValueError("BROKER must be fake, device or HOST:PORT")
        log = self.log
        return SimpleNamespace(managed=self.managed, mac_port=8080, start=lambda: log.append("backend.start"), stop=lambda: log.append("backend.stop"), describe=lambda: "fake on localhost:8080")

    def page_url(self, backend, served):
        return f"http://{served.address(8081)}/?x=1"


class Harness:
    def __init__(self, log: list, flavor: str = "vm", on_wait=lambda: None):
        self.log, self.flavor_name, self.on_wait = log, flavor, on_wait
        self.open_status, self.show_error = 0, None

    @property
    def injected(self) -> dict:
        return dict(
            ensure_dev_server=self.ensure, stop_dev_server=lambda proc: self.log.append("stop dev server"), flavor_for=lambda name: self,
            wait_for_inspector=self.wait_for_inspector, open_=self.open_, until_interrupted=self.until_interrupted, arm_sigterm=lambda: None,
            entry=lambda pid: [pid, "T"],
        )

    def ensure(self, dev, root, log):
        self.log.append(f"ensure {dev.port}")
        return SimpleNamespace(pid=77)

    def show(self, app, settings, backend, dev, cleanup, rec):
        self.log.append(f"show {settings.flavor}")
        if self.show_error:
            raise self.show_error
        if self.flavor_name == "browser":
            return flavors.Shown(app.page_url(backend, flavors.BrowserServed()))
        return flavors.Shown("http://localhost:8081/", "127.0.0.1:54321")

    def wait_for_inspector(self, address):
        self.log.append(f"wait_for_inspector {address}")
        return f"http://{address}/Main.html"

    def open_(self, argv, check):
        self.log.append(f"open {argv[2]} {argv[3]}")
        return CompletedProcess(argv, self.open_status, "", "")

    def until_interrupted(self, watch):
        self.on_wait()
        self.log.append("until_interrupted")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_preview_session.py -q`
Expected: FAIL with `ImportError: cannot import name 'session'`

- [ ] **Step 3: Write session.py and export main**

```python
# testkit/src/pihero_testkit/preview/session.py
"""One preview session from claim to cleanup: the backend, the dev server, the flavor, the inspector, and Ctrl-C."""

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path

from . import board, dev_server, flavors, kiosk, process
from .api import FLAVORS, Backend, KioskApp, Settings
from .record import AlreadyRunning, Record


def state_dir(app: KioskApp) -> Path:
    """Return where the app's preview keeps its record, logs and session: root/dist/preview."""
    return app.root / "dist" / "preview"


def ready_message(settings: Settings, shown: flavors.Shown, backend: Backend) -> str:
    """Return the lines printed once the preview is up."""
    inspector = f"\n  inspector  http://{shown.inspector}/" if shown.inspector else ""
    return f"preview ready ({settings.flavor})\n  page       {shown.page}\n  backend    {backend.describe()}{inspector}\nCtrl-C ends it."


def run(app: KioskApp, settings: Settings, *, ensure_dev_server=dev_server.ensure, stop_dev_server=dev_server.stop, flavor_for=flavors.flavor_for, wait_for_inspector=kiosk.wait_for_inspector, open_=subprocess.run, until_interrupted=process.until_interrupted, arm_sigterm=process.raise_on_sigterm, entry=process.entry, out=sys.stderr) -> int:
    """Run the preview until Ctrl-C and return 0; everything started is ended on the way out."""
    backend = app.backend(settings)
    dev = app.dev_server(settings)
    arm_sigterm()
    state = state_dir(app)
    rec = Record(state)
    rec.claim(backend.stop, lambda target: board.Board(target, app.name, state / board.LOG_NAME).restore())
    with ExitStack() as cleanup:
        cleanup.callback(rec.forget)
        if backend.managed:
            backend.start()
            cleanup.callback(backend.stop)
            rec.update(backend=True)
        log = state / dev_server.LOG_NAME
        print(f"dev server: {shlex.join(dev.argv)} on port {dev.port}, log in {log}", file=out, flush=True)
        server = ensure_dev_server(dev, app.root, log)
        cleanup.callback(stop_dev_server, server)
        rec.update(dev_server=entry(server.pid))
        shown = flavor_for(settings.flavor).show(app, settings, backend, dev, cleanup, rec)
        opened = wait_for_inspector(shown.inspector) if shown.inspector else shown.page
        if settings.inspect:
            open_(kiosk.open_command(settings.inspect, opened), check=False)
        print(ready_message(settings, shown, backend), file=out, flush=True)
        until_interrupted(shown.watch)
    return 0


def main(app: KioskApp, argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """Run the app's preview for `--on browser|vm|device`; return 2 with the message on a bad variable or a failure, 130 on Ctrl-C."""
    parser = argparse.ArgumentParser(prog="preview.py", description=f"Show {app.name}'s page from the dev server in a browser, a VM's kiosk or a board's kiosk until Ctrl-C.")
    parser.add_argument("--on", required=True, choices=FLAVORS, help="where to show the page")
    flavor = parser.parse_args(argv).on
    try:
        return run(app, Settings.from_environ(flavor, os.environ if environ is None else environ))
    except (ValueError, AlreadyRunning, RuntimeError, TimeoutError) as error:
        print(error, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
```

Replace `preview/__init__.py` with:

```python
"""A kiosk app's page from the Mac's dev server in a browser, a VM's kiosk or a board's kiosk; see docs/app-conventions.md."""

from .api import Backend, DevServer, KioskApp, Served, Settings
from .session import main

__all__ = ["Backend", "DevServer", "KioskApp", "Served", "Settings", "main"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_preview_session.py testkit/tests/test_preview_api.py -q`
Expected: 25 passed

- [ ] **Step 5: Commit**

```bash
git add testkit/src/pihero_testkit/preview/session.py testkit/src/pihero_testkit/preview/__init__.py testkit/tests/test_preview_session.py
git commit -m "feat(testkit): run a kiosk app's preview from claim to cleanup"
```

---

### Task 14: The `preview` marker, the version, `make test-preview`, and the live session test

**Files:**
- Modify: `testkit/src/pihero_testkit/plugin.py:411-419`, `testkit/pyproject.toml:3`, `Makefile`
- Test: `testkit/tests/test_plugin.py`, `testkit/tests/test_preview_live.py`

**Interfaces:**
- Consumes: `device_file`, `layer.ensure`, `vm.Session`, `kiosk.inspector_url`, `process.free_port`.

- [ ] **Step 1: Write the failing marker test**

Append to `testkit/tests/test_plugin.py`:

```python
class TestPreviewMarker:
    def test_is_registered_as_opt_in(self, pytester):
        pytester.makepyfile("import pytest\n\npytestmark = pytest.mark.preview\n\n\ndef test_passes():\n    assert True\n")

        result = pytester.runpytest_inprocess("-p", "pihero_testkit.plugin", "-p", "no:pytest11.testinfra", "--strict-markers", "-m", "preview")

        result.assert_outcomes(passed=1)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --frozen pytest testkit/tests/test_plugin.py -q -k PreviewMarker`
Expected: FAIL: `'preview' not found in 'markers' configuration option`

- [ ] **Step 3: Register the marker, bump the version, add the target**

`plugin.py`'s `pytest_configure` becomes:

```python
def pytest_configure(config):
    config.addinivalue_line("markers", "tier0: runs on the Mac against fixtures and the tools container, no target")
    config.addinivalue_line("markers", "installed: runs against any target with the packages installed (podman, vm, ssh)")
    config.addinivalue_line("markers", "boot: cross-cutting checks that need a booted VM or device (vm, ssh)")
    config.addinivalue_line("markers", "mutating: changes the target's state; skipped on --target=ssh")
    config.addinivalue_line("markers", "preview: runs a kiosk preview session on this Mac (QEMU, a window server), opt-in (make test-preview)")
    if config.getoption("--target") == "vm":
        from .vm import parse_display

        parse_display(config.getoption("--display"))
```

In `testkit/pyproject.toml`: `version = "2.8.0"`.

In the `Makefile`, after `test-tier2`:

```make
test-preview: ## the kiosk preview's VM session on this Mac (QEMU, a window server, Accessibility for the terminal)
	@$(UV) pytest -m preview
```

- [ ] **Step 4: Run the marker test**

Run: `uv run --frozen pytest testkit/tests/test_plugin.py -q -k PreviewMarker`
Expected: 1 passed

- [ ] **Step 5: Write the live session test**

```python
# testkit/tests/test_preview_live.py
import http.server
import socket
import struct
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from pihero_testkit import device_file
from pihero_testkit.preview import flavors, kiosk, layer, process, record, vm, window

pytestmark = [pytest.mark.preview, pytest.mark.skipif(sys.platform != "darwin", reason="the window is a macOS window")]
REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "devices" / "sample" / "user-data"


class TestVmSession:
    def test_keeps_the_guest_at_the_apps_display_whatever_the_window_does(self, session):
        resized = window.place(session.vm.process.pid, (1000, 668))
        session.restart_kiosk()

        assert (resized, picture_size(session)) == (True, (800, 480))

    def test_tunnels_the_inspector_of_a_page_served_from_the_macs_loopback(self, session):
        port = process.free_port()
        session.open_tunnel(port)

        listing = wait_for_listing(port)

        assert kiosk.inspector_url(listing, f"127.0.0.1:{port}") is not None

    def test_the_kiosk_loaded_the_page_from_the_mac(self, session):
        count = session.vm.ssh("sudo journalctl -u pihero-kiosk -b --no-pager | grep -c 'Loaded successfully'").stdout

        assert kiosk.loaded(count)


class TestRecovery:
    def test_the_next_start_ends_the_qemu_a_killed_record_names(self, session, tmp_path):
        rec = record.Record(tmp_path)
        rec.update(owner=[999999, "gone"], qemu=process.entry(session.vm.process.pid))

        rec.claim(stop_backend=lambda: None, restore_board=lambda t: None)

        assert session.vm.process.poll() is not None


class StaticApp:
    name = "pihero-preview-probe"
    display = (800, 480)

    def __init__(self, root: Path, port: int):
        self.root, self.port = root, port

    def user_data(self) -> str:
        text = device_file.with_user(SAMPLE.read_text(), device_file.PUBLIC_KEY.read_text().strip())
        return text.replace("  - pihero\n", f"  - pihero\n  - {kiosk.PACKAGE}\n", 1)

    def dev_server(self, settings):
        raise NotImplementedError

    def backend(self, settings):
        raise NotImplementedError

    def page_url(self, backend, served) -> str:
        return f"http://{served.address(self.port)}/"


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    directory = tmp_path_factory.mktemp("page")
    (directory / "index.html").write_text("<h1>preview</h1>")
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=str(directory), **kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


@pytest.fixture(scope="module")
def session(tmp_path_factory, page):
    app = StaticApp(tmp_path_factory.mktemp("root"), page)
    started = vm.Session(layer.ensure(app), app.root / "dist" / "preview" / "session", app.display)
    started.start()
    started.place_window()
    started.configure_kiosk(app.page_url(None, flavors.VmServed()))
    yield started
    started.stop()


def picture_size(session) -> tuple[int, int]:
    png = session.directory / "picture.png"
    session.vm.screenshot(png)
    return struct.unpack(">II", png.read_bytes()[16:24])


def wait_for_listing(port: int) -> str:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            listing = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3).read().decode()
            if "socket/" in listing:
                return listing
        except OSError:
            pass
        time.sleep(1)
    raise AssertionError("the inspector's page list named no target within 60 seconds")
```

Order matters: `TestRecovery` ends the VM, so it must run last; pytest runs classes in file order, which it is.

- [ ] **Step 6: Run the live test on the Mac**

Run: `make test-preview`
Expected: 4 passed, after about 3 minutes the first time (the layer builds: the sample device from the published repository plus `pihero-kiosk`), a QEMU window appearing and resizing. Needs Accessibility permission for the terminal.

- [ ] **Step 7: Run the whole tier 0**

Run: `make test-tier0`
Expected: all passed

- [ ] **Step 8: Commit**

```bash
git add testkit/src/pihero_testkit/plugin.py testkit/pyproject.toml Makefile testkit/tests/test_plugin.py testkit/tests/test_preview_live.py
git commit -m "feat(testkit): add make test-preview and the preview marker"
```

---

### Task 15: Documentation

**Files:**
- Modify: `README.md` (Development, "Build and test"), `docs/testing.md` (Tiers command block, "Writing tests", "Real devices"), `docs/app-conventions.md` (new section), `docs/design.md` ("`pihero-kiosk`", "Applications")

- [ ] **Step 1: README**

In the "Build and test" shell block, after the `make test-all` line:

```
make test-preview                   # the kiosk preview's VM session on this Mac (QEMU, a window server)
```

- [ ] **Step 2: testing.md**

In the "Tiers" shell block, after `make test-all`:

```
make test-preview                              # the kiosk preview's VM session, Mac only
```

At the end of "Writing tests", a new paragraph:

```
`preview` marks the tests of the kiosk preview that boot a VM in a window on this Mac (`make test-preview`); they are opt-in and
`skipif` not darwin. Their reference app serves a static page with `http.server` and installs the published `pihero-kiosk`
into the sample device, so the first run builds a layer under `~/.cache/pihero/preview` (about 2.5 minutes).
```

At the end of "Real devices", before "Neither tier is a Raspberry Pi", a new paragraph:

```
The kiosk preview's device flavor (`preview-device` in an app, [app-conventions.md](app-conventions.md) "Kiosk preview") has
no VM counterpart: it is proven by hand on an application board. The check: the page shows the app's fixture; a CSS edit
reaches the panel within seconds; the Web Inspector shows the live DOM; Ctrl-C leaves `/run/<app>-preview` and the drop-in
under `/run/systemd/system/pihero-kiosk.service.d/` gone and the kiosk on its own `URL`; `kill -9` of the session and the
next start recovers both. Last run: netmon on `netmon.local`, 2026-10-03, with netmon's own implementation.
```

- [ ] **Step 3: app-conventions.md**

Append:

```
## Kiosk preview

An app with a page previews it from the Mac with `pihero_testkit.preview`: the page from the app's dev server, shown in a
browser tab, in the kiosk of a short-lived QEMU VM (WPE WebKit in a window, exact rendering) or in the kiosk of a real
board, each with a Web Inspector, each ended by Ctrl-C with nothing left behind. The app implements `KioskApp` in
`tests/preview.py` and ends the file with `sys.exit(main(App()))`; its make targets are `preview-browser`, `preview-vm` and
`preview-device TARGET=user@host`, each `uv run --frozen python tests/preview.py --on <flavor>`.

- `name` scopes the record, the board's `/run/<name>-preview` and its drop-in. `root` is the repository; the record and
  logs live under `root/dist/preview`. `display` is the panel's size, the VM's display and the window's size in points.
- `user_data()` returns the VM's device file: the sample with the testkit's user and key (`device_file.with_user`), minus
  the app's apt source, packages and boot-config lines (the page and the backend come from the Mac), plus `pihero-kiosk`,
  which the sample gets only through the app's package. `device_file.block`, `drop` and `with_source` do the editing.
- `dev_server(settings)` returns the command and its port. The dev server binds `127.0.0.1` on a port of the app's own
  (netmon 8081, busy-screen 8082; two apps on one Mac must differ), accepts the guest's `Host:` header (`allowedHosts:
  'all'` for webpack-dev-server) and lets its live-reload client use the address the page came from (`client.webSocketURL:
  'auto://0.0.0.0:0/ws'`). `settings.flavor` and `settings.target` are there for what differs per flavor, such as a proxy
  to the board's own files.
- `backend(settings)` parses the app's own variables from `settings.environ` and raises `ValueError` naming the grammar.
  The recommended grammar is `fake | device | HOST:PORT`: the *fake* is the real backend software seeded with a fixture
  (Mosquitto with retained scans, Node-RED with a status), started and stopped by the session (`managed`); `device` is the
  board's own, `preview-device` only; `HOST:PORT` attaches to one that runs. `mac_port` is the backend's port on the Mac,
  or `None`; the session forwards it. `stop()` ends the fake wherever a session left it, from any process, so a killed
  session is cleaned up by the next.
- `page_url(backend, served)` returns the URL the kiosk or browser loads, with `served.address(port)` for every Mac port
  the page needs: `localhost:P` in a browser, `10.0.2.2:P` in the VM, `127.0.0.1:(10000+P)` on a board.
- Every flavor takes `INSPECT` (the application that opens the page or the kiosk's Web Inspector, default `Safari`, `0`
  opens nothing) and `preview-device` takes `TARGET=user@host[:port]`.
- One preview per app (Gradle allows one build per project directory) and one per board (one kiosk); two apps preview side
  by side, each in its VM or on its board.
```

- [ ] **Step 4: design.md**

At the end of the "`pihero-kiosk`" section's first paragraph (after "takes `COG_PLATFORM_DRM_VIDEO_MODE=800x480` in the same file."):

```
 The testkit's preview drives this unit from the Mac: it rewrites `kiosk.conf` for a session (the page's URL, developer
extras, the Web Inspector, `GSETTINGS_BACKEND=memory` against a dconf hang) in a VM's overlay or in a `/run` drop-in on a
board, and a tier-0 test holds the preview's constants to this package's unit and script.
```

In "Applications", after the existing paragraph:

```
An app that shows a page previews it from the Mac through `pihero_testkit.preview` (2026-10-03): the page from the app's
dev server in a browser tab, in the kiosk of a VM shown in a window, or in the kiosk of a real board, with a Web Inspector
and a clean exit. The app implements `KioskApp` ([app-conventions.md](app-conventions.md) "Kiosk preview"); the testkit
owns the session, the provisioned layer cache, the VM and its window, the board's tunnel and drop-in. The server a session
starts on the Mac is the app's *fake*: the real backend software seeded with a *fixture*. Two apps preview at once because
everything on the Mac is scoped by the app's name or allocated per session. Design:
[2026-10-03-kiosk-preview-design.md](superpowers/specs/2026-10-03-kiosk-preview-design.md).
```

- [ ] **Step 5: Check the links and commit**

Run: `uv run --frozen pytest testkit/tests/test_static.py -q` (the static checks, which include the docs if any apply)
Expected: passed

```bash
git add README.md docs/testing.md docs/app-conventions.md docs/design.md
git commit -m "docs(testkit): describe the kiosk preview for apps"
```

---

### Task 16: netmon on the library

In `/Users/bkahlert/Development/com.bkahlert/netmon`, branch `refactor/preview-on-testkit`.

**Files:**
- Modify: `pyproject.toml` (the pin), `tests/preview.py` (rewritten), `tests/preview_broker.py` (gains a `Backend`), `tests/vm_device.py` (on `device_file`), `tests/preview_device.py` (only `render` stays, moved into `tests/preview.py`), `README.md` ("Run the web display component locally": `BROKER=fake`).
- Delete: `tests/preview_session.py`, `preview_flavors.py`, `preview_kiosk.py`, `preview_board.py`, `preview_dev_server.py`, `preview_settings.py`, `preview_process.py`, `preview_device.py` and their tests; keep the tests of what stays (`test_preview_broker.py`, `test_scan_fixtures.py`, `test_vm_device.py`, a new `test_preview.py` for `render`, `page_url` and `backend`).

- [ ] **Step 1: Pin the unreleased testkit**

```toml
pihero-testkit = { git = "https://github.com/bkahlert/pihero", subdirectory = "testkit", rev = "<sha of feat/kiosk-preview>" }
```

Run: `uv lock && uv run --frozen python -c "import pihero_testkit.preview"`

- [ ] **Step 2: `vm_device.py` on `device_file`**

```python
"""The device directory tier 2 boots: the sample device file with the testkit's user and the local apt repository."""
from pathlib import Path

from pihero_testkit import device_file

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "devices" / "sample" / "user-data"
OUT = ROOT / "dist" / "vm-device"
SOURCE = "/etc/apt/sources.list.d/netmon.sources"


def render(sample: str, key: str) -> str:
    return device_file.with_source(device_file.with_user(sample, key), SOURCE)


def write(out: Path = OUT, sample: Path = SAMPLE) -> Path:
    return device_file.write(out, render(sample.read_text(), device_file.PUBLIC_KEY.read_text().strip()))


if __name__ == "__main__":
    print(write())
```

`test_vm_device.py` keeps passing; drop its tests of `block` (now the testkit's).

- [ ] **Step 3: The `Backend` in `preview_broker.py`**

Add, keeping `parse_broker`, `run_command`, `publish_command`, `ensure`, `publish`, `stop`, `main`:

```python
LOOPBACK = ("localhost", "127.0.0.1", "::1")


FAKE = "fake"


def parse_broker(text: str | None) -> Broker:
    if text in (None, "", FAKE, "fixture"):
        return Broker(FAKE, "localhost", WEBSOCKET_PORT)
    if text == DEVICE:
        return Broker(DEVICE, "127.0.0.1", WEBSOCKET_PORT)
    host, separator, port = text.rpartition(":")
    if not separator or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError(f"BROKER must be fake, device or HOST:PORT, not {text!r}")
    return Broker(EXTERNAL, host, int(port))


class MosquittoBackend:
    """netmon's backend for one session: the fake broker in a container, the board's own, or an address given."""

    def __init__(self, broker: Broker, scan: scan_fixtures.Scan):
        self.broker, self.scan = broker, scan
        self.managed = broker.kind == FAKE
        self.mac_port = broker.port if broker.kind == FAKE or (broker.kind == EXTERNAL and broker.host in LOOPBACK) else None

    def start(self) -> None:
        ensure(self.broker, self.scan)

    def stop(self) -> None:
        stop()

    def describe(self) -> str:
        return self.broker.describe()

    def address_for(self, served) -> tuple[str, int]:
        """Return the broker's host and port as the page of `served` reaches it."""
        if self.mac_port is not None:
            host, _, port = served.address(self.mac_port).rpartition(":")
            return host, int(port)
        return self.broker.host, self.broker.port
```

`Broker.describe()` says `fake on localhost:8080` for the fake. `README.md` and the Makefile's help lines say `BROKER=fake|device|HOST:PORT`; `fixture` is still accepted for one release.

- [ ] **Step 4: `tests/preview.py`**

```python
"""make preview-browser, preview-vm and preview-device: netmon's page from the dev server in a browser, a VM's kiosk or a board's kiosk."""
import sys
from pathlib import Path

from pihero_testkit import device_file
from pihero_testkit.preview import DevServer, Settings, main

import preview_broker
import scan_fixtures
import vm_device

ROOT = Path(__file__).resolve().parents[1]
DEV_PORT = 8081
NETMON_PACKAGES = ("netmon-scanner", "netmon-display")
KIOSK_PACKAGE = "pihero-kiosk"


def render(sample: str, key: str) -> str:
    """Return the sample for the preview's VM: no netmon source, packages or boot-config lines; the kiosk named, since only netmon-display brought it."""
    text = device_file.with_user(sample, key)
    text = device_file.drop(text, f"  - path: {vm_device.SOURCE}")
    for package in NETMON_PACKAGES:
        text = text.replace(f"  - {package}\n", f"  - {KIOSK_PACKAGE}\n" if package == "netmon-display" else "")
    return "".join(line for line in text.splitlines(keepends=True) if "--package netmon-" not in line)


def host_of(target: str) -> str:
    return target.partition(":")[0].rpartition("@")[2]


class Netmon:
    name = "netmon"
    root = ROOT
    display = (800, 480)

    def user_data(self) -> str:
        return render(vm_device.SAMPLE.read_text(), device_file.PUBLIC_KEY.read_text().strip())

    def dev_server(self, settings: Settings) -> DevServer:
        env = {"NETMON_STATS_PROXY": f"http://{host_of(settings.target)}"} if settings.flavor == "device" else {}
        return DevServer(["./gradlew", "--console=plain", "jsBrowserDevelopmentRun", "--continuous"], DEV_PORT, env)

    def backend(self, settings: Settings) -> preview_broker.MosquittoBackend:
        broker = preview_broker.parse_broker(settings.environ.get("BROKER"))
        scan = scan_fixtures.parse_scan(settings.environ.get("SCAN") or "14+39")
        if broker.kind == preview_broker.DEVICE and settings.flavor != "device":
            raise ValueError("BROKER=device is only for preview-device")
        return preview_broker.MosquittoBackend(broker, scan)

    def page_url(self, backend: preview_broker.MosquittoBackend, served) -> str:
        host, port = backend.address_for(served)
        return f"http://{served.address(DEV_PORT)}/?broker.host={host}&broker.port={port}"


if __name__ == "__main__":
    sys.exit(main(Netmon()))
```

Tests in `tests/test_preview.py`: `render` as `test_preview_device.py` had it; `page_url` for the fake in each flavor (`localhost:8080`, `10.0.2.2:8080`, `127.0.0.1:18080`), for `device` (`127.0.0.1:8080` on the board) and for a remote `HOST:PORT` (unchanged); `backend` refusing `BROKER=device` outside the device flavor; `dev_server` setting the proxy only for the device flavor. `tests/test_preview_broker.py` gains `MosquittoBackend`'s `managed`, `mac_port` and `address_for`.

- [ ] **Step 5: Delete what moved, run the tiers, commit**

```bash
git rm tests/preview_session.py tests/preview_flavors.py tests/preview_kiosk.py tests/preview_board.py \
  tests/preview_dev_server.py tests/preview_settings.py tests/preview_process.py tests/preview_device.py \
  tests/test_preview_session.py tests/test_preview_flavors.py tests/test_preview_kiosk.py tests/test_preview_board.py \
  tests/test_preview_dev_server.py tests/test_preview_settings.py tests/test_preview_process.py tests/test_preview_device.py
make test-tier0
make test-preview
git commit -am "refactor(preview): build the preview on pihero-testkit's library"
```

The `preview` marker now comes from the testkit's plugin; remove netmon's own registration in `conftest.py`. `make test-preview` in netmon keeps a test that the fake holds the fixture and answers a websocket handshake, and drops the VM session tests (the testkit's).

---

### Task 17: busy-screen's preview with a Node-RED fake

In `/Users/bkahlert/Development/com.bkahlert/busy-screen`, branch `feat/preview`.

**Files:**
- Create: `webpack.config.d/dev-server.js`, `tests/preview.py`, `tests/preview_backend.py`, `tests/test_preview.py`, `tests/test_preview_backend.py`
- Modify: `pyproject.toml` (the pin), `Makefile` (three targets), `tests/vm_device.py` (on `device_file`), `README.md`

- [ ] **Step 1: Pin and lock**

Same `rev` pin as Task 16, then `uv lock`. The jump from v2.4.0 brings the window and backing-disk support, the free-port repository and the deb-naming fixes: run `make test-tier2` once before anything else and fix what it shows.

- [ ] **Step 2: The dev server**

```javascript
// webpack.config.d/dev-server.js
// The preview's pages and the VM kiosk reach the dev server on 8082 (netmon has 8081, so both can preview at once). The
// kiosk asks for Host: 10.0.2.2:8082, which webpack-dev-server rejects unless allowedHosts says otherwise. With a host set,
// the client would reconnect to that host, which is the guest's own loopback in the VM, so it takes the address the page
// came from.
;(function (config) {
  'use strict'
  config.devServer = Object.assign(config.devServer || {}, {
    host: '127.0.0.1',
    port: 8082,
    allowedHosts: 'all',
    client: { webSocketURL: 'auto://0.0.0.0:0/ws' },
  })
})(config)
```

- [ ] **Step 3: `tests/preview_backend.py`, the Node-RED fake**

```python
"""busy-screen's backend for a preview: Node-RED from the vendored server directory with the repository's flow, seeded with a status."""
import json
import os
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "packages" / "busy-screen-server" / "server"
FLOW = ROOT / "packages" / "busy-screen-server" / "flows.json"
STATE = ROOT / "dist" / "preview" / "node-red"
PORT = 1880
FAKE, DEVICE, EXTERNAL = "fake", "device", "external"
LOOPBACK = ("localhost", "127.0.0.1", "::1")
DEFAULT_STATUS = {"name": "preview", "task": "busy-screen on the Mac", "duration": "PT10M"}


@dataclass(frozen=True)
class Address:
    kind: str
    host: str
    port: int

    def describe(self) -> str:
        if self.kind == FAKE:
            return f"fake on {self.host}:{self.port}"
        if self.kind == DEVICE:
            return f"the device's own, {self.host}:{self.port} on the board"
        return f"{self.host}:{self.port}"


def parse_backend(text: str | None) -> Address:
    """Return the backend BACKEND names: unset or `fake`, `device`, or HOST:PORT; raise ValueError for anything else."""
    if text in (None, "", FAKE):
        return Address(FAKE, "localhost", PORT)
    if text == DEVICE:
        return Address(DEVICE, "127.0.0.1", PORT)
    host, separator, port = text.rpartition(":")
    if not separator or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError(f"BACKEND must be fake, device or HOST:PORT, not {text!r}")
    return Address(EXTERNAL, host, int(port))


def parse_status(text: str | None) -> dict:
    """Return the status STATUS holds as JSON, or the default; raise ValueError for text that is not a JSON object."""
    if not text:
        return DEFAULT_STATUS
    status = json.loads(text)
    if not isinstance(status, dict):
        raise ValueError("STATUS must be a JSON object such as " + json.dumps(DEFAULT_STATUS))
    return status


def node_red_command(port: int, user_dir: Path) -> list[str]:
    return ["node", str(SERVER / "node_modules" / "node-red" / "red.js"), "--userDir", str(user_dir), "--settings", str(SERVER / "settings.js"), "flows.json"]


class NodeRedBackend:
    def __init__(self, address: Address, status: dict, state: Path = STATE):
        self.address, self.status, self.state = address, status, state
        self.managed = address.kind == FAKE
        self.mac_port = address.port if address.kind == FAKE or (address.kind == EXTERNAL and address.host in LOOPBACK) else None
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        """Start Node-RED on the Mac port with the repository's flow, wait for /info, and put the status; raise RuntimeError when the port is taken or node is missing."""
        if answers(self.address.port):
            raise RuntimeError(f"port {self.address.port} is taken; to use the backend there, run with BACKEND=localhost:{self.address.port}")
        if not shutil.which("node"):
            raise RuntimeError("node is not installed; brew install node")
        self.stop()
        shutil.rmtree(self.state, ignore_errors=True)
        self.state.mkdir(parents=True)
        shutil.copy(FLOW, self.state / "flows.json")
        log = (self.state / "node-red.log").open("w")
        self.process = subprocess.Popen(node_red_command(self.address.port, self.state), cwd=self.state, env={**os.environ, "PORT": str(self.address.port)}, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        (self.state / "pid").write_text(str(self.process.pid))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"Node-RED exited with status {self.process.returncode}; see {self.state / 'node-red.log'}")
            if answers(self.address.port):
                break
            time.sleep(0.5)
        else:
            raise TimeoutError(f"Node-RED did not answer on {self.address.port} within 120 s; see {self.state / 'node-red.log'}")
        put_status(self.address.port, self.status)

    def stop(self) -> None:
        """End the Node-RED a session left running, found by the pid file; nothing when there is none."""
        pid_file = self.state / "pid"
        if not pid_file.exists():
            return
        try:
            os.killpg(int(pid_file.read_text()), signal.SIGINT)
        except (ProcessLookupError, ValueError, PermissionError):
            pass
        pid_file.unlink(missing_ok=True)

    def describe(self) -> str:
        return self.address.describe()

    def address_for(self, served) -> str:
        """Return the backend's http origin as the page of `served` reaches it."""
        if self.mac_port is not None:
            return f"http://{served.address(self.mac_port)}"
        return f"http://{self.address.host}:{self.address.port}"


def answers(port: int) -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def put_status(port: int, status: dict, attempts: int = 60) -> None:
    """PUT the status to the flow, retrying while Node-RED still deploys it."""
    request = urllib.request.Request(f"http://127.0.0.1:{port}/status", data=json.dumps(status).encode(), method="PUT", headers={"Content-Type": "application/json"})
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=5):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    raise RuntimeError(f"the flow on port {port} did not accept the status")
```

Tier 0 tests: `parse_backend` (the three forms and the failure), `parse_status`, `node_red_command`, `NodeRedBackend.managed`/`mac_port` per kind, `address_for` with a served stub per flavor, `stop()` with and without a pid file (a fake `killpg`). A `preview`-marked test starts the fake on a free port and reads `/info` back.

- [ ] **Step 4: `tests/preview.py`**

```python
"""make preview-browser, preview-vm and preview-device: the page from the dev server in a browser, a VM's kiosk or a board's kiosk."""
import sys
from pathlib import Path

from pihero_testkit import device_file
from pihero_testkit.preview import DevServer, Settings, main

import preview_backend
import vm_device

ROOT = Path(__file__).resolve().parents[1]
DEV_PORT = 8082
PACKAGES = ("busy-screen-server", "busy-screen-display")
KIOSK_PACKAGE = "pihero-kiosk"


def render(sample: str, key: str) -> str:
    """Return the sample for the preview's VM: the tier-2 rendering minus busy-screen's source, packages and runcmd lines, with the kiosk named."""
    text = vm_device.render(sample, key)
    text = device_file.drop(text, vm_device.BUSY_SCREEN_SOURCES)
    for package in PACKAGES:
        text = text.replace(f"  - {package}\n", f"  - {KIOSK_PACKAGE}\n" if package == "busy-screen-display" else "")
    return "".join(line for line in text.splitlines(keepends=True) if "--package busy-screen-" not in line)


class BusyScreen:
    name = "busy-screen"
    root = ROOT
    display = (480, 320)

    def user_data(self) -> str:
        return render(vm_device.SAMPLE.read_text(), device_file.PUBLIC_KEY.read_text().strip())

    def dev_server(self, settings: Settings) -> DevServer:
        return DevServer(["./gradlew", "--console=plain", "jsBrowserDevelopmentRun", "--continuous"], DEV_PORT)

    def backend(self, settings: Settings) -> preview_backend.NodeRedBackend:
        address = preview_backend.parse_backend(settings.environ.get("BACKEND"))
        if address.kind == preview_backend.DEVICE and settings.flavor != "device":
            raise ValueError("BACKEND=device is only for preview-device")
        return preview_backend.NodeRedBackend(address, preview_backend.parse_status(settings.environ.get("STATUS")))

    def page_url(self, backend: preview_backend.NodeRedBackend, served) -> str:
        return f"http://{served.address(DEV_PORT)}/?address={backend.address_for(served)}"


if __name__ == "__main__":
    sys.exit(main(BusyScreen()))
```

`vm_device.py` moves onto `device_file` as netmon's did (its `with_user` and `block` go; `without_cog_args` and the panel removals stay). Tests in `tests/test_preview.py`: `render` leaves out the two packages, the source and the `--package busy-screen-` lines, names `pihero-kiosk`, keeps `URL=http://localhost/` and no `COG_ARGS`; `page_url` per flavor for the fake, `device` and a remote address.

- [ ] **Step 5: Makefile and README**

```make
preview-browser: ## the Node-RED fake, the dev server and the page in a browser tab (BACKEND=fake|HOST:PORT STATUS='{...}' INSPECT=Safari)
	@$(UV) python tests/preview.py --on browser

preview-vm: ## the fake, the dev server and the kiosk's WebKit in a VM window at 480x320, its inspector in Safari
	@$(UV) python tests/preview.py --on vm

preview-device: ## the fake, the dev server and the kiosk of a real Pi (TARGET=pi@host BACKEND=fake|device|HOST:PORT)
	@$(UV) python tests/preview.py --on device
```

Add the targets to `.PHONY`. README: a "Preview the page" subsection with the three targets, `BACKEND`, `STATUS`, `INSPECT`, `TARGET`, the port 8082, and the note that the development bundle is heavier than what the board runs (the Model B is the open risk the spec names).

- [ ] **Step 6: Run and commit**

```bash
make test-tier0
make test-tier2
make preview-vm      # by eye: the 480x320 window shows the status's frame colour
git commit -am "feat(preview): preview the page in a browser, a VM or on the board"
```

---

### Task 18: Release 2.8.0 and verify both apps at once

- [ ] **Step 1: pihero's branch review and merge**

`make test-all` and `make test-preview` green on `feat/kiosk-preview`; open the pull request with the title `feat(testkit): add the kiosk preview library`; merge.

- [ ] **Step 2: Release**

```bash
make release VERSION=2.8.0
git push origin v2.8.0
curl -fsS https://bkahlert.github.io/pihero/apt/Packages | grep -A1 '^Package: pihero'
```

Then the checkpoints as [docs/testing.md](../../testing.md) "Release" says.

- [ ] **Step 3: Switch the apps to the tag**

In both repositories: `tag = "v2.8.0"` in `pyproject.toml`, `uv lock`, tier 0, commit `build(deps): pin pihero-testkit v2.8.0`.

- [ ] **Step 4: Verify concurrently**

In two terminals each: netmon `make test-preview`, `make preview-vm`, `make preview-device TARGET=pi@netmon.local`; busy-screen `make test-preview`, `make preview-vm`, `make preview-device TARGET=pi@busy-screen.local`, both VMs and both boards running at the same time. After Ctrl-C on each, check on the Mac:

```bash
pgrep -fl 'qemu-system|gradlew|ssh -N|red.js'
podman ps --filter name=netmon-preview-broker
```

and on each board:

```bash
ls /run/*-preview /run/systemd/system/pihero-kiosk.service.d/ 2>&1
systemctl show -p Environment pihero-kiosk | grep -c preview
```

Expected: nothing listed on the Mac, no `-preview` paths on the boards, the kiosk on its own `URL`. Record the date and boards in testing.md "Real devices" (Task 15's paragraph).

---

## Self-review notes

- Spec coverage: every module in the spec's "Components" has a task (1 to 13); the marker, target and version are Task 14; the four documents are Task 15; the downstream and release steps are Tasks 16 to 18; the kiosk contract test is in Task 5; the base image lock in Task 1; the `pihero-kiosk` guard on `user_data()` in Task 9.
- Names used across tasks: `process.entry/alive/info`, `record.Record(directory).claim(stop_backend, restore_board)`, `kiosk.session_conf/UNIT/CONF/PACKAGE/INSPECTOR_PORT`, `layer.ensure(app)`, `vm.Session(layer, directory, display)`, `board.Board(target, name, tunnel_log)`, `flavors.flavor_for(flavor).show(app, settings, backend, dev, cleanup, rec)`, `session.run/main`, `dev_server.ensure(server, root, log)`, `window.place(pid, display)`.
- The Review Focus items are pinned by: Task 6 (`test_reads_a_record_of_the_older_format_without_crashing`, `test_claim_treats_a_corrupt_record_as_empty`), Task 13 (`test_goes_on_when_the_application_to_open_is_missing`), Task 9 (`test_refuses_a_device_file_without_the_kiosk`), Task 11 (`test_passes_the_targets_port`, `test_runs_the_remote_through_the_testkits_ssh_command`).
