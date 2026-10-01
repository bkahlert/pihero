# The virtual GPU: the kiosk in the tier 2 VM, pictured

Date: 2026-10-02. Status: approved design, ready for planning. Builds on
[2026-10-01-cog-package-design.md](2026-10-01-cog-package-design.md), whose cog build is what keeps the kiosk alive here.

## Intent

The tier 2 VM has no display adapter, so `pihero-kiosk.service` is skipped by its condition and the kiosk's own tier 2
tests skip with it; nothing proves that cog starts, paints, survives a stop, or how much memory it takes, except a board.
The spike of 2026-10-01 showed what a `virtio-gpu-pci` device gives the VM: `/dev/dri/card0`, a connector `Virtual-1`
whose EDID carries the configured size as the preferred mode, a kiosk unit that starts, and, with the fixed cog, a page
painted by WPE WebKit that QEMU's `screendump` saves as a PNG.

This gives every tier 2 VM that display and the harness a way to picture it. Success looks like this: `make test-tier2`
boots the all-features device with an 800×480 virtual display, the kiosk unit is active without a restart, the kiosk's
stop test runs for real, the boot tests see the connector connected at that size and save `dist/vm/all-features/display.png`
at 800×480; an application passes its panel's size with `--display 480x320`, or `--display none` for the headless VM of
before; and `Vm.screenshot(path)` is there for an application's own kiosk test.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Default | The display is on, 800×480, in every tier 2 VM | The all-features device provisions the kiosk since the cog package, so its tests should run; 800×480 is the common HDMI panel size and the one netmon uses |
| Option | `--display WIDTHxHEIGHT` or `--display none` for pytest and `python -m pihero_testkit.vm`; `Vm(display=...)`; `make test-tier2 DISPLAY=...` and `make vm DISPLAY=...` | An application names its panel in one place; `none` keeps the old VM for a device without a kiosk |
| Device | `-device virtio-gpu-pci,xres=W,yres=H`, EDID on (QEMU's default) | The guest sees a connected connector with W×H preferred, as cog wants; no 3D, since macOS QEMU has no virgl, which is why cog's software path had to be fixed |
| Monitor | `-qmp tcp:127.0.0.1:<free port>,server,nowait` on every VM, display or not | A UNIX socket path has a 104-byte limit that a scratch directory already exceeds; a port costs nothing |
| Screenshot | `Vm.screenshot(path) -> Path`: QMP `screendump` with `format: png` into the path given, parent directories created | PNG needs QEMU 7.1 or newer; Homebrew ships 11, Ubuntu 24.04's runner 8.2. With `--display none` QEMU has no graphics console and `screendump` fails; the method raises with QMP's message |
| Testability | The QEMU command line comes from a function `qemu_command(...)` that `Vm.start()` calls, and the QMP exchange from a module `qmp` with `execute(port, command, arguments)` | Both are unit-tested in tier 0 without a VM: the argument list for the display variants, the client against a fake QMP server |
| Proof on the VM | Testkit boot tests: the connector is connected with the display's size as a mode, and a screenshot is a PNG of that size. Kiosk tests: `NRestarts=0` after the first frames, next to the existing running and stop tests that now run | The connector test proves the device without the kiosk; the restart count is the regression the cog fix guards against; the stop test proves `SuccessExitStatus=SIGKILL` on a real display |
| Emulation | Nothing special for `--qemu-accel tcg` | virtio-gpu is device emulation; cog's software rendering is slow there but the restart count stays zero either way |
| Memory | The VM keeps 1 GB | The kiosk's cgroup held about 250 MB in the spike; the all-features device leaves room |

## Components

- [vm.py](../../../testkit/src/pihero_testkit/vm.py): `parse_display("800x480") -> tuple[int, int] | None` (`None` for
  `none`, `ValueError` otherwise); `qemu_command(...)` builds the argument list `start()` runs today plus the GPU device
  (unless the display is `None`) and the QMP port; `Vm.__init__` takes `display: str = "800x480"` and picks a free
  `qmp_port`; `Vm.screenshot(path)`; `provisioned_vm(...)` and `main()` pass the display through; the kept VM's message
  names the QMP port.
- `qmp.py` (new): `execute(port, command, arguments=None) -> dict`: connects, reads the greeting, negotiates
  capabilities, sends the command, skips events, raises `RuntimeError` with QMP's error on failure, returns `return`.
- [plugin.py](../../../testkit/src/pihero_testkit/plugin.py): the `--display` option, default `800x480`.
- Makefile: `DISPLAY ?= 800x480` for `test-tier2` and `vm`.
- Tests: `testkit/tests/test_vm.py` and `testkit/tests/test_qmp.py` (tier 0, new); `testkit/tests/test_boot.py`
  gains `TestDisplay`; `packages/pihero-kiosk/tests/test_installed.py` gains the restart-count test.
- Docs: testing.md (the tier 2 bullets, the options, the screenshot), design.md (the kiosk section's claim that the VM
  has no display), README (`make vm`/`test-tier2` with `DISPLAY=`).

## Failure modes

- QEMU older than 7.1 on a host: `screendump` rejects `format: png`; the error names it, and the Brewfile's QEMU is far
  newer.
- The QMP port is taken between choosing it and starting QEMU: the same race the SSH port has today, and as unlikely.
- The kiosk under TCG never paints within the test's wait: the test asserts the unit's state and restart count, not the
  picture's content, so a slow paint passes; the screenshot then shows the console, which is the honest picture.
- An application's device file without `pihero-kiosk` under the default display: the kiosk tests skip as they do today
  when the package is absent; the connector and screenshot tests still pass.

## Follow-ups

1. `make release VERSION=2.4.0` once this and the cog package are on `main`.
2. netmon: bump the pin, assert the kiosk is active, save the screendump next to Playwright's screenshot, compare.
3. busy-screen: the same at `--display 480x320`, with its VM device rendered without the panel's settings.
