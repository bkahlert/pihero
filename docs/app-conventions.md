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

- One dedicated system user per app, created in `postinst` with `adduser --system --group --no-create-home`.
- `Restart=always` so a crash never leaves the device without its app; `MemoryMax=` so a leak never starves sshd.
- Hardware access through group membership (`spi`, `gpio`, `i2c`, `video`), never by running as root.
- Configuration overrides in `/etc/<app>/<app>.conf` as `KEY=VALUE`, read with `EnvironmentFile=-`.
- Tests depend on `pihero-testkit` pinned to a tag and reuse its tiers; the app's tier-2 device file adds the app's apt source to a copy of the `all-features` device.
- App test suites that reuse the testkit put `-p no:pytest11.testinfra` in their pytest `addopts`: pytest-testinfra's own plugin registers after the testkit's, and its local-host `host` fixture would shadow the target's.
- The app's apt source goes into the device file as a `write_files` entry writing a deb822 `.sources` file; cloud-init's `apt:` block is not applied on Raspberry Pi OS.
- An app that shows a page depends on `pihero-kiosk`; the device file writes `/etc/pihero/kiosk.conf` with `URL=`. The kiosk
  waits until the URL answers, so the app's units need no ordering towards it.
- `MemoryMax=` only binds once the memory controller is on: Raspberry Pi OS boots with `cgroup_disable=memory`, so a device
  file that wants the caps enforced adds `/usr/lib/pihero/bootconfig add cmdline cgroup_enable=memory` to its `runcmd`.
