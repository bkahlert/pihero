# Spike: tier-1 podman systemd containers

Host: podman 6.1.2, `podman-machine-default` (applehv, rootful, Fedora CoreOS 44, kernel 7.1.10, SELinux enforcing), uv 0.12.19.

## arm/v7 works

Partly. Plain arm/v7 containers print `armv7l`, but systemd-as-PID-1 arm/v7 containers boot `degraded` and are not usable (see below).
Out of the box: `Exec format error`, because the machine has no `qemu-arm` binfmt entry (Fedora ships none on aarch64 hosts). `rpm-ostree install qemu-user-static` fails: `rpm-ostreed` cannot start because `/etc/containers` is a virtiofs mount from the Mac without `policy.json`. `tonistiigi/binfmt --install arm` registers the handler, but containers then exit 139.
What worked: copy Fedora's `qemu-arm-static` (qemu 10.2.2) to `/usr/local/bin`, `chcon -t container_ro_file_t` it, then register it with flag `F` via `/etc/binfmt.d/qemu-arm-static.conf` and `sudo /usr/lib/systemd/systemd-binfmt`. The label is required because `--systemd=always` containers run as `container_init_t`, which is denied `map` on `bin_t`. After a machine restart, `systemd-binfmt.service` fails (`init_t` denied `execute` on `container_ro_file_t`), so the registration must be rerun after every machine start.

## systemd container state

arm64: `running`, `0 loaded units listed.` under `systemctl --failed`.
arm/v7: `degraded`, 15 failed units, all `status=1/FAILURE`: dbus, ldconfig, systemd-journald (+ both journald sockets), systemd-journal-catalog-update, systemd-journal-flush, systemd-logind, systemd-remount-fs, systemd-sysusers, systemd-tmpfiles-setup(-dev, -dev-early), systemd-update-done, systemd-user-sessions. The same commands succeed through `podman exec`, so only processes spawned by systemd fail.
`sudo`: absent on both (`no-sudo`). The base image ships `/usr/sbin/policy-rc.d` (`exit 101`), so `apt-get install` does not start services. On arm64 avahi-daemon was started later by socket activation.

## RuntimeWatchdogUSec in a container

`RuntimeWatchdogUSec=0` on both arm64 and arm/v7.

## avahi-browse inside a container

arm64: `avahi-browse -rpt _workstation._tcp` printed nothing (exit 0), because Debian ships `publish-workstation=no`. A record published inside the container with `avahi-publish -s spiketest _http._tcp 8080` was resolved on `eth0` IPv4 (`10.88.0.4`), `eth0` IPv6 and `lo`.
Interfaces: `lo` (LOOPBACK) and `eth0@ifN` (`BROADCAST,MULTICAST,UP,LOWER_UP`).
arm/v7: `Failed to create client object: Daemon not running`, because avahi-daemon is `inactive` without dbus.

## testinfra podman backend

Works. The brief's `uvx --from pytest-testinfra --with pytest python -c ...` command ran verbatim (Python 3.14.4, pytest-testinfra 10.2.2).
arm64 printed `True True`. arm/v7 printed `True False`.

## Decisions for Task 8

Masked units: none beyond the brief's list (arm64 has 0 failed units). Add `rm -f /usr/sbin/policy-rc.d` to the Containerfile so package postinsts start services. Build with `--format docker`, otherwise podman warns `HEALTHCHECK is not supported for OCI image format and will be ignored`. Install `sudo` in the image, since it is absent.
`PODMAN` prefix: plain `podman`, no `sudo`. The machine is rootful and the Mac client already talks to it as root.
avahi-browse: records are visible inside an arm64 container, so browse tests can run in tier 1 if they publish their own record or enable `publish-workstation`. systemd tests for arm/v7 must run in tier 2: tier-1 arm/v7 systemd containers are degraded.
