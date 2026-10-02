# Virtual GPU Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every tier 2 VM has a virtual display of a configurable size, the harness can save a PNG of it, and the kiosk's tier 2 tests run for real.

**Architecture:** `vm.py` grows a pure `qemu_command()` that adds `virtio-gpu-pci` at the configured size and a QMP TCP port; a new `qmp` module speaks the protocol; `Vm.screenshot()` uses it. The option `--display` flows from pytest and the `vm` entry point through `provisioned_vm()` into `Vm`. Tier 2 tests assert the connector, the screenshot and the kiosk's restart count.

**Tech Stack:** Python 3.13, pytest, QEMU 11 (`virtio-gpu-pci`, QMP over TCP, `screendump` PNG), pytest-testinfra.

**Spec:** [docs/superpowers/specs/2026-10-02-virtual-gpu-design.md](../specs/2026-10-02-virtual-gpu-design.md)

## Global Constraints

- Branch `feat/testkit-virtual-gpu`, stacked on `feat/cog-package` (PR #29), in the pihero repository.
- Default display `800x480`; `none` means no GPU device. The QMP port is always configured. Regular expressions use named or non-capturing groups only.
- Tests: one class per subject, names are claims, tests first and helpers last, result stored before asserting, no comments or docstrings in tests. No test launches QEMU; the fake QMP server is a thread with a listening socket.
- Commits: Conventional Commits, scope `testkit` or `kiosk`, lowercase imperative header at most 72 characters, no AI-attribution trailers, one change per commit, gated on `uv run --frozen pytest -m tier0 -q`.
- IDE inspections with `mcp__idea__get_file_problems` (`errorsOnly: false`) on every changed file; explain what stays.
- One VM at a time; `make test-tier2` runs in the foreground or as a watched background task.

## Review Focus

1. `--display 480x320` must reach QEMU as `xres=480,yres=320`, not the default. Pinned in Task 1, `TestQemuCommand.test_sizes_the_gpu_as_asked`.
2. `--display none` must produce the VM of before: no GPU device at all. Pinned in Task 1, `TestQemuCommand.test_leaves_the_gpu_out_for_none`.
3. A malformed display such as `800` or `800×480` must fail at option time, not as a QEMU error ten minutes in. Pinned in Task 1, `TestParseDisplay.test_rejects_anything_but_width_x_height_or_none`.
4. A QMP error such as `screendump` without a console must surface as an exception naming the error, not as a silent empty return. Pinned in Task 2, `TestExecute.test_raises_with_qmps_error`.
5. The kiosk must not be in a restart loop on the virtual display, the defect the cog package fixes. Pinned in Task 3, `TestUnit.test_has_not_restarted_since_boot` under `--target=vm`.

---

### Task 1: The QEMU command line with a display, and the option that sets it

**Files:**
- Modify: `testkit/src/pihero_testkit/vm.py`
- Modify: `testkit/src/pihero_testkit/plugin.py:13-15`, `:64-67`
- Modify: `Makefile:5`, `:34`, `:44`
- Create: `testkit/tests/test_vm.py`

**Interfaces:**
- Produces: `vm.parse_display(display: str) -> tuple[int, int] | None`; `vm.qemu_command(base: prepare.BaseImage, overlay: Path, bootfs: Path, serial_log: Path, append: str, accel: str, memory_mb: int, port: int, qmp_port: int, display: tuple[int, int] | None) -> list[str]`; `Vm.__init__(..., display: str = "800x480")` with `self.display` (the parsed tuple) and `self.qmp_port`; `provisioned_vm(debs, device_dir, accel, keep, display="800x480")`; pytest option `--display` (default `800x480`); `python -m pihero_testkit.vm --display`.

- [x] **Step 1: Write the failing tests**

Create `testkit/tests/test_vm.py`:

```python
from pathlib import Path

import pytest

from pihero_testkit import prepare, vm

pytestmark = pytest.mark.tier0
BASE = prepare.BaseImage(Path("/b/rootfs.qcow2"), Path("/b/vmlinuz"), Path("/b/initrd.img"), Path("/b/boot"))


class TestParseDisplay:
    def test_reads_width_and_height(self):
        size = vm.parse_display("480x320")

        assert size == (480, 320)

    def test_is_none_for_none(self):
        size = vm.parse_display("none")

        assert size is None

    @pytest.mark.parametrize("display", ["800", "800×480", "800x", "x480", "", "800x480x60"])
    def test_rejects_anything_but_width_x_height_or_none(self, display):
        with pytest.raises(ValueError, match="WIDTHxHEIGHT"):
            vm.parse_display(display)


class TestQemuCommand:
    def test_has_a_gpu_of_the_default_size_and_a_qmp_port(self):
        command = qemu_command(display=(800, 480))

        assert "virtio-gpu-pci,xres=800,yres=480" in command
        assert "tcp:127.0.0.1:4444,server,nowait" in command
        assert command[command.index("tcp:127.0.0.1:4444,server,nowait") - 1] == "-qmp"

    def test_sizes_the_gpu_as_asked(self):
        command = qemu_command(display=(480, 320))

        assert "virtio-gpu-pci,xres=480,yres=320" in command

    def test_leaves_the_gpu_out_for_none(self):
        command = qemu_command(display=None)

        assert not any("virtio-gpu" in word for word in command)
        assert "-qmp" in command

    def test_keeps_the_headless_console_and_the_serial_log(self):
        command = qemu_command(display=(800, 480))

        assert command[command.index("-display") + 1] == "none"
        assert "file,id=serial0,path=/w/serial.log,append=on" in command


def qemu_command(display):
    return vm.qemu_command(BASE, Path("/w/overlay.qcow2"), Path("/w/bootfs.img"), Path("/w/serial.log"), "root=LABEL=rootfs", "hvf", 1024, 2222, 4444, display)
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_vm.py -q`
Expected: every test fails with `AttributeError: module 'pihero_testkit.vm' has no attribute 'parse_display'` or `'qemu_command'`.

- [x] **Step 3: Implement**

In `vm.py`, after `SSH_CONNECTION_FAILED = 255` add:

```python
DEFAULT_DISPLAY = "800x480"
DISPLAY = re.compile(r"^(?P<width>\d+)x(?P<height>\d+)$")


def parse_display(display: str) -> tuple[int, int] | None:
    """Returns the virtual display's size, or None for "none"; raises ValueError for anything else."""
    if display == "none":
        return None
    match = DISPLAY.match(display)
    if not match:
        raise ValueError(f"display must be WIDTHxHEIGHT or none, not {display!r}")
    return int(match["width"]), int(match["height"])


def qemu_command(base: prepare.BaseImage, overlay: Path, bootfs: Path, serial_log: Path, append: str, accel: str, memory_mb: int, port: int, qmp_port: int, display: tuple[int, int] | None) -> list[str]:
    """The qemu-system-aarch64 argument list for one boot: the headless virt machine, the disks, the network, the serial log, the QMP port, and the virtual display if any."""
    cpu = ["-cpu", "host"] if accel == "hvf" else ["-cpu", "cortex-a72"]
    gpu = ["-device", f"virtio-gpu-pci,xres={display[0]},yres={display[1]}"] if display else []
    return [
        "qemu-system-aarch64", "-M", "virt", "-accel", accel, *cpu, "-m", str(memory_mb), "-smp", "2",
        "-no-reboot", "-display", "none", "-monitor", "none",
        "-kernel", str(base.kernel), "-initrd", str(base.initrd), "-append", append,
        "-drive", f"if=none,file={overlay},format=qcow2,id=root", "-device", "virtio-blk-pci,drive=root",
        "-drive", f"if=none,file={bootfs},format=raw,id=boot", "-device", "virtio-blk-pci,drive=boot",
        "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:22", "-device", "virtio-net-pci,netdev=net0",
        "-device", "virtio-rng-pci",
        # `-serial file:` truncates on open and would discard the boot marker written below and every earlier boot.
        "-chardev", f"file,id=serial0,path={serial_log},append=on", "-serial", "chardev:serial0",
        # A TCP port, since a UNIX socket path is limited to 104 bytes, which a scratch directory already exceeds.
        "-qmp", f"tcp:127.0.0.1:{qmp_port},server,nowait",
        *gpu,
    ]
```

Add `import re` to the imports. In `Vm.__init__` add the parameter `display: str = DEFAULT_DISPLAY`, and after `self.port = _free_port()`:

```python
        self.qmp_port = _free_port()
        self.display = parse_display(display)
```

Replace the body of `start()` up to `self.boots += 1` with:

```python
        append = bootfs_mod.kernel_args(bootfs_mod.read_cmdline(self.bootfs))
        command = qemu_command(self.base, self.overlay, self.bootfs, self.serial_log, append, self.accel, self.memory_mb, self.port, self.qmp_port, self.display)
```

`provisioned_vm` gains `display: str = DEFAULT_DISPLAY` and passes `display=display` to `Vm(...)`; the kept-VM message gains a line `QMP port: {vm.qmp_port}`. `main()` gains `parser.add_argument("--display", default=DEFAULT_DISPLAY)` and passes `display=args.display`.

In `plugin.py` add after the `--device` option:

```python
    group.addoption("--display", default="800x480", help="for --target=vm: the virtual display's WIDTHxHEIGHT, or none")
```

and pass `display=request.config.getoption("--display")` to `provisioned_vm(...)`. In `pytest_configure` (line 18), validate early: `vm.parse_display(config.getoption("--display"))` when `--target` is `vm` (import `parse_display` from `.vm`; a `ValueError` there ends the session before any build).

In the Makefile: `DISPLAY ?= 800x480` after `QEMU_ACCEL ?= hvf`; `test-tier2` and `vm` get `--display=$(DISPLAY)`.

- [x] **Step 4: Run the tests**

Run: `uv run --frozen pytest testkit/tests/test_vm.py -q` then `uv run --frozen pytest -m tier0 -q`
Expected: all pass.

- [x] **Step 5: Inspections and commit**

```bash
git add testkit/src/pihero_testkit/vm.py testkit/src/pihero_testkit/plugin.py Makefile testkit/tests/test_vm.py
git commit -m "feat(testkit): give the tier 2 vm a virtual display and a qmp port"
```

---

### Task 2: The QMP client and `Vm.screenshot()`

**Files:**
- Create: `testkit/src/pihero_testkit/qmp.py`
- Modify: `testkit/src/pihero_testkit/vm.py` (`Vm.screenshot`)
- Create: `testkit/tests/test_qmp.py`

**Interfaces:**
- Produces: `qmp.execute(port: int, command: str, arguments: dict | None = None, timeout: float = 30) -> dict`; `Vm.screenshot(path: Path) -> Path`.

- [x] **Step 1: Write the failing tests**

Create `testkit/tests/test_qmp.py`:

```python
import json
import socket
import threading

import pytest

from pihero_testkit import qmp

pytestmark = pytest.mark.tier0


class TestExecute:
    def test_negotiates_capabilities_and_returns_the_commands_result(self):
        server = FakeQmp([{"return": {}}, {"return": {"qemu": {"major": 11}}}])
        with server:
            result = qmp.execute(server.port, "query-version")

        assert result == {"qemu": {"major": 11}}
        assert [m["execute"] for m in server.received] == ["qmp_capabilities", "query-version"]

    def test_passes_the_arguments(self):
        server = FakeQmp([{"return": {}}, {"return": {}}])
        with server:
            qmp.execute(server.port, "screendump", {"filename": "/tmp/x.png", "format": "png"})

        assert server.received[1]["arguments"] == {"filename": "/tmp/x.png", "format": "png"}

    def test_skips_events_while_waiting_for_the_reply(self):
        server = FakeQmp([{"return": {}}, {"event": "RESUME", "timestamp": {}}, {"return": {"ok": 1}}])
        with server:
            result = qmp.execute(server.port, "cont")

        assert result == {"ok": 1}

    def test_raises_with_qmps_error(self):
        server = FakeQmp([{"return": {}}, {"error": {"class": "GenericError", "desc": "no console"}}])
        with server, pytest.raises(RuntimeError, match="screendump: .*no console"):
            qmp.execute(server.port, "screendump", {"filename": "/tmp/x.png"})


class FakeQmp:
    def __init__(self, replies: list[dict]):
        self.replies = replies
        self.received: list[dict] = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.thread.join(timeout=5)
        self.sock.close()

    def serve(self):
        conn, _ = self.sock.accept()
        with conn, conn.makefile("rwb", buffering=0) as stream:
            stream.write(b'{"QMP": {"version": {}, "capabilities": []}}\r\n')
            for reply in self.replies:
                if "event" not in reply:
                    self.received.append(json.loads(stream.readline()))
                stream.write((json.dumps(reply) + "\r\n").encode())
```

- [x] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_qmp.py -q`
Expected: `ModuleNotFoundError: No module named 'pihero_testkit.qmp'`.

- [x] **Step 3: Implement**

Create `testkit/src/pihero_testkit/qmp.py`:

```python
"""A QEMU Machine Protocol client for the one thing the harness asks QEMU: a screendump."""

import json
import socket


def execute(port: int, command: str, arguments: dict | None = None, timeout: float = 30) -> dict:
    """Runs one QMP command on the monitor at 127.0.0.1:port and returns its result; raises RuntimeError with QMP's error."""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        stream = sock.makefile("rwb", buffering=0)
        greeting = json.loads(stream.readline())
        if "QMP" not in greeting:
            raise RuntimeError(f"not a QMP monitor on port {port}: {greeting}")
        _exchange(stream, {"execute": "qmp_capabilities"})
        message = {"execute": command, **({"arguments": arguments} if arguments else {})}
        return _exchange(stream, message)


def _exchange(stream, message: dict) -> dict:
    stream.write((json.dumps(message) + "\n").encode())
    while True:
        reply = json.loads(stream.readline())
        if "event" in reply:
            continue
        if "error" in reply:
            raise RuntimeError(f"{message['execute']}: {reply['error'].get('desc', reply['error'])}")
        return reply["return"]
```

In `vm.py`, import `from . import qmp` and add to `Vm` after `ssh_command()`:

```python
    def screenshot(self, path: Path) -> Path:
        """Saves what the virtual display shows as a PNG at path and returns it; fails without a display."""
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        qmp.execute(self.qmp_port, "screendump", {"filename": str(path), "format": "png"})
        return path
```

- [x] **Step 4: Run the tests and commit**

Run: `uv run --frozen pytest testkit/tests/test_qmp.py testkit/tests/test_vm.py -q`, then `uv run --frozen pytest -m tier0 -q`.

```bash
git add testkit/src/pihero_testkit/qmp.py testkit/src/pihero_testkit/vm.py testkit/tests/test_qmp.py
git commit -m "feat(testkit): save a screenshot of the vm's display over qmp"
```

---

### Task 3: Tier 2 proves the display and the kiosk on it

**Files:**
- Modify: `testkit/tests/test_boot.py` (new class `TestDisplay` before `TestBootConfigRoundTrip`)
- Modify: `packages/pihero-kiosk/tests/test_installed.py` (new test in `TestUnit`)

- [x] **Step 1: Write the tests**

In `testkit/tests/test_boot.py`, add before `class TestBootConfigRoundTrip` (add `from pathlib import Path` to the imports):

```python
class TestDisplay:
    def test_is_connected_at_the_configured_size(self, host, target):
        if target.display is None:
            pytest.skip("no display")

        status = host.file("/sys/class/drm/card0-Virtual-1/status").content_string.strip()
        modes = host.file("/sys/class/drm/card0-Virtual-1/modes").content_string.split()

        assert status == "connected"
        assert f"{target.display[0]}x{target.display[1]}" in modes

    def test_is_pictured_as_a_png_of_its_size(self, target):
        if target.display is None:
            pytest.skip("no display")

        picture = target.screenshot(target.workdir / "display.png")

        assert png_size(picture) == target.display
```

and at the end of the file:

```python
def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
```

In `packages/pihero-kiosk/tests/test_installed.py`, add to `TestUnit` after `test_is_running_with_a_connected_display`:

```python
    def test_has_not_restarted_since_boot(self, host):
        if not host.file("/dev/dri").exists:
            pytest.skip("no display adapter")
        if "connected" not in host.run("cat /sys/class/drm/card*-*/status").stdout.split():
            pytest.skip("no connected display")
        time.sleep(20)

        restarts = host.check_output("systemctl show -p NRestarts --value pihero-kiosk.service").strip()

        assert restarts == "0"
```

with `import time` added to the imports.

- [x] **Step 2: Run tier 2**

Run: `make test-tier2` (foreground or watched; about three minutes)
Expected: pass; `dist/vm/all-features/display.png` exists at 800×480; the kiosk tests report no skips except on armhf-only grounds (`TestStop` runs now). Look at the PNG with the Read tool: the pihero default kiosk page, or the console if cog had not painted yet.

Then: `make test-tier2 DISPLAY=none` is not run here (ten more minutes); `TestQemuCommand.test_leaves_the_gpu_out_for_none` covers the command, and the tests skip on `target.display is None`.

- [x] **Step 3: Commit**

```bash
git add testkit/tests/test_boot.py packages/pihero-kiosk/tests/test_installed.py
git commit -m "test: prove the virtual display and the kiosk on it in tier 2"
```

---

### Task 4: Documentation

**Files:**
- Modify: `docs/testing.md` (tier 2 bullets, the options paragraph)
- Modify: `docs/design.md` (`pihero-kiosk` section: the condition's list of places)
- Modify: `README.md` (`make test-tier2`, `make vm` lines)

- [x] **Step 1: Edit**

testing.md, options paragraph: after "`--device` for a device directory other than the testkit's `all-features`," add "`--display` for the VM's virtual display (`WIDTHxHEIGHT`, default `800x480`, or `none`),". Tier 2 **Disk and QEMU** bullet: after "serial console logged under `dist/vm/<device>/`" add ", a `virtio-gpu-pci` display at the configured size whose EDID makes the guest's connector `Virtual-1` prefer it, and a QMP monitor on a localhost TCP port through which `Vm.screenshot(path)` saves a PNG of the display (`DISPLAY=none` for the headless VM)". Tier 2 table row "Proves": add "the kiosk active on a virtual display, a screenshot of it".

design.md, `pihero-kiosk` section: "`ConditionPathExistsGlob=/dev/dri/card*` keeps the unit skipped, not failed, in the container, the VM, and on a headless board" becomes "in the container, a VM started with `--display none`, and on a headless board; the tier 2 VM has a virtual display by default since 2.4.0, where the unit runs on Pi Hero's cog".

README: `make test-tier2                     # boot a QEMU VM from a device file` becomes `make test-tier2 [DISPLAY=480x320]   # boot a QEMU VM from a device file, with a virtual display`; the `make vm` line in the same block likewise if present.

- [x] **Step 2: Inspections, tier 0, commit**

```bash
git add docs/testing.md docs/design.md README.md docs/superpowers/specs/2026-10-02-virtual-gpu-design.md docs/superpowers/plans/2026-10-02-virtual-gpu.md
git commit -m "docs: the tier 2 vm's virtual display and screenshots"
```
