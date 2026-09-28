# `pihero-usb-gadget` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Ethernet over USB out of the sample device file into a `pihero-usb-gadget` package that delegates to upstream `rpi-usb-gadget` and names the gadget after the board.

**Architecture:** A Debian package built with nfpm like `pihero-avahi`: postinst turns upstream on once, a package-shipped modprobe.d blacklist keeps upstream's `g_ether` from loading, and a oneshot unit gated on a USB device controller runs a Python script every boot that sets the shared subnet and loads `g_cdc` with serial-derived MACs and the device-tree model as product string. The tier-1 container image gains the Raspberry Pi archive so the dependency resolves.

**Tech Stack:** Python 3 standard library on the device, POSIX sh maintainer-script fragments, systemd units, nfpm, pytest with pytest-testinfra, podman, QEMU.

**Spec:** [docs/superpowers/specs/2026-09-28-pihero-usb-gadget-design.md](../specs/2026-09-28-pihero-usb-gadget-design.md)

## Global Constraints

- Every `pihero-*` package is `Architecture: all` and depends only on packages present in both the arm64 and armhf Raspberry Pi OS archives (`rpi-usb-gadget` 1.0.6 is in both).
- On-device code is Python 3 standard library; shell appears only in `ExecStart=` lines and maintainer-script fragments, and every shell file passes shellcheck.
- Names and paths: package `pihero-usb-gadget`, unit `pihero-usb-gadget.service`, executable `/usr/lib/pihero/usb-gadget`, conffile `/etc/pihero/usb-gadget.conf`; the package ships nothing under `/etc/pihero/`.
- Reboots are requested through `/run/reboot-required` and `/run/reboot-required.pkgs`, never taken.
- Tests: one class per subject, names are claims, tests first and helpers last in every file, result stored before asserting (`~/.config/agents/rules/testing.md`).
- Comments say only what the code cannot; Markdown references to files are links.
- Work on branch `feat/pihero-usb-gadget`, never on `main`. Every commit ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Commands run from the repository root with `uv run`; podman machine must be running for tiers 1 and 2.

## Review Focus

1. `PRODUCT` containing a double quote would break the kernel's parameter parser; the script must exit 1 before calling `nmcli` or `modprobe` (Task 2).
2. `PRODUCT=` left empty in the conffile must fall back to the device-tree model rather than load an unnamed gadget (Task 2).
3. `CIDR` set while upstream is off (profile missing) must exit 1 without loading the module, so the MOTD shows the failure (Task 2).
4. A changed tier-1 Containerfile must rebuild the image even though a tag for the platform already exists locally (Task 1).
5. On a system without a USB device controller the unit must be inactive with `ConditionResult=no`, never failed (Task 3).

---

### Task 1: Tier-1 image with the Raspberry Pi archive and a content-hashed tag

**Files:**
- Modify: `testkit/src/pihero_testkit/podman.py:18-23`
- Create: `testkit/tests/test_podman.py`
- Create: `testkit/src/pihero_testkit/tier1/raspberrypi.asc`
- Create: `testkit/src/pihero_testkit/tier1/raspberrypi.sources`
- Modify: `testkit/src/pihero_testkit/tier1/Containerfile`
- Modify: `docs/testing.md` (Tier 1 section)

**Interfaces:**
- Consumes: `podman.TIER1_DIR: Path`, `podman.PODMAN: list[str]` (existing).
- Produces: `podman.image_tag(platform: str, context: Path = TIER1_DIR) -> str`, used by `podman.image_for(platform)`.

- [ ] **Step 1: Write the failing test**

Create `testkit/tests/test_podman.py`:

```python
import shutil

import pytest

from pihero_testkit import podman

pytestmark = pytest.mark.tier0


class TestImageTag:
    def test_ends_with_the_platform(self):
        tag = podman.image_tag("linux/arm/v7")

        assert tag.startswith("localhost/pihero-tier1:")
        assert tag.endswith("-arm-v7")

    def test_changes_with_the_build_context(self, tmp_path):
        context = tmp_path / "tier1"
        shutil.copytree(podman.TIER1_DIR, context)
        before = podman.image_tag("linux/arm64", context)
        (context / "Containerfile").write_text((context / "Containerfile").read_text() + "# probe\n")

        after = podman.image_tag("linux/arm64", context)

        assert after != before
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest testkit/tests/test_podman.py -v`
Expected: FAIL with `AttributeError: module 'pihero_testkit.podman' has no attribute 'image_tag'`

- [ ] **Step 3: Implement `image_tag` and use it in `image_for`**

In `testkit/src/pihero_testkit/podman.py` add `import hashlib` to the imports and replace `image_for`:

```python
def image_tag(platform: str, context: Path = TIER1_DIR) -> str:
    """The tag carries a digest of the build context, so a changed Containerfile or fixture is rebuilt on first use."""
    digest = hashlib.sha256()
    for path in sorted(p for p in context.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(context)).encode())
        digest.update(path.read_bytes())
    return f"localhost/pihero-tier1:{digest.hexdigest()[:12]}-{platform.removeprefix('linux/').replace('/', '-')}"


def image_for(platform: str) -> str:
    tag = image_tag(platform)
    if subprocess.run([*PODMAN, "image", "exists", tag], check=False).returncode != 0:
        # The default OCI format drops HEALTHCHECK.
        subprocess.run([*PODMAN, "build", "--format", "docker", "--platform", platform, "-t", tag, "-f", str(TIER1_DIR / "Containerfile"), str(TIER1_DIR)], check=True)
    return tag
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest testkit/tests/test_podman.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit the tagging change**

```bash
git add testkit/src/pihero_testkit/podman.py testkit/tests/test_podman.py
git commit -m "testkit: tag the tier-1 image by its build context

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 6: Download and verify the archive key**

```bash
curl -fsSL https://archive.raspberrypi.com/debian/raspberrypi.gpg.key -o testkit/src/pihero_testkit/tier1/raspberrypi.asc
gpg --show-keys --with-fingerprint testkit/src/pihero_testkit/tier1/raspberrypi.asc
```

Expected: one `pub rsa2048 2012-06-17` key, uid `Raspberry Pi Archive Signing Key`, fingerprint
`CF8A 1AF5 02A2 AA2D 763B AE7E 82B1 2992 7FA3 303E`. Stop if the fingerprint differs.

- [ ] **Step 7: Write the apt source**

Create `testkit/src/pihero_testkit/tier1/raspberrypi.sources`:

```
Types: deb
URIs: https://archive.raspberrypi.com/debian/
Suites: trixie
Components: main
Signed-By: /etc/apt/keyrings/raspberrypi.asc
```

- [ ] **Step 8: Copy key and source into the image**

In `testkit/src/pihero_testkit/tier1/Containerfile`, insert before the `COPY boot/ /boot/firmware/` line:

```dockerfile
# pihero-usb-gadget depends on rpi-usb-gadget, which only the Raspberry Pi archive carries; the tests run apt-get update.
COPY raspberrypi.asc /etc/apt/keyrings/raspberrypi.asc
COPY raspberrypi.sources /etc/apt/sources.list.d/raspberrypi.sources
```

The existing `HEALTHCHECK` stays; the image already declares one.

- [ ] **Step 9: Build the image and prove the dependency resolves**

```bash
tag=$(uv run python -c "from pihero_testkit import podman; print(podman.image_for('linux/arm64'))")
podman run --rm "$tag" sh -c 'apt-get update -q >/dev/null && apt-cache policy rpi-usb-gadget'
```

Expected: the build runs (new tag), then `Candidate: 1.0.6` and a line containing `archive.raspberrypi.com/debian trixie/main arm64`.
Repeat with `linux/arm/v7` if the podman machine can run armhf; expected `trixie/main armhf`.

- [ ] **Step 10: Document the image in the testing doc**

In `docs/testing.md`, Tier 1 section, replace the first sentence

> The base image is `debian:trixie-slim` with `systemd`, `dbus`, `apt-utils`, and `sudo`, one per platform, started with `podman run --systemd=always … /sbin/init`.

with

> The base image is `debian:trixie-slim` with `systemd`, `dbus`, `apt-utils`, and `sudo`, plus the Raspberry Pi archive as an apt source signed by the key committed next to the Containerfile, because `pihero-usb-gadget` depends on `rpi-usb-gadget`, which only that archive carries. One image per platform, tagged with a digest of its build context so a changed Containerfile is rebuilt on first use, started with `podman run --systemd=always … /sbin/init`.

In the paragraph starting "What a container cannot show", append:

> The container has no USB device controller, so `pihero-usb-gadget.service` is skipped by its condition there and in the VM; the gadget itself is proven on a Pi over ssh.

- [ ] **Step 11: Commit**

```bash
git add testkit/src/pihero_testkit/tier1/raspberrypi.asc testkit/src/pihero_testkit/tier1/raspberrypi.sources testkit/src/pihero_testkit/tier1/Containerfile docs/testing.md
git commit -m "testkit: add the Raspberry Pi archive to the tier-1 image

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The `usb-gadget` loader script

**Files:**
- Create: `packages/pihero-usb-gadget/root/usr/lib/pihero/usb-gadget` (mode 0755)
- Create: `packages/pihero-usb-gadget/tests/test_usb_gadget.py`

**Interfaces:**
- Consumes: `pihero_testkit.scripts.load_script(path: Path) -> ModuleType` (existing).
- Produces: in the script, `device_tree_string(path: Path) -> str | None`, `macs(serial: str) -> tuple[str, str]`
  (host, dev), `module_args(host_addr: str, dev_addr: str, manufacturer: str, product: str) -> list[str]`
  (starts with `"g_cdc"`), `main() -> int`; environment `PRODUCT`, `CIDR`, `PIHERO_DEVICE_TREE`; external commands
  `nmcli` and `modprobe` found through `PATH`.

- [ ] **Step 1: Write the failing tests for the pure functions**

Create `packages/pihero-usb-gadget/tests/test_usb_gadget.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0

SCRIPT = Path(__file__).resolve().parents[1] / "root" / "usr" / "lib" / "pihero" / "usb-gadget"
usb_gadget = load_script(SCRIPT)

MODPROBE = ["modprobe", "g_cdc", "host_addr=02:00:a1:b2:c3:d4", "dev_addr=06:00:a1:b2:c3:d4", 'iManufacturer="Raspberry Pi Ltd."', 'iProduct="Raspberry Pi Zero W Rev 1.1"']


class TestDeviceTreeString:
    def test_strips_the_trailing_nul_and_whitespace(self, tmp_path):
        path = tmp_path / "model"
        path.write_bytes(b"Raspberry Pi Zero W Rev 1.1 \x00")

        result = usb_gadget.device_tree_string(path)

        assert result == "Raspberry Pi Zero W Rev 1.1"

    def test_is_none_on_a_missing_file(self, tmp_path):
        result = usb_gadget.device_tree_string(tmp_path / "model")

        assert result is None

    def test_is_none_on_an_empty_file(self, tmp_path):
        path = tmp_path / "serial-number"
        path.write_bytes(b"\x00")

        result = usb_gadget.device_tree_string(path)

        assert result is None


class TestMacs:
    def test_derives_host_and_dev_addresses_from_the_last_ten_digits_of_the_serial(self):
        result = usb_gadget.macs("00000000a1b2c3d4")

        assert result == ("02:00:a1:b2:c3:d4", "06:00:a1:b2:c3:d4")


class TestModuleArgs:
    def test_quotes_the_strings_for_the_kernel(self):
        result = usb_gadget.module_args("02:00:a1:b2:c3:d4", "06:00:a1:b2:c3:d4", "Raspberry Pi Ltd.", "Raspberry Pi Zero W Rev 1.1")

        assert result == MODPROBE[1:]
```

- [ ] **Step 2: Create the script with the pure functions and run the tests**

Create `packages/pihero-usb-gadget/root/usr/lib/pihero/usb-gadget`:

```python
#!/usr/bin/python3
"""Loads Pi Hero's USB Ethernet gadget: g_cdc named after the board, with MACs derived from its serial.

Environment:
  PRODUCT             USB product string (default: the device-tree model)
  CIDR                address of the "USB Gadget (shared)" profile (default: left as rpi-usb-gadget created it)
  PIHERO_DEVICE_TREE  directory holding model and serial-number (default /proc/device-tree)
"""

import os
import subprocess
import sys
from pathlib import Path

MODULE = "g_cdc"
MANUFACTURER = "Raspberry Pi Ltd."
SHARED_PROFILE = "USB Gadget (shared)"


def device_tree_string(path: Path) -> str | None:
    try:
        return path.read_bytes().rstrip(b"\x00").decode().strip() or None
    except OSError:
        return None


def macs(serial: str) -> tuple[str, str]:
    tail = serial[-10:]
    octets = ":".join(tail[i:i + 2] for i in range(0, len(tail), 2))
    return f"02:{octets}", f"06:{octets}"


def module_args(host_addr: str, dev_addr: str, manufacturer: str, product: str) -> list[str]:
    # The kernel's parameter parser accepts only double quotes around a value with spaces.
    return [MODULE, f"host_addr={host_addr}", f"dev_addr={dev_addr}", f'iManufacturer="{manufacturer}"', f'iProduct="{product}"']
```

Then:

```bash
chmod 755 packages/pihero-usb-gadget/root/usr/lib/pihero/usb-gadget
uv run pytest packages/pihero-usb-gadget/tests -v
```

Expected: 5 passed

- [ ] **Step 3: Write the failing CLI tests**

Append to `packages/pihero-usb-gadget/tests/test_usb_gadget.py`, after `TestModuleArgs` and before any helpers:

```python
class TestCli:
    def test_loads_g_cdc_named_after_the_model(self, device_tree, stubs):
        result = cli(device_tree, stubs)

        assert result.returncode == 0, result.stderr
        assert stubs.calls() == [MODPROBE]
        assert result.stdout == f"usb-gadget: loaded {' '.join(MODPROBE[1:])}\n"

    def test_product_overrides_the_model(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"PRODUCT": "Kitchen Pi"})

        assert result.returncode == 0, result.stderr
        assert stubs.calls() == [[*MODPROBE[:-1], 'iProduct="Kitchen Pi"']]

    def test_an_empty_product_falls_back_to_the_model(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"PRODUCT": ""})

        assert result.returncode == 0, result.stderr
        assert stubs.calls() == [MODPROBE]

    def test_cidr_sets_the_shared_profile_before_loading(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"CIDR": "10.10.10.10/29"})

        assert result.returncode == 0, result.stderr
        assert stubs.calls() == [["nmcli", "connection", "modify", "USB Gadget (shared)", "ipv4.addresses", "10.10.10.10/29"], MODPROBE]

    def test_exits_1_on_a_missing_serial(self, device_tree, stubs):
        (device_tree / "serial-number").unlink()

        result = cli(device_tree, stubs)

        assert result.returncode == 1
        assert "no serial number" in result.stderr
        assert stubs.calls() == []

    def test_exits_1_without_a_model_or_product(self, device_tree, stubs):
        (device_tree / "model").unlink()

        result = cli(device_tree, stubs)

        assert result.returncode == 1
        assert "PRODUCT is unset" in result.stderr
        assert stubs.calls() == []

    def test_exits_1_on_a_product_with_a_double_quote(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"PRODUCT": 'Pi "Zero"'})

        assert result.returncode == 1
        assert "double quote" in result.stderr
        assert stubs.calls() == []

    def test_exits_1_when_nmcli_fails_and_does_not_load_the_module(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"CIDR": "10.10.10.10/29"}, fail="nmcli")

        assert result.returncode == 1
        assert "could not set 10.10.10.10/29" in result.stderr
        assert [call[0] for call in stubs.calls()] == ["nmcli"]

    def test_exits_1_when_modprobe_fails(self, device_tree, stubs):
        result = cli(device_tree, stubs, fail="modprobe")

        assert result.returncode == 1
        assert "modprobe g_cdc" in result.stderr


STUB = """#!/bin/sh
printf '%s\\t' "${0##*/}" "$@" >>"$STUB_LOG"
printf '\\n' >>"$STUB_LOG"
[ "$STUB_FAIL" != "${0##*/}" ]
"""


class Stubs:
    def __init__(self, directory: Path):
        self.directory = directory
        self.log = directory / "calls.log"
        for name in ("modprobe", "nmcli"):
            (directory / name).write_text(STUB)
            (directory / name).chmod(0o755)

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [line.rstrip("\t").split("\t") for line in self.log.read_text().splitlines()]


@pytest.fixture
def stubs(tmp_path):
    directory = tmp_path / "bin"
    directory.mkdir()
    return Stubs(directory)


@pytest.fixture
def device_tree(tmp_path):
    path = tmp_path / "device-tree"
    path.mkdir()
    (path / "model").write_bytes(b"Raspberry Pi Zero W Rev 1.1\x00")
    (path / "serial-number").write_bytes(b"00000000a1b2c3d4\x00")
    return path


def cli(device_tree: Path, stubs: Stubs, env: dict | None = None, fail: str = "") -> subprocess.CompletedProcess:
    base = {key: value for key, value in os.environ.items() if key not in ("PRODUCT", "CIDR")}
    full = {**base, "PATH": f"{stubs.directory}:{base['PATH']}", "PIHERO_DEVICE_TREE": str(device_tree), "STUB_LOG": str(stubs.log), "STUB_FAIL": fail, **(env or {})}
    return subprocess.run([sys.executable, str(SCRIPT)], env=full, capture_output=True, text=True)
```

The stub records one tab-separated line per call and exits 1 only when `STUB_FAIL` names it.

- [ ] **Step 4: Run the CLI tests to verify they fail**

Run: `uv run pytest packages/pihero-usb-gadget/tests -v -k TestCli`
Expected: 9 failed, each with `returncode == 0` not matching (the script currently exits 0 doing nothing, so `stubs.calls() == []`).

- [ ] **Step 5: Implement `main`**

Append to `packages/pihero-usb-gadget/root/usr/lib/pihero/usb-gadget`:

```python
def fail(message: str) -> int:
    print(f"usb-gadget: {message}", file=sys.stderr)
    return 1


def main() -> int:
    device_tree = Path(os.environ.get("PIHERO_DEVICE_TREE", "/proc/device-tree"))
    serial = device_tree_string(device_tree / "serial-number")
    if not serial:
        return fail(f"no serial number in {device_tree}")
    product = os.environ.get("PRODUCT") or device_tree_string(device_tree / "model")
    if not product:
        return fail(f"no model in {device_tree} and PRODUCT is unset")
    if '"' in product:
        return fail(f"PRODUCT must not contain a double quote: {product}")
    cidr = os.environ.get("CIDR")
    if cidr and subprocess.run(["nmcli", "connection", "modify", SHARED_PROFILE, "ipv4.addresses", cidr]).returncode != 0:
        return fail(f"could not set {cidr} on '{SHARED_PROFILE}'")
    args = module_args(*macs(serial), MANUFACTURER, product)
    if subprocess.run(["modprobe", *args]).returncode != 0:
        return fail(f"modprobe {' '.join(args)} failed")
    print(f"usb-gadget: loaded {' '.join(args)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run all tier-0 tests of the package**

Run: `uv run pytest packages/pihero-usb-gadget/tests -v`
Expected: 14 passed

- [ ] **Step 7: Commit**

```bash
git add packages/pihero-usb-gadget/root/usr/lib/pihero/usb-gadget packages/pihero-usb-gadget/tests/test_usb_gadget.py
git commit -m "pihero-usb-gadget: load g_cdc named after the board

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Package manifest, unit, blacklist, and installed tests

**Files:**
- Create: `packages/pihero-usb-gadget/nfpm.yaml`
- Create: `packages/pihero-usb-gadget/units.txt`
- Create: `packages/pihero-usb-gadget/root/usr/lib/systemd/system/pihero-usb-gadget.service`
- Create: `packages/pihero-usb-gadget/root/usr/lib/modprobe.d/pihero-usb-gadget.conf`
- Create: `packages/pihero-usb-gadget/tests/test_installed.py`

**Interfaces:**
- Consumes: the script from Task 2 at `/usr/lib/pihero/usb-gadget`; the tier-1 image from Task 1; the `host`, `target`, and `version` fixtures from `pihero_testkit.plugin`; `target.purge(names)` and `target.reinstall()`.
- Produces: the unit name `pihero-usb-gadget.service` and the file `/usr/lib/modprobe.d/pihero-usb-gadget.conf` that Task 4's fragments and Task 6's docs refer to.

- [ ] **Step 1: Write the installed tests**

Create `packages/pihero-usb-gadget/tests/test_installed.py`:

```python
import pytest

pytestmark = pytest.mark.installed


class TestPackage:
    def test_is_installed_at_the_built_version(self, host, version):
        package = host.package("pihero-usb-gadget")

        assert package.is_installed
        assert package.version == version

    def test_pulls_in_rpi_usb_gadget(self, host):
        assert host.package("rpi-usb-gadget").is_installed

    def test_ships_the_loader_owned_by_root(self, host):
        file = host.file("/usr/lib/pihero/usb-gadget")

        assert file.exists
        assert file.mode == 0o755
        assert file.user == "root"

    def test_blacklists_g_ether(self, host):
        assert host.file("/usr/lib/modprobe.d/pihero-usb-gadget.conf").contains("^blacklist g_ether$")


class TestUnit:
    def test_is_enabled(self, host):
        assert host.service("pihero-usb-gadget").is_enabled

    def test_is_active_on_a_raspberry_pi(self, host, raspberry_pi_only):
        assert host.service("pihero-usb-gadget").is_running

    def test_is_skipped_by_its_condition_without_a_device_controller(self, host):
        if raspberry_pi(host):
            pytest.skip("runs on a Raspberry Pi")

        active_state = host.check_output("systemctl show --property=ActiveState --value pihero-usb-gadget.service").strip()
        condition_result = host.check_output("systemctl show --property=ConditionResult --value pihero-usb-gadget.service").strip()

        assert (active_state, condition_result) == ("inactive", "no")


class TestGadget:
    def test_is_named_after_the_board_or_the_conffile(self, host, raspberry_pi_only):
        expected = configured(host, "PRODUCT") or model(host)

        product = host.file("/sys/module/g_cdc/parameters/iProduct").content_string.strip()

        assert product == expected

    def test_derives_the_host_mac_from_the_serial(self, host, raspberry_pi_only):
        serial = host.file("/proc/device-tree/serial-number").content.rstrip(b"\x00").decode()
        tail = serial[-10:]
        expected = "02:" + ":".join(tail[i:i + 2] for i in range(0, 10, 2))

        host_addr = host.file("/sys/module/g_cdc/parameters/host_addr").content_string.strip()

        assert host_addr == expected

    def test_brings_up_usb0(self, host, raspberry_pi_only):
        assert host.interface("usb0").exists


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_leaves_nothing_behind(self, host, target):
        target.purge(["pihero-usb-gadget"])

        assert not host.file("/usr/lib/pihero/usb-gadget").exists
        assert not host.file("/usr/lib/systemd/system/pihero-usb-gadget.service").exists
        assert not host.file("/usr/lib/modprobe.d/pihero-usb-gadget.conf").exists

        target.reinstall()


@pytest.fixture
def raspberry_pi_only(host):
    if not raspberry_pi(host):
        pytest.skip("needs a Raspberry Pi")


def raspberry_pi(host) -> bool:
    return "Raspberry Pi" in model(host)


def model(host) -> str:
    file = host.file("/proc/device-tree/model")
    return file.content.rstrip(b"\x00").decode() if file.exists else ""


def configured(host, key: str) -> str | None:
    conf = host.file("/etc/pihero/usb-gadget.conf")
    if not conf.exists:
        return None
    for line in conf.content_string.splitlines():
        if line.startswith(f"{key}="):
            return line.removeprefix(f"{key}=").strip().strip('"')
    return None
```

- [ ] **Step 2: Run tier 1 to verify it fails**

Run: `make test-tier1`
Expected: `pihero-usb-gadget/tests/test_installed.py` fails at `test_is_installed_at_the_built_version` (`is_installed` false), because the package does not exist yet. The other packages' tests still pass.

- [ ] **Step 3: Write the manifest, units file, unit, and blacklist**

`packages/pihero-usb-gadget/nfpm.yaml`:

```yaml
name: pihero-usb-gadget
arch: all
platform: linux
version: ${VERSION}
section: admin
priority: optional
maintainer: Björn Kahlert <bkahlert@users.noreply.github.com>
description: |
  Pi Hero: Ethernet over USB, named after the board.
  Turns rpi-usb-gadget on and loads g_cdc (CDC ECM) once NetworkManager is up, with MACs derived from
  the board serial and the device-tree model as the USB product string; the shared subnet is configurable.
homepage: https://github.com/bkahlert/pihero
license: MIT
depends:
  - pihero
  - rpi-usb-gadget
contents:
  - src: root/
    dst: /
    type: tree
scripts:
  postinstall: .build/postinst
  preremove: .build/prerm
  postremove: .build/postrm
```

`packages/pihero-usb-gadget/units.txt`:

```
pihero-usb-gadget.service
```

`packages/pihero-usb-gadget/root/usr/lib/systemd/system/pihero-usb-gadget.service`:

```ini
[Unit]
Description=Pi Hero: USB Ethernet gadget (CDC ECM)
After=NetworkManager.service
Wants=NetworkManager.service
ConditionPathExistsGlob=/sys/class/udc/*

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=-/etc/pihero/usb-gadget.conf
ExecStart=/usr/lib/pihero/usb-gadget

[Install]
WantedBy=multi-user.target
```

`packages/pihero-usb-gadget/root/usr/lib/modprobe.d/pihero-usb-gadget.conf`:

```
# rpi-usb-gadget lists g_ether in modules-load.d; pihero-usb-gadget.service loads g_cdc instead, after NetworkManager.
blacklist g_ether
```

- [ ] **Step 4: Build and run the tier-0 static checks**

```bash
make build
uv run pytest testkit/tests/test_static.py -v
```

Expected: `dist/pihero-usb-gadget_<version>_all.deb` is listed; `test_unit_passes_systemd_analyze_verify[pihero-usb-gadget.service]` passes; all shellcheck and schema tests pass. Then `dpkg-deb --contents` through the tools container shows `./usr/lib/pihero/usb-gadget` as `-rwxr-xr-x`:

```bash
uv run python -c "from pihero_testkit import tools; import glob; deb = sorted(glob.glob('dist/pihero-usb-gadget_*_all.deb'))[-1]; print(tools.run(['dpkg-deb', '--contents', f'/work/{deb}'], capture=True).stdout)"
```

- [ ] **Step 5: Run tier 1 to verify it passes**

Run: `make test-tier1`
Expected: every `pihero-usb-gadget` test passes or is skipped with "needs a Raspberry Pi"; `test_is_skipped_by_its_condition_without_a_device_controller` passes; `test_purge_leaves_nothing_behind` passes. The install pulls `rpi-usb-gadget` and `network-manager` from the archive, which adds about a minute.

- [ ] **Step 6: Commit**

```bash
git add packages/pihero-usb-gadget/nfpm.yaml packages/pihero-usb-gadget/units.txt packages/pihero-usb-gadget/root/usr/lib/systemd/system/pihero-usb-gadget.service packages/pihero-usb-gadget/root/usr/lib/modprobe.d/pihero-usb-gadget.conf packages/pihero-usb-gadget/tests/test_installed.py
git commit -m "pihero-usb-gadget: package, unit, and g_ether blacklist

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Maintainer-script fragments

**Files:**
- Create: `packages/pihero-usb-gadget/scripts/postinst.sh`
- Create: `packages/pihero-usb-gadget/scripts/postrm.sh`

**Interfaces:**
- Consumes: `pihero_testkit.maintscripts.write(pkg_dir)`, which wraps `postinst.sh` in the `configure` block before enabling the unit and `postrm.sh` in the `purge` block (existing, run by `make build`).
- Produces: the enable-once and purge-off behaviour Task 5's device file and Task 6's docs describe.

- [ ] **Step 1: Write the postinst fragment**

Create `packages/pihero-usb-gadget/scripts/postinst.sh`:

```sh
# shellcheck shell=sh
# rpi-usb-gadget refuses anything but a Raspberry Pi. Turning it on is the one step that needs a reboot; an upgrade finds it on.
if grep -qs 'Raspberry Pi' /proc/device-tree/model && [ ! -f /etc/modules-load.d/usb-gadget.conf ]; then
  rpi-usb-gadget on -f >/dev/null
  printf '*** System restart required ***\n' >/run/reboot-required
  grep -qsx pihero-usb-gadget /run/reboot-required.pkgs || echo pihero-usb-gadget >>/run/reboot-required.pkgs
fi
```

- [ ] **Step 2: Write the postrm fragment**

Create `packages/pihero-usb-gadget/scripts/postrm.sh`:

```sh
# shellcheck shell=sh
# Purging the package turns the feature off. rpi-usb-gadget may already be gone when both are purged in one run.
if grep -qs 'Raspberry Pi' /proc/device-tree/model && command -v rpi-usb-gadget >/dev/null && [ -f /etc/modules-load.d/usb-gadget.conf ]; then
  rpi-usb-gadget off >/dev/null
  printf '*** System restart required ***\n' >/run/reboot-required
  grep -qsx pihero-usb-gadget /run/reboot-required.pkgs || echo pihero-usb-gadget >>/run/reboot-required.pkgs
fi
```

- [ ] **Step 3: Regenerate the scripts and check them**

```bash
make build
cat packages/pihero-usb-gadget/.build/postinst
uv run pytest testkit/tests/test_static.py -v -k shellcheck
```

Expected: the generated `postinst` contains the fragment inside `if [ "$1" = "configure" ] ...` before the `deb-systemd-helper` lines; the generated `postrm` contains it inside `if [ "$1" = "purge" ]`; both fragments and all generated scripts pass shellcheck.

- [ ] **Step 4: Re-run tier 1**

Run: `make test-tier1`
Expected: all pass; the container is not a Raspberry Pi, so both fragments skip their bodies, and purge in `test_purge_leaves_nothing_behind` still succeeds.

- [ ] **Step 5: Commit**

```bash
git add packages/pihero-usb-gadget/scripts/postinst.sh packages/pihero-usb-gadget/scripts/postrm.sh
git commit -m "pihero-usb-gadget: turn rpi-usb-gadget on at install and off at purge

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Device files, device docs, and the tier-2 run

**Files:**
- Modify: `devices/sample/user-data` (`packages`, `write_files`, `runcmd`)
- Modify: `testkit/src/pihero_testkit/devices/all-features/user-data` (`packages`)
- Modify: `devices/README.md`
- Modify: `docs/workflows.md`
- Modify: `README.md` (package table)

**Interfaces:**
- Consumes: the package name `pihero-usb-gadget` and conffile keys `CIDR`, `PRODUCT` from Tasks 2 and 3.
- Produces: the committed device files tier 0 validates and tier 2 boots.

- [ ] **Step 1: Rewrite the sample device file's gadget parts**

In `devices/sample/user-data`:

Under `packages:` add a line so the list reads:

```yaml
packages:
  - pihero
  - pihero-avahi
  - pihero-usb-gadget
```

In `write_files`, delete the `/etc/modprobe.d/g_cdc.conf` entry, the comment above `usb-gadget.service`, and the
`/etc/systemd/system/usb-gadget.service` entry. After the `/etc/pihero/device-info.conf` entry add:

```yaml
  # CIDR is the subnet the Pi serves to the USB host; PRODUCT="..." would rename the gadget, which is the board model by default.
  - path: /etc/pihero/usb-gadget.conf
    content: CIDR=10.10.10.10/29
```

In `runcmd`, delete the four comment lines starting `# \`rpi: enable_usb_gadget: true\`` through `# ... loads g_cdc (CDC ECM) instead.`, the
`rpi-usb-gadget on -f && ...` line, and the `nmcli connection modify "USB Gadget (shared)" ...` line. The list then reads:

```yaml
runcmd:
  - hostnamectl set-hostname --pretty "Sample Pi"
  - systemctl restart pihero-avahi-render.service
  # Tailscale: uncomment to join a tailnet on first boot with a single-use, expiring auth key (tailscale.com/kb/1085). For an
  # exit node keep the forwarding line and the flag, then approve the node under Machines in the admin console (kb/1103).
  # - curl -fsSL https://tailscale.com/install.sh | sh
  # - printf 'net.ipv4.ip_forward = 1\nnet.ipv6.conf.all.forwarding = 1\n' > /etc/sysctl.d/99-tailscale.conf && sysctl -q -p /etc/sysctl.d/99-tailscale.conf
  # - tailscale up --auth-key=tskey-auth-... --advertise-exit-node
```

`bootcmd`, the apt source, `power_state`, and everything else stay.

- [ ] **Step 2: Add the package to the all-features device**

In `testkit/src/pihero_testkit/devices/all-features/user-data` the `packages` list becomes:

```yaml
packages:
  - avahi-utils
  - pihero
  - pihero-avahi
  - pihero-usb-gadget
```

- [ ] **Step 3: Validate both device files**

Run: `uv run pytest testkit/tests/test_static.py -v -k schema`
Expected: `test_device_file_validates_against_cloud_init_schema[sample]` and `[all-features]` pass.

- [ ] **Step 4: Update the devices README**

In `devices/README.md`:

Replace the `write_files` bullet with:

> - `write_files` puts the signed apt source in place (the key is inline, so the device trusts nothing else),
>   `/etc/pihero/device-info.conf` with the `MODEL` for the Finder icon, and `/etc/pihero/usb-gadget.conf` with the subnet the
>   Pi serves over USB.

Replace the `runcmd` bullet with:

> - `runcmd` sets the pretty name the Pi is advertised under, restarts the Avahi renderer, and holds the commented Tailscale
>   lines: install, join with an auth key, and, for an exit node, forwarding plus `--advertise-exit-node`.

Replace the `power_state` bullet with:

> - `power_state` reboots when a package left `/run/reboot-required` behind; `pihero-usb-gadget` does on its first install.

After the "The Finder icon" section and before "Flash", add:

> ## Ethernet over USB
>
> `pihero-usb-gadget` turns on Raspberry Pi's `rpi-usb-gadget`, which provides the boot overlay, the NetworkManager profiles,
> and the switch to a host that shares its internet connection, and loads a CDC ECM gadget once NetworkManager is up, named
> after the board (`Raspberry Pi Zero 2 W Rev 1.0`) with MACs derived from the board serial, so a Mac sees the same device on
> every boot. `/etc/pihero/usb-gadget.conf` takes two optional keys: `CIDR`, the address the Pi serves to the host (upstream's
> `10.12.194.1/28` if unset), and `PRODUCT`, another name for the gadget, double-quoted when it contains spaces. Changing them
> later: edit the file on the Pi and reboot. Windows has no driver for CDC ECM; [docs/raspberry-pi-os.md](../docs/raspberry-pi-os.md)
> says why upstream's `g_ether` is not used.

In "Later changes", replace the last sentence with:

> Small things are done live and survive updates: the icon as above, the gadget's name and subnet in
> `/etc/pihero/usb-gadget.conf` followed by a reboot, network settings with `nmcli`, boot settings with
> `/usr/lib/pihero/bootconfig`.

- [ ] **Step 5: Update workflows and the README table**

In `docs/workflows.md`, "Bring up a new device" step 1, replace "and the USB subnet." with "and the USB subnet in
`/etc/pihero/usb-gadget.conf`." In "Change a device", replace "the Finder icon in `/etc/pihero/device-info.conf` followed
by `systemctl restart pihero-avahi-render.service`, network settings" with "the Finder icon in `/etc/pihero/device-info.conf`
followed by `systemctl restart pihero-avahi-render.service`, the USB gadget's name and subnet in `/etc/pihero/usb-gadget.conf`
followed by a reboot, network settings".

In `README.md`, add a row to the package table after `pihero-avahi`:

```markdown
| `pihero-usb-gadget` | Ethernet over USB on top of Raspberry Pi's `rpi-usb-gadget`: a Mac on the cable gets an address from the Pi and lists the interface under the board's name |
```

Reflow the table's column widths so the pipes align.

- [ ] **Step 6: Run tier 2**

Run: `make test-tier2` (about ten minutes; needs `make vm-prepare` to have run once)
Expected: `testkit/tests/test_boot.py` all pass, in particular `test_no_unit_failed` and `test_cloud_init_finished_without_errors`; `pihero-usb-gadget/tests/test_installed.py` passes with the gadget tests skipped ("needs a Raspberry Pi") and `test_is_skipped_by_its_condition_without_a_device_controller` passing.

- [ ] **Step 7: Commit**

```bash
git add devices/sample/user-data testkit/src/pihero_testkit/devices/all-features/user-data devices/README.md docs/workflows.md README.md
git commit -m "devices: install pihero-usb-gadget instead of carrying the gadget in user-data

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Design doc and field notes

**Files:**
- Modify: `docs/design.md`
- Modify: `docs/raspberry-pi-os.md`

**Interfaces:**
- Consumes: names and behaviour from Tasks 2 to 4.
- Produces: nothing code depends on.

- [ ] **Step 1: Update the design doc**

In `docs/design.md`:

Decisions table, replace the "USB Ethernet" row with:

```markdown
| USB Ethernet | `pihero-usb-gadget` on top of upstream `rpi-usb-gadget`, loading `g_cdc` from its own unit | Maintained by Raspberry Pi and handles internet-sharing detection; its `g_ether` default and its cloud-init hook both fail in practice, see [raspberry-pi-os.md](raspberry-pi-os.md) |
```

Architecture box, replace the two "Pi Hero" lines with these three (inner width stays 62 characters):

```
│ Pi Hero         pihero, pihero-avahi, pihero-usb-gadget,     │  this repo, packages/*
│                 later pihero-smb, pihero-splash,             │
│                 pihero-display-hdmi, pihero-bt-pan           │
```

Repository layout tree, after the `pihero-avahi/` block add:

```
  pihero-usb-gadget/
    root/usr/lib/pihero/usb-gadget                          # Python, loads g_cdc named after the board
    root/usr/lib/systemd/system/pihero-usb-gadget.service
    root/usr/lib/modprobe.d/pihero-usb-gadget.conf          # blacklist g_ether
```

After the `## \`pihero-avahi\`` section, add:

```markdown
## `pihero-usb-gadget`

Depends on `pihero` and Raspberry Pi's `rpi-usb-gadget`, which owns the `dwc2` overlay, the two NetworkManager profiles on
`usb0`, and the watcher that switches between them when the host shares its internet connection. postinst runs
`rpi-usb-gadget on -f` once and requests the reboot; purge runs `off` and requests one too. What upstream gets wrong for a
Mac the package replaces: `/usr/lib/modprobe.d/pihero-usb-gadget.conf` blacklists `g_ether`, which `systemd-modules-load`
honours, and `pihero-usb-gadget.service` (`Type=oneshot`, `After=NetworkManager.service`,
`ConditionPathExistsGlob=/sys/class/udc/*`, `EnvironmentFile=-/etc/pihero/usb-gadget.conf`) runs `usb-gadget` every boot,
which sets `CIDR` on the "USB Gadget (shared)" profile if given and loads `g_cdc` with `host_addr` and `dev_addr` derived
from the board serial, `iManufacturer` "Raspberry Pi Ltd.", and `iProduct` from `PRODUCT` or the device-tree model. The
condition keeps the unit skipped, not failed, until the enabling reboot and on anything without a device controller, which
is what the container and the VM are. Module parameters are read at load time, so a conffile change takes effect on the
next boot.
```

Planned packages: delete the `pihero-usb-gadget` bullet.

Configuration contract, "Identity" bullet: replace "the USB subnet from one `nmcli` line against the profile `rpi-usb-gadget`
creates." with "the USB gadget's name and subnet from `/etc/pihero/usb-gadget.conf`."

- [ ] **Step 2: Update the field notes**

In `docs/raspberry-pi-os.md`:

Intro, replace "what the [sample device file](../devices/sample/user-data) or `make flash` does about it" with "what the
packages, the [sample device file](../devices/sample/user-data), or `make flash` do about it".

Bullet "`rpi: enable_usb_gadget: true` never works on a fresh card", replace "The device file enables the gadget from `runcmd`
and touches `/run/reboot-required` for `power_state`." with "`pihero-usb-gadget`'s postinst runs `rpi-usb-gadget on -f`, which
has no timeout, and requests the reboot `power_state` takes."

Bullet "`g_ether` passes no frames to macOS 27", replace "The device file empties `rpi-usb-gadget`'s modules-load file, which
keeps the script's on/off state without loading `g_ether`, and loads `g_cdc` from its own unit." with "`pihero-usb-gadget`
blacklists `g_ether`, which `systemd-modules-load` honours, so `rpi-usb-gadget`'s on/off marker stays as it is, and loads
`g_cdc` from its own unit."

Bullet "macOS creates a network service per host MAC", replace "The unit derives both MACs from the board serial, and the
gadget is named like upstream's, `Raspberry Pi USB Gadget`." with "The unit derives both MACs from the board serial and names
the gadget after the board, `Raspberry Pi Zero 2 W Rev 1.0`, so several Pis stay apart in a Mac's network list."

- [ ] **Step 3: Check every link and run tiers 0 and 1**

```bash
grep -rn '](\.\./\|](docs/\|](devices/' README.md docs/*.md devices/README.md | grep -v http | awk -F'[(<)]' '{print $2}' | sort -u
make test
```

Expected: every printed relative path exists (resolve them from the file that contains them); `make test` green.

- [ ] **Step 4: Commit**

```bash
git add docs/design.md docs/raspberry-pi-os.md
git commit -m "docs: describe pihero-usb-gadget

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Hardware verification (needs a Raspberry Pi and a Mac)

**Files:**
- Modify: `devices/README.md` ("Ethernet over USB" section, one sentence about macOS's remembered service name)

**Interfaces:**
- Consumes: the built packages from Tasks 2 to 4 and `make deploy`.
- Produces: the confirmed behaviour of the product string on macOS.

This task is for the human partner; the executor stops here and reports.

- [ ] **Step 1: Clear the old device-file gadget on a Pi provisioned with the previous sample**

On the Pi:

```bash
sudo systemctl disable --now usb-gadget.service
sudo rm -f /etc/systemd/system/usb-gadget.service /etc/modprobe.d/g_cdc.conf
sudo systemctl daemon-reload
```

A freshly flashed card needs none of this.

- [ ] **Step 2: Deploy and reboot**

```bash
make deploy TARGET=pi@<host>
ssh pi@<host> sudo reboot
```

Expected: `apt install` succeeds, the MOTD before the reboot says `reboot required: yes (pihero-usb-gadget)` on a Pi where
upstream was off, and nothing about a reboot on a Pi where it already was on.

- [ ] **Step 3: Run the ssh tier**

```bash
uv run pytest -m installed --target=ssh --target-uri=pi@<host>
```

Expected: every `pihero-usb-gadget` test passes, including `test_is_named_after_the_board_or_the_conffile`,
`test_derives_the_host_mac_from_the_serial`, and `test_brings_up_usb0`; `TestRemoval` is skipped as mutating.

- [ ] **Step 4: Look at the Mac**

Open System Settings, Network. Expected: an interface named like the board, for example "Raspberry Pi Zero 2 W Rev 1.0", with
an address from the configured subnet. If the Mac already knew this Pi, it may show "Raspberry Pi USB Gadget"; remove that
service, unplug and replug, and note whether the new name appears.

- [ ] **Step 5: Record the finding**

In `devices/README.md`, "Ethernet over USB" section, add one sentence stating what macOS does with a remembered service name
(keeps the old name until the service is removed, or picks the new one up), as observed. Commit:

```bash
git add devices/README.md
git commit -m "docs: what macOS shows for a renamed gadget

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
