# Application unit conventions

Apps run as systemd services installed by their own Debian package. Pi Hero packages never depend on app units.

    [Unit]
    Description=My App
    After=network-online.target
    Wants=network-online.target

    [Service]
    User=myapp
    Group=myapp
    ExecStart=/usr/lib/myapp/run
    Restart=always
    RestartSec=5
    MemoryMax=200M
    NoNewPrivileges=yes
    ProtectSystem=strict
    StateDirectory=myapp

    [Install]
    WantedBy=multi-user.target

- One dedicated system user per app, created in `postinst` with `adduser --system --group --no-create-home`; the package
  depends on `adduser`, which Trixie's minimal images no longer carry.
- `Restart=always` so a crash never leaves the device without its app; `MemoryMax=` so a leak never starves sshd.
- Hardware access through group membership (`spi`, `gpio`, `i2c`, `video`), never by running as root.
- Configuration overrides in `/etc/<app>/<app>.conf` as `KEY=VALUE`, read with `EnvironmentFile=-`.
- Tests depend on `pihero-testkit` pinned to a tag and reuse its tiers; the app's tier-2 device file adds the app's apt source to a copy of the `all-features` device. Its `URIs:` line is `http://10.0.2.2:8000/` exactly, with the trailing slash: the harness serves on a free port and points that URL at it when it stages the file.
- App test suites that reuse the testkit put `-p no:pytest11.testinfra` in their pytest `addopts`: pytest-testinfra's own plugin registers after the testkit's, and its local-host `host` fixture would shadow the target's.
- The app's apt source goes into the device file as a `write_files` entry writing a deb822 `.sources` file; cloud-init's `apt:` block is not applied on Raspberry Pi OS.
- An app that shows a page depends on `pihero-kiosk`; the device file writes `/etc/pihero/kiosk.conf` with `URL=`. The kiosk
  waits until the URL answers, so the app's units need no ordering towards it.
- An app that shows a face runs `kaomoji hero`, `kaomoji wizard`, or `kaomoji visitor` from the `kaomoji` package, which
  `pihero` brings along, and ships no copy of its own.
- `MemoryMax=` only binds once the memory controller is on: Raspberry Pi OS boots with `cgroup_disable=memory`, so a device
  file that wants the caps enforced adds `/usr/lib/pihero/bootconfig add cmdline cgroup_enable=memory` to its `runcmd`.
- Measure memory with swap: Raspberry Pi OS Trixie swaps into a zram device (`rpi-swap`), so `free -m`'s Swap line and
  `systemctl show -p MemorySwapPeak` belong to every figure, and `MemoryMax=` bounds RAM only. A cap below the working set
  makes the board thrash rather than the unit shrink; on a Zero 2 W the hardware watchdog then resets it.

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
