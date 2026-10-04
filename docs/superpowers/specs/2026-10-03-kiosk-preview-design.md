# The kiosk preview as a testkit library

Date: 2026-10-03. Status: approved design, ready for planning. Builds on
[2026-10-02-virtual-gpu-design.md](2026-10-02-virtual-gpu-design.md), whose window and backing-disk support the VM
session uses, and generalises netmon's `2026-10-03-preview-design.md` and `2026-10-03-preview-flavors-design.md`, the
reference implementation in `netmon/tests/preview*.py`.

## Intent

An app that shows a page in `pihero-kiosk` wants to see an edit where it is judged, from one command, with a Web
Inspector on the page, and with nothing left running when the command ends: in a browser tab on the Mac (fastest, the
browser's rendering), in the kiosk of a short-lived QEMU VM shown in a window (WPE WebKit, exact rendering, the Mac's
speed), or in the kiosk of a real board (the panel's own CPU). netmon has this as `make preview-browser`,
`preview-vm` and `preview-device`; busy-screen wants the same, and its page has the same engine differences and no
inspector at all.

Everything about the kiosk in netmon's implementation is the same for every app: the session's lifecycle and recovery,
the provisioned disk layer, the VM and its window, the kiosk's settings and restart, the inspector and its tunnel, the
board's drop-in and reverse tunnel. What differs is the app's own: its page URL, its dev server, its backend and the data
it seeds, and its device file. This change moves the shared part into `pihero_testkit.preview` behind a protocol an app
implements in a thin `tests/preview.py`, and the device-file rendering both apps copy into `pihero_testkit.device_file`.

Success looks like this: netmon's three targets behave as before on top of the library, busy-screen gets the same three
with a `tests/preview.py` of its own, and both previews run at the same time on one Mac, each on its board or in its
VM, with Ctrl-C leaving no QEMU, dev server, container, tunnel, `/run/<app>-preview` or drop-in behind on either side.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Shape | A library: the app implements `KioskApp` and calls `preview.main(app)` from its `tests/preview.py`; the make targets stay `python tests/preview.py --on browser\|vm\|board` | A CLI driven by configuration cannot start a Mosquitto container or seed a Node-RED flow; code can. The entry point stays where it is today, so the Makefiles do not change |
| Name | `KioskApp`, in `pihero_testkit.preview` | Not every Pi Hero app shows a page; the protocol describes one that does, and the subpackage exists only for the kiosk. The device-file rendering, which every app's tier 2 needs, is top-level as `pihero_testkit.device_file` |
| Words | The server a session starts on the Mac is the app's *fake*: the real software, seeded (Mosquitto with retained scans, Node-RED with a status). The seeded data is the *fixture*. The API's generic word is *backend*. The app's variable keeps its name (`BROKER`, `BACKEND`) and the recommended value grammar is `fake \| board \| HOST:PORT` | "Fixture" named both the server and its data. "Mock" verifies interactions, "virtual" collides with the VM, "simulated" is wrong for the real software |
| Words for the Pi | `board` is the real Raspberry Pi in every name (`--on board`, `preview-board`, the record's `board`, `board.Session`); `device` stays for device files and directories | The repository already uses the two words that way; netmon's `preview-device` and `BROKER=device` are renamed when it moves onto the library, with `device` accepted for one release |
| Reaching the Mac | The app names the Mac ports its page needs: the dev server's and, when the backend runs on the Mac, the backend's. The session forwards them per flavor and hands the app `Served.address(mac_port)`: `localhost:P` in a browser, `10.0.2.2:P` in the VM, `127.0.0.1:(10000+P)` on a board through `ssh -R` | One rule for every flavor replaces netmon's `guest_host`, `forwards` and `on_the_mac`. The board rule keeps netmon's 18080 and 18081 exactly and is deterministic, so a dead tunnel's forwards can be ended by port |
| Inspector ports | 2999 in the guest and on the board; a free port on the Mac per session, recorded, printed and opened by `INSPECT` | One kiosk per machine on the far side; two sessions on the Mac must not share the near side |
| Concurrency | Everything on the Mac is scoped by the app's name or root, or allocated: record under `root/dist/preview`, container and `/run` names by the app, inspector and VM ports free, windows placed by QEMU's pid and cascaded, layer builds and the base image build under a lock. One preview per app (Gradle allows one build per project directory) and one per board (one kiosk) | The user runs netmon and busy-screen side by side |
| Window | Placed through System Events by the QEMU process id, sized to the display plus the 32-point title bar, at an origin that moves by 40 points per other QEMU window already open | A window found by process name is ambiguous with two VMs; the sizes differ per app |
| kiosk.conf | `COG_ARGS` quoted, unquoted or absent are all handled; the session writes it quoted with `--enable-developer-extras=true` in front; `URL=` is replaced or added; the inspector and `GSETTINGS_BACKEND=memory` lines replace any present | busy-screen's sample has `COG_ARGS=--platform-params=renderer=gles` unquoted and its VM rendering drops the line; netmon's helper raised on both |
| Same program | The record stores each process as `[pid, start time]` from `ps -o lstart=`; recovery ends a process only when both still match | Exec-proof (Gradle's wrapper becomes java under the same pid) and immune to pid reuse, where netmon's substring match was a heuristic |
| Layer | `~/.cache/pihero/preview/<hash>/` with `rootfs.qcow2` and `bootfs.img`, read-only, hash of the base image's directory name and the rendered `user-data`, built in `<hash>.building` under `<hash>.lock` and renamed into place | As netmon, plus the lock: two apps with the same device file, or two runs of one app, must not build into the same directory |
| Base image lock | `prepare.prepare()` takes `~/.cache/pihero/base/<key>.lock` around the build | Two previews on a cold cache otherwise run two privileged tools containers into one output directory |
| Backend recovery | `Backend.stop()` is idempotent and works from a fresh process; the record notes that a backend was started and recovery calls `stop()` on the backend of the new run's settings | netmon's `podman stop <name>` already has this property; the protocol states it |
| booted helpers | Only what the preview needs moves (the journal wait, the kiosk.conf parser, free ports), as internals of the subpackage. The `booted.py` both apps copy is a separate change | The two copies already diverge (unit names, Node-RED's `/info`); this release's API is the preview |
| Production bundle | Out of scope. `KioskApp.dev_server()` returns a command, so an app can serve its built bundle under a variable of its own later | The flavors spec left `BUNDLE=production` out; the API must not preclude it, and does not |
| Accelerator | HVF; the preview is a Mac command | The window is a macOS window; the layer build under TCG would take an hour |
| Version | `pihero-testkit` 2.8.0, and `testkit/pyproject.toml` corrected from its stale 2.0.0 | Additive API; the apps pin by tag |

## The API

```python
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Settings:
    """What every flavor takes: the flavor, TARGET for the board, INSPECT, and the environment the app's own variables come from."""

    flavor: str  # "browser", "vm" or "board"
    target: str | None  # user@host[:port]; required by "board", refused elsewhere
    inspect: str | None  # the application INSPECT names; None for "0" or ""
    environ: Mapping[str, str]


@dataclass(frozen=True)
class DevServer:
    """The app's dev server: run in the app's root with env added to the environment, ready once port answers on 127.0.0.1."""

    argv: list[str]
    port: int
    env: dict[str, str] = field(default_factory=dict)


class Backend(Protocol):
    """The app's backend as one session sees it: a fake the session starts, the board's own, or an address given."""

    managed: bool  # whether start() starts something the session must stop
    mac_port: int | None  # the Mac port the kiosk must reach, None when the backend is not on the Mac

    def start(self) -> None: ...  # raises RuntimeError when the fake cannot start, with the reason

    def stop(self) -> None: ...  # ends the app's fake wherever a session left it; idempotent; works from a fresh process

    def describe(self) -> str: ...  # one line for the ready message, e.g. "fake on localhost:8080"


class Served(Protocol):
    """How the kiosk of this flavor reaches the Mac."""

    flavor: str

    def address(self, mac_port: int) -> str: ...  # "host:port" as the kiosk reaches the Mac's port


class KioskApp(Protocol):
    """What the preview needs from an app that shows a page in pihero-kiosk."""

    name: str  # scopes the record, the board's /run directory and drop-in; "netmon"
    root: Path  # the repository; the record lives under root/dist/preview and the dev server runs there
    display: tuple[int, int]  # the VM's display and the window's size in points; (800, 480)

    def user_data(self) -> str: ...  # the VM's device file: the sample minus what the Mac serves, with pihero-kiosk

    def dev_server(self, settings: Settings) -> DevServer: ...

    def backend(self, settings: Settings) -> Backend: ...  # parses the app's variables; raises ValueError naming the grammar

    def page_url(self, backend: Backend, served: Served) -> str: ...  # the URL the kiosk or browser loads


def main(app: KioskApp, argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int: ...
```

`main` parses `--on browser|vm|board`, builds `Settings` from `TARGET` and `INSPECT` (default `Safari`), and returns 2
with the message on `ValueError`, `RuntimeError` or `TimeoutError`, 130 on Ctrl-C. `backend()` and `dev_server()` are
called before anything starts, so a bad variable fails before the record is claimed. The ready message names the page
(`page_url` in the browser flavor, `http://localhost:<dev port>/` in the others, as netmon prints today),
`backend.describe()`, and the inspector's address.

netmon's `tests/preview.py` under this API: `name="netmon"`, `display=(800, 480)`, `user_data()` is today's
`preview_device.render` on top of `device_file`, `dev_server()` is Gradle on 8081 with `NETMON_STATS_PROXY` set for the
board flavor, `backend()` parses `BROKER` and `SCAN` into its Mosquitto container (`mac_port` 8080 for the fake and a
loopback `HOST:PORT`, `None` for `board` and a remote host), and `page_url()` is
`http://{served.address(8081)}/?broker.host=…&broker.port=…` with the broker's address from `served.address(mac_port)`,
`127.0.0.1:8080` for `board`, or the given `HOST:PORT`. busy-screen's: `(480, 320)`, Node-RED from the vendored server
directory on a Mac port with the repository's flow and a seeded status as the fake, `?address=http://{served.address(1880)}`.

## Components

All new modules are tier-0 tested; the subpackage is `testkit/src/pihero_testkit/preview/`.

- `preview/__init__.py`: the protocols above, `Settings.from_environ`, `main`, `run`. `run` sets SIGTERM to raise
  `KeyboardInterrupt`, claims the record, and on an `ExitStack` starts the backend if managed, checks the dev server's port
  is free and starts it, shows the flavor, waits for the inspector's page list to name a target (30 s, else the list's own
  address), runs `open -a INSPECT`, prints the ready message and waits for Ctrl-C, asking the flavor's `watch` every second.
- `preview/record.py`: the record `root/dist/preview/session.json` with `owner`, `dev_server`, `qemu`, `tunnel` as
  `[pid, started]`, `backend` (bool), `board` (the target), `inspector` (the Mac port); `claim()` ends what a killed
  session left (terminate, terminate the dev server's process group, restore the board, stop the backend, wait until gone)
  and raises `AlreadyRunning` next to a live owner; `update(**fields)`; `forget()` keeps only a board whose restore failed.
- `preview/process.py`: `answers(host, port)`, `info(pid) -> (started, state) | None` from `ps`, `raise_on_sigterm()`,
  `until_interrupted(watch)`, `free_port()`.
- `preview/flavors.py`: `Shown(page, inspector, watch)`, `Browser`, `Vm`, `Board`, and the `Served` implementations
  (`localhost:P`, `10.0.2.2:P`, `127.0.0.1:(10000+P)`; a Mac port above 55535 is a `ValueError`).
- `preview/kiosk.py`, pure: `session_conf(current, url, inspector_port=2999)`, `inspector_url(listing, address)`,
  `inspect_app(value)`, `open_command(app, url)`, `parse_conf(text)` (the `EnvironmentFile` parser both apps copy).
- `preview/layer.py`: `Layer(rootfs, bootfs)`, `name(base_id, user_data)`, `ensure(app, cache)` with the lock; the
  device directory is `root/dist/preview/preview-device/` holding the app's `user_data()`; the build is
  `provisioned_vm([], …, display=app.display)` followed by `poweroff`, a copy of the overlay and the bootfs image,
  `chmod 444`, `os.replace`.
- `preview/vm.py`: `Session(layer, directory, display)`: `start()` on an overlay of the layer with a window, `place_window(pid)`,
  `configure_kiosk(url)` (read, `session_conf`, `tee`, restart, journal wait for `Loaded successfully`, 90 s),
  `open_tunnel(local, 2999)`, `stop()` (`poweroff`, wait, terminate, delete the directory), `keep_serial_log()` to
  `root/dist/preview/serial.log` on failure.
- `preview/window.py`: `place(pid, size, origin)` through `osascript` and System Events, 20 attempts; `cascade_origin(n)`;
  `other_windows()` counts other `qemu-system-aarch64` processes with `-display cocoa`; a refusal prints the Accessibility
  hint once and goes on.
- `preview/board.py`: `Session(target, name)`: `check_kiosk()`, `session_conf()`, `forwards(mac_ports, inspector_local)`,
  `tunnel_command(...)` (`-N -4`, `BatchMode`, `ExitOnForwardFailure`, `ssh.KEEPALIVE`), `open_tunnel()` after ending the
  board's stale `sshd` forwards on the session's remote ports, log at `root/dist/preview/tunnel.log`, `install(conf,
  tunnel)` to `/run/<name>-preview/kiosk.conf` and `/run/systemd/system/pihero-kiosk.service.d/<name>-preview.conf`,
  `wait_loaded()`, `restore()`, `tunnel_problem()`, `close_tunnel()`.
- `preview/dev_server.py`: `start(dev_server, root, log)` in a new session with the env added, `wait_until_serving` (900 s,
  fails early if the process ends), `stop()` by process group, SIGTERM then SIGKILL after 30 s; log at
  `root/dist/preview/dev-server.log`.
- `device_file.py` (top-level): `USER`, `PUBLIC_KEY`, `block(text, start)` (netmon's variant: blank and comment lines
  inside the block belong to it, trailing ones to what follows), `with_user(text, user, key)`, `with_source(text, path,
  url=repo.URL)` (replaces the `write_files` entry at `path` with a `Trusted: yes` deb822 source at `url`), `drop(text,
  start)`, `write(directory, user_data)`.
- [prepare.py](../../../testkit/src/pihero_testkit/prepare.py): the lock around the base image build.
- [plugin.py](../../../testkit/src/pihero_testkit/plugin.py): the `preview` marker, opt-in.
- Makefile and README "Development": `make test-preview`. [testing.md](../testing.md): the target in the command lists,
  the marker in "Writing tests", the board flavor's manual check in "Real devices". [app-conventions.md](../app-conventions.md):
  a "Kiosk preview" section with the `KioskApp` contract, the make targets, the dev-server requirements (bound to
  `127.0.0.1` on a port of the app's own, `allowedHosts: 'all'`, `client.webSocketURL: 'auto://0.0.0.0:0/ws'`), the
  `fake | board | HOST:PORT` grammar, one preview per app and per board. [design.md](../design.md): a paragraph under
  "Applications" and the kiosk section's pointer to it.
- `testkit/pyproject.toml`: `version = "2.8.0"`.

## Failure modes

- Something answers on the app's dev-server port: `something already answers on port P; end it first`, nothing started.
  Two apps declaring the same port hit this; the conventions say to differ.
- The fake's port is taken: the app's `start()` raises with the app's own advice (netmon: `BROKER=localhost:8080` to attach).
- A second session of the same app: `a preview is already running (process N); end it with Ctrl-C first`.
- A killed session: the next start ends the recorded processes that still match, restores the board if it answers, stops the
  backend, deletes the session directory, then proceeds. A board that does not answer keeps its entry in the record and
  the message says a reboot removes the session's files.
- Two sessions need the same layer at once: the second waits on the lock, then finds the layer built. A build that dies
  leaves `<hash>.building`, which the next build removes first.
- macOS refuses the window placement: the hint about Accessibility is printed and the session goes on with QEMU's own
  window size; nothing else depends on it.
- The kiosk does not log `Loaded successfully` within 90 s: `TimeoutError` naming the serial log (VM) or asking whether
  the dev server and tunnel are up (board); the session ends and cleans up.
- The tunnel ends while the session runs: the watch reports the tunnel log's last line or the exit status, and the
  session ends like Ctrl-C, restoring the board.
- A Mac port above 55535 on the board: `ValueError` from the `Served` rule, before the tunnel opens.
- `INSPECT` names an application that is not installed: `open` fails, the message is printed, the session goes on.
- The dev server exits before it serves: `RuntimeError` naming its log.

## Tests

Tier 0, in `testkit/tests/test_preview*.py` and `test_device_file.py`, with a reference `KioskApp` in the tests whose
dev server is `python -m http.server` on a static page and whose backend is unmanaged with `mac_port=None`:

- `Settings.from_environ`: the flavors, `TARGET` required and refused, `INSPECT` values; `main` exits 2 with the app's
  `ValueError` and runs nothing.
- `Served.address` per flavor, the board rule and its bound.
- `session_conf` for quoted, unquoted, single-quoted and absent `COG_ARGS`, a missing `URL=`, and present inspector lines.
- `inspector_url` against a recorded listing; `parse_conf`.
- The record: `claim` raising next to a live owner, the stale actions for each recorded field, pid reuse with a different
  start time left alone, `forget` keeping a board; `info` parsing `ps` output including a zombie.
- The layer name changing with the base id and the user-data and with nothing else; `ensure` building under the lock
  (a fake builder) and skipping an existing layer; the `.building` directory removed first.
- The window: the System Events script by pid and size, the cascade origin, the count of other windows from `ps` output.
- The board: `forwards` and `tunnel_command` argument lists, the install and restore command texts for a name, the end
  of stale forwards for the session's ports, `wait_loaded` failing early on a dead tunnel, `restore` warning on an
  unreachable board.
- The dev server: the command's cwd, env and new session; `wait_until_serving` failing early; stop by process group.
- `device_file`: `block` on a sample with comments and blanks inside and after a block, `with_user` and its two
  `ValueError`s, `with_source` with the default and a given URL, `drop`, `write`.
- `prepare`: the lock file taken around the build (a fake `tools.run`).
- The kiosk's contract: the preview's constants against the package in this repository, so a change to the unit fails
  the same `make test-tier0`: the unit name and `EnvironmentFile=-/etc/pihero/kiosk.conf` read from
  `packages/pihero-kiosk/root/usr/lib/systemd/system/pihero-kiosk.service`, and the `URL` and `COG_ARGS` variables the
  kiosk script reads, loaded with `load_script`, against the keys `session_conf` writes.

The `preview` marker, Mac only (`skipif` not darwin), run by `make test-preview`: a session of the reference app on the
VM flavor keeps the guest at its display size after the window was resized and the kiosk restarted; a page served from
the Mac's loopback loads in the kiosk; the inspector's page list through the tunnel names a target; the QEMU a killed
record names is ended by the next start. The board flavor is proven by hand on an application board and recorded in
testing.md "Real devices": the page shows, a CSS edit reaches the panel, the inspector shows the DOM, Ctrl-C leaves
`/run/<app>-preview` and the drop-in gone and the kiosk on its own URL, `kill -9` and the next start recovers.

## Downstream and release

1. pihero: this spec, the plan, the implementation on `feat/kiosk-preview`, `make release VERSION=2.8.0`, push the tag,
   the checkpoints.
2. netmon and busy-screen are prepared against the unreleased API with `pihero-testkit = { git = …, subdirectory =
   "testkit", rev = "<sha>" }` and `uv lock`, then switched to `tag = "v2.8.0"`. netmon's `tests/preview*.py` shrink
   to `tests/preview.py` (the `KioskApp`), `preview_broker.py` and `scan_fixtures.py`; its `vm_device.py` and
   busy-screen's build on `device_file`. busy-screen adds `webpack.config.d/dev-server.js` on a port other than 8081,
   the three make targets, and reruns its tier 2 after the jump from v2.4.0.
3. Verification, both at once: netmon `make test-preview`, `make preview-vm`, `make preview-board TARGET=pi@netmon.local`;
   busy-screen the same against `pi@busy-screen.local`; nothing left behind on either side after Ctrl-C.

## Follow-ups

- A shared `booted` module for the journal, cloud-init status and tunnel helpers both apps copy.
- Serving a production bundle to a weak board (busy-screen's Model B, ARMv6, 512 MB, `MemoryMax=300M`).
- Whether webpack's `allowedHosts` can be narrower than `all`.
