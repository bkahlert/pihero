# Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A gitignored `.env` points `make flash` and the tests at device directories kept elsewhere, the ssh tier skips the tests of packages a board lacks, and `make checkpoint` proves a release on both real boards with one verdict per board.

**Architecture:** The Makefile includes `.env` and exports `PIHERO_DEVICES` and `CHECKPOINTS`; `flash.device_dir` looks under `$PIHERO_DEVICES` after `devices/`. The pytest plugin asks the device for its dpkg status once at collection and skips items under a package directory the device lacks. A new `checkpoint` module resolves each board to `pi@<hostname>.local`, probes it, runs the ssh tier in a subprocess, and summarises.

**Tech Stack:** Python 3.13, pytest 9 (pytester for the plugin test), GNU make, OpenSSH.

**Spec:** [docs/superpowers/specs/2026-10-02-checkpoints-design.md](../specs/2026-10-02-checkpoints-design.md)

## Global Constraints

- Branch `feat/checkpoints` off `main` in the pihero repository; `main` takes changes only through a pull request with tiers 0 and 1 green.
- Variables: `PIHERO_DEVICES` (one directory, `~` expanded) and `CHECKPOINTS` (space-separated device names). The ssh user is `pi`; the host is `<hostname>.local`. The skip reason is `<package> is not installed on <uri>`.
- Tests: tier 0 under `testkit/tests`, one class per subject, names are claims, tests first and helpers last, result stored before asserting, no comments or docstrings in tests. No test opens an ssh connection or runs pytest in a subprocess; the plugin test runs pytester in process with a fake `installed_packages`.
- Regular expressions use named or non-capturing groups only. Doc comments on public functions state the contract in one line, third person.
- Commits: Conventional Commits, lowercase imperative header at most 72 characters, scope `testkit`, `docs`, or `devices`, no AI-attribution trailers, one change per commit, gated on `uv run --frozen pytest -m tier0 -q`.
- IDE inspections with `mcp__idea__get_file_problems` (`errorsOnly: false`) on every changed file where the JetBrains MCP is connected; explain what stays.

## Review Focus

1. A device name that exists both under `devices/` and under `$PIHERO_DEVICES` must resolve to `devices/`, so the quick start never changes meaning. Pinned in Task 1, `TestDeviceDir.test_prefers_devices_over_the_configured_directory`.
2. An unset or empty `PIHERO_DEVICES` (the Makefile exports it empty) must behave exactly as before, with an error that says where to set it. Pinned in Task 1, `TestDeviceDir.test_names_every_place_it_looked`.
3. Tests outside any package directory, the testkit's own, must never be skipped by the filter. Pinned in Task 2, `TestSshTarget.test_skips_the_installed_tests_of_packages_the_device_lacks` (the `testkit/tests` item passes).
4. A target other than ssh must not contact anything at collection. Pinned in Task 2, `TestSshTarget.test_asks_nothing_on_podman` (the fake raises if called).
5. An unreachable board must not stop the run, must not be reported as failed, and must still fail the command. Pinned in Task 3, `TestMain.test_reports_an_unreachable_board_and_fails`.

---

### Task 1: `.env` and the third place a device directory is looked for

**Files:**
- Modify: `Makefile:1-14`, the `flash` target's usage line
- Modify: `.gitignore`
- Modify: `testkit/src/pihero_testkit/flash.py:25-29` (`device_dir`), the usage string in `main`
- Test: `testkit/tests/test_flash.py` (`TestDeviceDir`)
- Modify: `devices/README.md` "Flash", `README.md` "Repository layout"

**Interfaces:**
- Produces: `flash.DEVICES_ENV = "PIHERO_DEVICES"`; `flash.device_dir(name: str) -> Path` (unchanged signature, one more place to look). The Makefile exports `PIHERO_DEVICES` and `CHECKPOINTS` (both default empty).

- [x] **Step 1: Write the failing tests**

Add to `TestDeviceDir` in `testkit/tests/test_flash.py`, after `test_resolves_a_name_under_devices`:

```python
    def test_resolves_a_name_under_the_configured_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(flash.DEVICES_ENV, str(tmp_path / "fleet"))
        (tmp_path / "fleet" / "checkpoint").mkdir(parents=True)
        (tmp_path / "fleet" / "checkpoint" / "user-data").write_text("#cloud-config\n")

        path = flash.device_dir("checkpoint")

        assert path == tmp_path / "fleet" / "checkpoint"

    def test_prefers_devices_over_the_configured_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(flash.DEVICES_ENV, str(tmp_path / "fleet"))
        for parent in ("devices", "fleet"):
            (tmp_path / parent / "pi").mkdir(parents=True)
            (tmp_path / parent / "pi" / "user-data").write_text("#cloud-config\n")

        path = flash.device_dir("pi")

        assert path == tmp_path / "devices" / "pi"

    def test_expands_the_home_directory_in_the_configured_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv(flash.DEVICES_ENV, "~/fleet")
        (tmp_path / "fleet" / "pi").mkdir(parents=True)
        (tmp_path / "fleet" / "pi" / "user-data").write_text("#cloud-config\n")

        path = flash.device_dir("pi")

        assert path == tmp_path / "fleet" / "pi"

    def test_names_every_place_it_looked(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(flash.DEVICES_ENV, "")

        with pytest.raises(SystemExit, match=r"no user-data.*devices/nope.*PIHERO_DEVICES"):
            flash.device_dir("nope")
```

Change the existing `test_rejects_a_directory_without_user_data` to expect the new wording:

```python
    def test_rejects_a_directory_without_user_data(self, tmp_path):
        with pytest.raises(SystemExit, match="no user-data"):
            flash.device_dir(str(tmp_path))
```

(It already matches `no user-data`; keep it as it is.)

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_flash.py -k TestDeviceDir -q`
Expected: the three new resolution tests fail with `SystemExit`, `test_names_every_place_it_looked` fails on the match (the old message does not mention `PIHERO_DEVICES`).

- [x] **Step 3: Implement `device_dir`**

In `testkit/src/pihero_testkit/flash.py`, add the constant next to the others and replace `device_dir`:

```python
DEVICES_ENV = "PIHERO_DEVICES"
```

```python
def device_dir(name: str) -> Path:
    """Returns the directory holding name's user-data: name as a path, devices/name, or name under $PIHERO_DEVICES, in that order."""
    candidates = [Path(name), Path.cwd() / "devices" / name]
    if configured := os.environ.get(DEVICES_ENV):
        candidates.append(Path(configured).expanduser() / name)
    for path in candidates:
        if (path / "user-data").is_file():
            return path
    hint = "" if configured else f"; set {DEVICES_ENV} in .env for device directories kept elsewhere"
    raise SystemExit(f"no user-data for {name!r} in {', '.join(map(str, candidates))}{hint}")
```

Update the usage string in `main`:

```python
        print("usage: python -m pihero_testkit.flash DEVICE DISK   (DEVICE: a directory under devices/ or $PIHERO_DEVICES, or a path; e.g. mypi disk9; see: diskutil list external)", file=sys.stderr)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_flash.py -q`
Expected: all pass.

- [x] **Step 5: The Makefile and `.gitignore`**

In `Makefile`, after `UV := uv run --frozen`:

```make
PIHERO_DEVICES ?=
CHECKPOINTS ?=
-include .env
export PIHERO_DEVICES CHECKPOINTS
```

Change the `flash` target's comment and usage:

```make
flash: ## write Raspberry Pi OS and a device's files to an SD card (make flash DEVICE=name|path DISK=disk9)
	@test -n "$(DEVICE)" -a -n "$(DISK)" || { echo "usage: make flash DEVICE=name DISK=diskN   (name: under devices/ or PIHERO_DEVICES from .env, or a path; diskutil list external)"; exit 2; }
	@$(UV) python -m pihero_testkit.flash "$(DEVICE)" "$(DISK)"
```

Append to `.gitignore`:

```
.env
```

Verify by hand (the Makefile has no unit tests here):

```shell
printf 'PIHERO_DEVICES=/tmp/fleet\nCHECKPOINTS=a b\n' > .env
make -n flash DEVICE=x DISK=disk9 | head -1         # the python line
make flash DEVICE=checkpoint DISK=disk9 2>&1 | tail -1   # the error names /tmp/fleet/checkpoint
rm .env
git status --short                                  # .env never shows up
```

- [x] **Step 6: Docs**

`devices/README.md`, section "Flash", replace the two command lines:

```
    make flash DEVICE=<name> DISK=disk9          # a directory under devices/, or under the directory .env names
    make flash DEVICE=<path> DISK=disk9          # or a device directory anywhere, such as a private repository
```

and add after "This" list's paragraph "macOS asks once for authorization …" a short paragraph:

```
Device directories kept in another repository are reached by name through a gitignored `.env` at the repository root
that `make` reads: `PIHERO_DEVICES=~/fleet/devices` makes `make flash DEVICE=checkpoint` look there after `devices/`.
```

`README.md`, "Repository layout" row for `devices/`:

```
| [devices/](devices)    | Device files, one directory per device, documented in [devices/README.md](devices/README.md); only `sample/` is committed, and a gitignored `.env` names a directory of device directories kept elsewhere |
```

- [x] **Step 7: Commit**

```bash
git add Makefile .gitignore testkit/src/pihero_testkit/flash.py testkit/tests/test_flash.py devices/README.md README.md
git commit -m "feat(testkit): find device directories under PIHERO_DEVICES from .env"
```

---

### Task 2: The ssh target skips the tests of packages the device lacks

**Files:**
- Modify: `testkit/src/pihero_testkit/build.py:41-42` (`discover`)
- Modify: `testkit/src/pihero_testkit/ssh.py`
- Modify: `testkit/src/pihero_testkit/plugin.py:32-38` (`pytest_collection_modifyitems`)
- Test: `testkit/tests/test_build.py` (`TestIsPackage`), `testkit/tests/test_ssh.py` (new), `testkit/tests/test_plugin.py` (new)
- Modify: `docs/testing.md` (tiers table, "Real devices" first paragraph), `docs/design.md` ("Development loop")

**Interfaces:**
- Consumes: `deploy.STATUS_QUERY: str`, `deploy.installed(status: str) -> set[str]` (existing).
- Produces: `build.is_package(directory: Path) -> bool`; `ssh.command(uri: str, remote: str) -> list[str]`; `ssh.installed_packages(uri: str) -> set[str]`; `plugin.package_of(path: Path) -> str | None`.

- [x] **Step 1: Write the failing tests**

Append to `testkit/tests/test_build.py`:

```python
class TestIsPackage:
    def test_is_true_for_a_directory_with_an_nfpm_manifest(self, tmp_path):
        (tmp_path / "nfpm.yaml").write_text("name: probe\n")

        assert build.is_package(tmp_path)

    def test_is_true_for_a_build_script_with_its_containerfile(self, tmp_path):
        (tmp_path / "build").write_text("#!/bin/sh\n")
        (tmp_path / "Containerfile").write_text("FROM scratch\n")

        assert build.is_package(tmp_path)

    def test_is_false_for_a_build_script_alone(self, tmp_path):
        (tmp_path / "build").write_text("#!/bin/sh\n")

        assert not build.is_package(tmp_path)

    def test_is_false_for_a_tests_directory(self, tmp_path):
        (tmp_path / "test_installed.py").write_text("")

        assert not build.is_package(tmp_path)
```

Create `testkit/tests/test_ssh.py`:

```python
import subprocess

import pytest

from pihero_testkit import deploy, ssh

pytestmark = pytest.mark.tier0

STATUS = "arm64\nbash ii \nkaomoji ii \npihero ii \npihero-avahi ii \npihero-usb-gadget rc \n"


class TestInstalledPackages:
    def test_asks_dpkg_over_ssh_in_batch_mode(self, monkeypatch):
        calls = fake_ssh(monkeypatch, STATUS)

        ssh.installed_packages("pi@host")

        assert calls == [["ssh", "-o", "BatchMode=yes", "pi@host", deploy.STATUS_QUERY]]

    def test_passes_the_port_of_the_uri(self, monkeypatch):
        calls = fake_ssh(monkeypatch, STATUS)

        ssh.installed_packages("pi@host:2222")

        assert calls == [["ssh", "-o", "BatchMode=yes", "-p", "2222", "pi@host", deploy.STATUS_QUERY]]

    def test_returns_the_names_dpkg_reports_installed(self, monkeypatch):
        fake_ssh(monkeypatch, STATUS)

        names = ssh.installed_packages("pi@host")

        assert names == {"bash", "kaomoji", "pihero", "pihero-avahi"}

    def test_exits_when_the_device_cannot_be_asked(self, monkeypatch):
        fake_ssh(monkeypatch, "", returncode=255, stderr="ssh: connect to host host port 22: Connection refused")

        with pytest.raises(SystemExit, match="pi@host.*Connection refused"):
            ssh.installed_packages("pi@host")

    def test_exits_without_a_uri(self):
        with pytest.raises(SystemExit, match="--target-uri"):
            ssh.installed_packages("")


def fake_ssh(monkeypatch, stdout: str, returncode: int = 0, stderr: str = "") -> list[list[str]]:
    calls: list[list[str]] = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(ssh.subprocess, "run", run)
    return calls
```

Create `testkit/tests/test_plugin.py`:

```python
from pathlib import Path

import pytest

from pihero_testkit import plugin, ssh

pytestmark = pytest.mark.tier0
pytest_plugins = ["pytester"]

OPTIONS = ("-p", "pihero_testkit.plugin", "-p", "no:pytest11.testinfra", "--import-mode=importlib", "-m", "installed", "-rs")
INSTALLED_TEST = "import pytest\n\npytestmark = pytest.mark.installed\n\n\ndef test_passes():\n    assert True\n"


class TestPackageOf:
    def test_is_the_package_directory_above_a_test(self, tmp_path):
        (tmp_path / "packages" / "pihero-kiosk" / "tests").mkdir(parents=True)
        (tmp_path / "packages" / "pihero-kiosk" / "nfpm.yaml").write_text("name: pihero-kiosk\n")

        name = plugin.package_of(tmp_path / "packages" / "pihero-kiosk" / "tests" / "test_installed.py")

        assert name == "pihero-kiosk"

    def test_is_none_outside_a_package(self, tmp_path):
        (tmp_path / "testkit" / "tests").mkdir(parents=True)

        name = plugin.package_of(tmp_path / "testkit" / "tests" / "test_boot.py")

        assert name is None


class TestSshTarget:
    def test_skips_the_installed_tests_of_packages_the_device_lacks(self, pytester, monkeypatch):
        monkeypatch.setattr(ssh, "installed_packages", lambda uri: {"pihero"})
        tree(pytester)

        result = pytester.runpytest_inprocess(*OPTIONS, "--target=ssh", "--target-uri=pi@host")

        result.assert_outcomes(passed=2, skipped=1)
        result.stdout.fnmatch_lines(["*pihero-kiosk is not installed on pi@host*"])

    def test_asks_nothing_on_podman(self, pytester, monkeypatch):
        monkeypatch.setattr(ssh, "installed_packages", lambda uri: pytest.fail("asked the device"))
        tree(pytester)

        result = pytester.runpytest_inprocess(*OPTIONS, "--target=podman")

        result.assert_outcomes(passed=3)


def tree(pytester) -> None:
    pytester.makefile(".yaml", **{"packages/pihero/nfpm": "name: pihero", "packages/pihero-kiosk/nfpm": "name: pihero-kiosk"})
    pytester.makepyfile(
        **{
            "packages/pihero/tests/test_installed": INSTALLED_TEST,
            "packages/pihero-kiosk/tests/test_installed": INSTALLED_TEST,
            "testkit/tests/test_boot": INSTALLED_TEST,
        }
    )
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_build.py testkit/tests/test_ssh.py testkit/tests/test_plugin.py -q`
Expected: `AttributeError` for `build.is_package`, `ssh.installed_packages`, `plugin.package_of`; the pytester tests fail on the missing attribute in `monkeypatch.setattr`.

- [x] **Step 3: Implement**

`testkit/src/pihero_testkit/build.py`: add `is_package` and let `discover` use it.

```python
def is_package(directory: Path) -> bool:
    """Returns whether directory builds a package: it has an nfpm manifest, or a build script next to a Containerfile."""
    return (directory / "nfpm.yaml").is_file() or ((directory / "build").is_file() and (directory / "Containerfile").is_file())


def discover() -> list[Path]:
    return sorted(p for p in PACKAGES.iterdir() if is_package(p))
```

`testkit/src/pihero_testkit/ssh.py`: a shared command builder, `installed_version` on it, and `installed_packages`.

```python
"""A real device over SSH as the ssh target. Mutating tests, and the tests of packages the device lacks, are skipped there by the plugin."""

import subprocess
from pathlib import Path

import testinfra

from . import deploy


def command(uri: str, remote: str) -> list[str]:
    """Returns the ssh command that runs remote at uri (user@host[:port]) without prompting; exits on an empty uri."""
    if not uri:
        raise SystemExit("--target=ssh needs --target-uri=user@host[:port]")
    user_host, _, port = uri.partition(":")
    return ["ssh", "-o", "BatchMode=yes", *(["-p", port] if port else []), user_host, remote]


def installed_version(uri: str) -> str:
    result = subprocess.run(command(uri, "dpkg-query -W -f '${Version}' pihero"), capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit(f"cannot read the installed pihero version from {uri}: {result.stderr.strip() or 'not installed'}")
    return result.stdout.strip()


def installed_packages(uri: str) -> set[str]:
    """Returns the names of the packages dpkg reports installed at uri; exits when the device cannot be asked."""
    result = subprocess.run(command(uri, deploy.STATUS_QUERY), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"cannot list the packages installed on {uri}: {result.stderr.strip()}")
    return deploy.installed(result.stdout)
```

`SshTarget.__init__` keeps its own empty-uri check as it is.

`testkit/src/pihero_testkit/plugin.py`: import `Path`, add `package_of`, extend the hook.

```python
from pathlib import Path
```

```python
def package_of(path: Path) -> str | None:
    """Returns the name of the package whose directory holds path, or None for a path outside every package."""
    return next((directory.name for directory in path.parents if build.is_package(directory)), None)


def pytest_collection_modifyitems(config, items):
    target = config.getoption("--target")
    installed, uri = None, config.getoption("--target-uri")
    if target == "ssh" and items:
        from .ssh import installed_packages

        installed = installed_packages(uri)
    for item in items:
        if "mutating" in item.keywords and target == "ssh":
            item.add_marker(pytest.mark.skip(reason="mutating test on a real device"))
        if "boot" in item.keywords and target == "podman":
            item.add_marker(pytest.mark.skip(reason="needs a booted system"))
        if installed is not None and (package := package_of(item.path)) and package not in installed:
            item.add_marker(pytest.mark.skip(reason=f"{package} is not installed on {uri}"))
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_build.py testkit/tests/test_ssh.py testkit/tests/test_plugin.py testkit/tests/test_deploy.py -q`
Expected: all pass. Then `uv run --frozen pytest -m tier0 -q` for the whole tier.

- [x] **Step 5: Docs**

`docs/testing.md`, tiers table, the ssh row:

```
| ssh | a Raspberry Pi | seconds | the `installed` tests of the packages the device has; the other packages' tests and mutating tests are skipped |
```

`docs/testing.md`, "Real devices", first sentence becomes:

```
`--target=ssh --target-uri=pi@host[:port]` builds nothing. It compares against the version installed on the device, because
the git-derived version only matches a device at a tag, and asks the device which packages it has, as `make deploy` does:
the installed tests of the others are skipped as "not installed on pi@host". The Avahi tests need `avahi-utils` on the device.
```

`docs/design.md`, "Development loop" bullet, append:

```
  The ssh tier asks the same question and skips the tests of the packages the device lacks, so a board with a subset is green.
```

- [x] **Step 6: Commit**

```bash
git add testkit/src/pihero_testkit/build.py testkit/src/pihero_testkit/ssh.py testkit/src/pihero_testkit/plugin.py testkit/tests/test_build.py testkit/tests/test_ssh.py testkit/tests/test_plugin.py docs/testing.md docs/design.md
git commit -m "feat(testkit): skip the tests of packages the ssh target lacks"
```

---

### Task 3: `make checkpoint`

**Files:**
- Create: `testkit/src/pihero_testkit/checkpoint.py`
- Test: `testkit/tests/test_checkpoint.py`
- Modify: `Makefile` (a `checkpoint` target after `deploy`)
- Modify: `docs/testing.md` ("Real devices", "Release"), `README.md` ("Build and test", "Release"), `docs/design.md` ("Release is a tag")

**Interfaces:**
- Consumes: `flash.device_dir(name) -> Path`, `flash.hostname(user_data: str) -> str | None` (existing), `PIHERO_DEVICES` and `CHECKPOINTS` exported by the Makefile (Task 1).
- Produces: `checkpoint.USER = "pi"`, `checkpoint.PROBE_TIMEOUT = 5`, `checkpoint.boards(argv: list[str]) -> list[str]`, `checkpoint.uri_for(name: str) -> str`, `checkpoint.reachable(uri: str) -> bool`, `checkpoint.run_tier(uri: str) -> int`, `checkpoint.main(argv: list[str]) -> int`.

- [x] **Step 1: Write the failing tests**

Create `testkit/tests/test_checkpoint.py`:

```python
import subprocess
import sys

import pytest

from pihero_testkit import checkpoint, flash

pytestmark = pytest.mark.tier0


class TestBoards:
    def test_takes_the_names_given(self):
        names = checkpoint.boards(["a", "b"])

        assert names == ["a", "b"]

    def test_falls_back_to_checkpoints_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("CHECKPOINTS", "checkpoint checkpoint32")

        names = checkpoint.boards([])

        assert names == ["checkpoint", "checkpoint32"]

    def test_exits_with_the_usage_without_names(self, monkeypatch):
        monkeypatch.setenv("CHECKPOINTS", "")

        with pytest.raises(SystemExit, match="CHECKPOINTS"):
            checkpoint.boards([])


class TestUriFor:
    def test_is_pi_at_the_hostname_of_the_devices_user_data_dot_local(self, tmp_path, monkeypatch):
        fleet(tmp_path, monkeypatch, {"cp": "checkpoint32"})

        uri = checkpoint.uri_for("cp")

        assert uri == "pi@checkpoint32.local"

    def test_exits_on_a_user_data_without_a_hostname(self, tmp_path, monkeypatch):
        fleet(tmp_path, monkeypatch, {"cp": None})

        with pytest.raises(SystemExit, match="no hostname"):
            checkpoint.uri_for("cp")


class TestMain:
    def test_runs_the_ssh_tier_against_every_reachable_board(self, tmp_path, monkeypatch, capsys):
        fleet(tmp_path, monkeypatch, {"a": "a", "b": "b"})
        calls = fake_ssh(monkeypatch)

        rc = checkpoint.main(["a", "b"])

        assert rc == 0
        assert calls[0] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "pi@a.local", "true"]
        assert calls[1] == [sys.executable, "-m", "pytest", "-m", "installed", "--target=ssh", "--target-uri=pi@a.local"]
        assert calls[3][-1] == "--target-uri=pi@b.local"
        assert capsys.readouterr().out.splitlines() == ["a: passed", "b: passed"]

    def test_reports_an_unreachable_board_and_fails(self, tmp_path, monkeypatch, capsys):
        fleet(tmp_path, monkeypatch, {"a": "a", "b": "b"})
        calls = fake_ssh(monkeypatch, probe={"pi@b.local": 255})

        rc = checkpoint.main(["a", "b"])

        assert rc == 1
        assert [c for c in calls if c[0] != "ssh"] == [[sys.executable, "-m", "pytest", "-m", "installed", "--target=ssh", "--target-uri=pi@a.local"]]
        assert capsys.readouterr().out.splitlines() == ["a: passed", "b: unreachable (pi@b.local)"]

    def test_fails_when_a_boards_tests_fail(self, tmp_path, monkeypatch, capsys):
        fleet(tmp_path, monkeypatch, {"a": "a", "b": "b"})
        fake_ssh(monkeypatch, tier={"pi@a.local": 1})

        rc = checkpoint.main(["a", "b"])

        assert rc == 1
        assert capsys.readouterr().out.splitlines() == ["a: failed", "b: passed"]


def fleet(tmp_path, monkeypatch, hosts: dict[str, str | None]) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(flash.DEVICES_ENV, str(tmp_path / "fleet"))
    for name, host in hosts.items():
        (tmp_path / "fleet" / name).mkdir(parents=True)
        (tmp_path / "fleet" / name / "user-data").write_text("#cloud-config\n" + (f"hostname: {host}\n" if host else ""))


def fake_ssh(monkeypatch, probe: dict[str, int] | None = None, tier: dict[str, int] | None = None) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ssh":
            return subprocess.CompletedProcess(cmd, (probe or {}).get(cmd[-2], 0))
        return subprocess.CompletedProcess(cmd, (tier or {}).get(cmd[-1].removeprefix("--target-uri="), 0))

    monkeypatch.setattr(checkpoint.subprocess, "run", run)
    return calls
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_checkpoint.py -q`
Expected: `ImportError: cannot import name 'checkpoint'`.

- [x] **Step 3: Implement `checkpoint.py`**

```python
"""Runs the ssh tier against the checkpoints, the real boards a release is proven on, and says which one is unreachable."""

import os
import subprocess
import sys

from .flash import device_dir, hostname

USER = "pi"
PROBE_TIMEOUT = 5


def boards(argv: list[str]) -> list[str]:
    """Returns the device names given, else those in CHECKPOINTS; exits with the usage when there are none."""
    names = argv or os.environ.get("CHECKPOINTS", "").split()
    if not names:
        raise SystemExit("usage: python -m pihero_testkit.checkpoint [DEVICE ...]   (default: the names in CHECKPOINTS, set in .env)")
    return names


def uri_for(name: str) -> str:
    """Returns pi@<hostname>.local for the device directory name resolves to; exits when its user-data names no hostname."""
    device = device_dir(name)
    host = hostname((device / "user-data").read_text())
    if not host:
        raise SystemExit(f"{device / 'user-data'} has no hostname")
    return f"{USER}@{host}.local"


def reachable(uri: str) -> bool:
    """Returns whether a non-interactive ssh login at uri succeeds within PROBE_TIMEOUT seconds."""
    probe = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={PROBE_TIMEOUT}", uri, "true"]
    return subprocess.run(probe, capture_output=True, check=False).returncode == 0


def run_tier(uri: str) -> int:
    """Runs the installed tests against uri and returns pytest's exit code."""
    tier = [sys.executable, "-m", "pytest", "-m", "installed", "--target=ssh", f"--target-uri={uri}"]
    return subprocess.run(tier, check=False).returncode


def main(argv: list[str]) -> int:
    verdicts: dict[str, str] = {}
    for name in boards(argv):
        uri = uri_for(name)
        if not reachable(uri):
            verdicts[name] = f"unreachable ({uri})"
            continue
        print(f"  {name}: the ssh tier against {uri}", file=sys.stderr, flush=True)
        verdicts[name] = "passed" if run_tier(uri) == 0 else "failed"
    for name, verdict in verdicts.items():
        print(f"{name}: {verdict}", flush=True)
    return 0 if all(verdict == "passed" for verdict in verdicts.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_checkpoint.py -q`
Expected: all pass.

- [x] **Step 5: The Makefile target**

After the `deploy` target:

```make
checkpoint: ## run the ssh tier against the checkpoints, the real boards CHECKPOINTS names in .env
	@$(UV) python -m pihero_testkit.checkpoint $(CHECKPOINTS)
```

Verify: `make checkpoint` without `.env` prints the usage line and exits 2; `make help` lists the target.

- [x] **Step 6: Docs**

`docs/testing.md`, "Real devices", replace everything after the first paragraph (from "What only a fresh card shows" to the end of the section) with:

```
Neither tier is a Raspberry Pi, so a release is proven on two real boards, the checkpoints, one per image. A 64-bit Zero 2 W
on Wi-Fi with `pihero-usb-gadget` is the gadget's board: only a fresh card there shows its postinst turning `rpi-usb-gadget`
on and requesting the reboot, purge turning it off, and a Mac on the cable getting an address. A 32-bit Zero, the hardware
floor, on a USB Ethernet hub covers ARMv6 timing and NetworkManager over a cable; it never takes the gadget, because
peripheral mode claims the Zero's one USB controller and leaves a board on a hub dark. Neither has a display, so the kiosk
is proven in tier 2 and on application boards. The checkpoints are disposable: their device directories live outside this
checkout, a release reflashes both, and nothing is kept on them.

A gitignored `.env` at the repository root, which `make` reads, names the directories and the boards:

    PIHERO_DEVICES=~/fleet/devices       # the directory holding the device directories
    CHECKPOINTS=checkpoint checkpoint32  # their names under it, one per image

`make flash DEVICE=<name>` finds a device directory there as well as under `devices/`, and `make checkpoint` runs the ssh tier
against every board in `CHECKPOINTS`, prints one verdict per board, and exits non-zero when one failed or was unreachable.
`make deploy TARGET=pi@host` reinstalls the freshly built packages the device already has over SSH for the development loop;
it adds none.
```

`docs/testing.md`, "Release", the code block becomes:

```shell
make release VERSION=2.1.0        # clean tree required; runs tiers 0 to 2, then tags v2.1.0
git push origin v2.1.0            # the release workflow builds, signs, and publishes
curl -fsS https://bkahlert.github.io/pihero/apt/Packages | grep -A1 '^Package: pihero'
make flash DEVICE=checkpoint DISK=disk9      # then the hardware step: reflash both checkpoints, one card at a time
make flash DEVICE=checkpoint32 DISK=disk9
ssh-keygen -R checkpoint.local; ssh-keygen -R checkpoint32.local   # reflashed boards have new host keys
make checkpoint                   # the ssh tier on both, once they have booted (about 6 min for the Zero 2 W, 16 for the Zero)
```

and this paragraph follows the block, before "Tags with a pre-release suffix":

```
The hardware step comes after publishing because a fresh card installs from the repository, so the checkpoints prove the
release as devices receive it. Their device directories are rendered as the repository holding them describes; the
boards' names, images, and `.env` are in "Real devices" above.
```

`README.md`, "Build and test" block, after the `make deploy` line:

```
make checkpoint                     # the ssh tier on the checkpoints, the real boards .env names
```

`README.md`, "Release" block:

```shell
make release VERSION=2.1.0   # clean tree required; runs tiers 0 to 2, then tags v2.1.0
git push origin v2.1.0       # CI builds, signs, and publishes
make checkpoint              # after reflashing the two real boards; docs/testing.md "Release" has the steps
```

`docs/design.md`, "Release is a tag" bullet, append:

```
  The published release is then proven on hardware: the two checkpoints, a 64-bit Zero 2 W with the gadget and a 32-bit
  Zero on a USB Ethernet hub, are reflashed from device directories a gitignored `.env` names, and `make checkpoint` runs
  the ssh tier on each. One board per image; the Zero never takes the gadget.
```

- [x] **Step 7: Commit**

```bash
git add testkit/src/pihero_testkit/checkpoint.py testkit/tests/test_checkpoint.py Makefile docs/testing.md README.md docs/design.md
git commit -m "feat(testkit): make checkpoint runs the ssh tier against the real boards"
```

---

### Task 4: Ship

- [x] **Step 1: The whole tier 0 and the IDE inspections**

Run: `uv run --frozen pytest -m tier0 -q`
Expected: all pass. Then `mcp__idea__get_file_problems` with `errorsOnly: false` on every changed file.

- [x] **Step 2: Commit the spec and the plan**

```bash
git add docs/superpowers/specs/2026-10-02-checkpoints-design.md docs/superpowers/plans/2026-10-02-checkpoints.md
git commit -m "docs(testkit): design and plan the checkpoints"
```

- [x] **Step 3: Pull request**

```bash
git push -u origin feat/checkpoints
gh pr create --title "feat(testkit): the checkpoints, the real boards a release is proven on" --body "..."
```

The body lists the three changes, the verification items of the handover, and that `uv run pytest -m installed --target=ssh --target-uri=pi@checkpoint32.local` without package directories is to be run on the next reflash.
