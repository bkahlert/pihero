# `cog`: Pi Hero's own build of the kiosk browser, with the SHM export fix

Date: 2026-10-01. Status: approved design, ready for planning.

## Intent

The kiosk cannot be seen anywhere but on a board. Tier 2 boots the real Raspberry Pi OS root filesystem in QEMU, but the
VM has no display adapter, so `pihero-kiosk.service` is skipped by its condition and nothing proves that cog paints the
page an application serves, or what the kiosk costs in memory. A spike on 2026-10-01 (netmon, spike B) gave the VM a
`virtio-gpu-pci` device at 800×480: the guest gets `/dev/dri/card0`, the connector reports the mode, the unit starts,
cog picks the mode and WPE WebKit loads the page. Then cog segfaults, on every start, five seconds apart.

The cause is cog's, not the VM's. macOS QEMU has no virgl, so the web process's Mesa falls back to software rendering
and hands cog its frames as `wl_shm` buffers. cog 0.18.4's DRM modeset renderer stores its own pointer in the SHM
buffer resource's user data, which libwayland uses for the `wl_shm_buffer` itself; the second attach of the same buffer,
the third frame, gives cog garbage and it crashes in the copy
([Igalia/cog#742](https://github.com/Igalia/cog/issues/742)). Debian ships 0.18.4-1 in trixie and 0.18.5-1 in testing,
neither with a fix; the fix exists only in the open pull request [Igalia/cog#794](https://github.com/Igalia/cog/pull/794).
With its two relevant hunks built into the DRM module, the kiosk in the spike's VM ran for minutes without a restart,
painted the Netmon page, and its cgroup held 249 MB. A board never reaches this code: its web process renders on the GPU
and exports dmabufs.

This ships cog with that fix from Pi Hero's own apt repository, the one place every device and every tier 2 VM already
gets its packages from. It is the prerequisite for the virtual GPU in the testkit, which follows in its own design.

Success looks like this: `make build` produces `cog_0.18.4-1+pihero1_arm64.deb` next to the other packages, in about
three minutes once and in no time afterwards; tier 1 on arm64 installs it and asserts the version, tier 1 on armhf is
untouched; `make release` publishes it; a 64-bit board takes it on its next `apt upgrade` and behaves as before; and with
the virtual GPU, the kiosk runs in the VM.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| What is shipped | Debian's `cog` source package 0.18.4-1 rebuilt under the same name as `0.18.4-1+pihero1` | apt takes the highest version from any source of equal priority, so a device gets it with `apt upgrade` and nothing else changes; `+pihero1` sorts above Debian's `+b1` and below a future `0.18.4-2`; a different name would need `Conflicts`, `Replaces`, `Provides` and a changed `pihero-kiosk` dependency |
| The fix | The two hunks of [Igalia/cog#794](https://github.com/Igalia/cog/pull/794) that matter: the renderer pointer kept in cog's own buffer record instead of the resource's user data, and the client's SHM buffer released right after the copy | The minimal change the spike proved; the rest of the pull request (cursor support, cold start) is unrelated and untested here |
| Base version | trixie's 0.18.4-1, not testing's 0.18.5-1 | The boards run 0.18.4; 0.18.5's two changes (a scaling factor fix, key repeat) are not needed; a DEP-3 patch on Debian's source keeps the difference to Debian one file |
| Architecture | arm64 only | The VM and the 64-bit boards are arm64. The 32-bit boards keep Debian's cog: their web process takes the dmabuf path and never hits the bug, and the Mac cannot build armhf (no `qemu-arm` binfmt in the podman machine, see [testing.md](../../testing.md#tier-1)) |
| Build | `dpkg-buildpackage` in a dedicated image from `packages/cog/Containerfile`: `debian:trixie-slim` at the tools image's digest plus cog's Build-Depends, always built for `linux/arm64` | The tools image stays small; the x86 weekly runner already runs arm64 containers through binfmt and builds this one the same slow way |
| How the testkit finds it | A package directory with an executable `build` next to a `Containerfile` builds itself: the testkit builds the image, runs `/work/packages/<name>/build` in it with the repository mounted at `/work`, and reads the `.deb` paths the script prints | A generic contract; everything cog-specific stays under `packages/cog/`. nfpm packages are discovered as before |
| Caching | The script returns at once, printing the path, when `dist/cog_0.18.4-1+pihero1_arm64.deb` exists | The Debian version is the cache key; `make clean` rebuilds; a changed patch bumps `+pihero1` to `+pihero2` |
| Sources | The `.dsc`, `.orig.tar.xz` and `.debian.tar.xz` of 0.18.4-1 from the Debian pool, pinned by sha256 in the script | Reproducible, as [images.lock](../../../testkit/src/pihero_testkit/images.lock) pins the OS images |
| `pihero-kiosk` | `Depends: cog`, unversioned, unchanged | A version constraint would make the package uninstallable on armhf |
| Architecture-specific debs on the targets | Tier 1 installs `_all` debs and those of the container's architecture; `deploy` sends `_all` debs and those of the target's architecture; the VM's apt picks by architecture itself from the local repository | Today every built deb goes into one `apt install`; an arm64 deb in the armhf container would fail the install |
| Repository index | `Architectures: all arm64` in the `Release` file | The field names what the flat repository carries |
| Proof | Tier 0 for the testkit's new logic; tier 1 on arm64 asserts `cog` is `0.18.4-1+pihero1`, on armhf that it is installed; the kiosk itself is proven in tier 2 once the VM has a GPU | The crash needs a display adapter to show; that is the next design |
| Release | 2.4.0, together with the virtual GPU | One release carries the fix and the means to see it |

## Package anatomy

```
packages/cog/
  Containerfile                 # debian:trixie-slim (the tools image's digest), build-essential, fakeroot, debhelper, cog's Build-Depends; HEALTHCHECK NONE
  build                         # bash: pinned sources, dpkg-source -x, the patch into debian/patches, a changelog entry, dpkg-buildpackage -b -uc -us, the .deb into /work/dist
  patches/
    0001-drm-keep-the-renderer-out-of-the-shm-buffer-resource.patch   # DEP-3 headers: Origin, Bug, Forwarded
  tests/test_installed.py       # tiers 1, 2, and ssh
```

The directory has no `nfpm.yaml`, no `root/`, no `units.txt`: the Debian packaging in the `.debian.tar.xz` is the manifest
and the maintainer scripts. The tier 0 checks that iterate nfpm packages (`arch: all`, `section: admin`, `adduser`) do not
apply to it; shellcheck covers `build` as it covers every shell file under `packages/`.

### The build script

`build --dist <directory>` runs inside the image. It downloads the source files into a temporary directory of the
container, checks their sha256 against the pinned values, unpacks with `dpkg-source -x`, copies the patch into
`debian/patches/` and appends its name to `series`, prepends a `debian/changelog` entry for `0.18.4-1+pihero1` naming the
fix, runs `dpkg-buildpackage -b -uc -us`, moves the resulting `.deb` into the directory given and prints its path. When
the `.deb` already exists it prints the path and exits. The build tree stays off the bind mount on purpose: the Mac's
filesystem, mounted into the podman machine, refuses the symlinks the source tarball carries. A failed download, a
checksum mismatch, a patch that does not apply, or a failed build exit non-zero with dpkg's output; nothing is retried.

### The testkit

- [tools.py](../../../testkit/src/pihero_testkit/tools.py): `image()` and `ensure_image()` take the Containerfile and the
  platform, defaulting to the tools image and the host platform; the tag is `localhost/pihero-<directory name>:<digest>`,
  so the tools image keeps its tag. `run()` takes the image.
- [build.py](../../../testkit/src/pihero_testkit/build.py): `discover()` also yields directories with `build` and
  `Containerfile`; `build()` dispatches on which of the two a directory has and returns the paths. `build_all()` keeps its
  signature; its callers, the plugin, `deploy`, `vm` and `make build`, change nothing.
- [podman.py](../../../testkit/src/pihero_testkit/podman.py): `install()` and `reinstall()` pass only the debs
  `installable()` keeps for the platform, by the architecture in the file name.
- [deploy.py](../../../testkit/src/pihero_testkit/deploy.py): the status query also reports `dpkg --print-architecture`;
  `select()` keeps `_all` debs and the target's architecture.
- [repo.py](../../../testkit/src/pihero_testkit/repo.py): `release_options()` writes `Architectures=all arm64`.

### Documentation

[design.md](../../design.md) gets `cog/` in the repository layout, a row in the decisions table, and a paragraph in the
`pihero-kiosk` section saying why Pi Hero carries cog and until when. [testing.md](../../testing.md) gets the second image
and the architecture filter. The README's package table gets a `cog` row.

## Failure modes

- The pinned source files leave the Debian pool: stable keeps them until a point release replaces the package; the build
  then fails on the download with the URL in its message, and the pins move to the new files or to snapshot.debian.org.
- A Build-Depends drifts in trixie: the image build fails; the base image is pinned by digest, which limits that to apt's
  own index.
- apt in the VM rejects the index because of the `Architectures` field: tier 2 shows it on the first run after this
  change; the fix is in `release_options`.
- The armhf tier 1 container: the cog deb is filtered out, `pihero-kiosk` pulls Debian's cog as it does today.
- The weekly x86 run: the cog build under binfmt takes minutes longer; the job's budget is three hours.

## Follow-ups, in order

1. **The virtual GPU in the testkit** (its own design): `virtio-gpu-pci,xres=800,yres=480`, a QMP TCP port (a UNIX socket
   path exceeds 104 bytes under a scratch directory), `Vm.screenshot(path)`, and a `pihero-kiosk` tier 2 test that the
   unit is active with `NRestarts=0` after the first frames. Then `make release VERSION=2.4.0`.
2. **The applications**: netmon bumps its pin, adds the kiosk boot test and the screendump; busy-screen bumps its pin and
   renders its sample for the VM without `COG_ARGS=--platform-params=renderer=gles`, the `panel.conf` drop-in and the
   `fbcon=map:1` line, since cog's gles renderer has no SHM path
   ([Igalia/cog#722](https://github.com/Igalia/cog/issues/722)) and the VM has one virtual card.
3. **Upstream**: the spike's finding goes to [Igalia/cog#794](https://github.com/Igalia/cog/pull/794) as a comment; the
   package is dropped when Debian ships a cog whose SHM path works.
