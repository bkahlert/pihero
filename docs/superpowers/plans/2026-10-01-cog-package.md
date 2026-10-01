# `cog` Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `make build` produces `cog_0.18.4-1+pihero1_arm64.deb`, Debian's cog 0.18.4-1 rebuilt with the DRM SHM export fix, next to the other packages, and the targets install it only where it fits.

**Architecture:** The testkit learns one new package shape: a directory with an executable `build` next to a `Containerfile` builds itself inside the image built from that file, and the testkit takes the `.deb` paths the script prints. `packages/cog/` is the first such package: its script fetches Debian's pinned source files, adds a DEP-3 patch and a changelog entry, and runs `dpkg-buildpackage`. Because the result is architecture-specific, the tier 1 container and `deploy` install only debs that match their architecture, and the repository's `Release` file names `arm64`.

**Tech Stack:** Python 3.13 (uv), pytest with pytest-testinfra, podman, Debian packaging (`dpkg-source`, `dpkg-buildpackage`, debhelper 13, meson), bash.

**Spec:** [docs/superpowers/specs/2026-10-01-cog-package-design.md](../specs/2026-10-01-cog-package-design.md)

## Global Constraints

- Branch `feat/cog-package` in the pihero repository, already created. Never commit on `main`.
- The package is Debian's source package `cog` 0.18.4-1 rebuilt as version `0.18.4-1+pihero1` for `arm64` only. The source files and their sha256 are pinned in the build script: `cog_0.18.4-1.dsc` `d3e583c063584067dc0f65b4c4b6e8b953df8f2f93fde44a3abc88832402a399`, `cog_0.18.4.orig.tar.xz` `31d7079db2eeed790899d2f1f824dd6a54bf30d072d196d737be572f105d99b1`, `cog_0.18.4.orig.tar.xz.asc` `f578744a2d6aa6a9643c9ecfb9c98fe97e9a4011c5ba1eee188f7ade3c5c1e5a`, `cog_0.18.4-1.debian.tar.xz` `5ffe778db83fe92327694c1baaa90ab3cb2db2bc0c9a4661b2a07ae890281e40`, all from `http://deb.debian.org/debian/pool/main/c/cog/`.
- The build image's base is the tools image's: `docker.io/library/debian:trixie-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a`. Every Containerfile declares `HEALTHCHECK NONE` with a one-line reason (`~/.config/agents/rules/docker.md`).
- The build script is bash under the Google style guide with the header, `usage`, `die` and `while`/`case` parsing of `~/.config/agents/rules/bash.md`; it must pass shellcheck. It writes only the `.deb` path to stdout.
- `pihero-kiosk` keeps `Depends: cog` unversioned.
- Tests: one class per subject, names are claims, tests first and helpers last, result stored before asserting, no comments or docstrings in tests (`~/.config/agents/rules/testing.md`). Regular expressions use named or non-capturing groups only.
- Commits: Conventional Commits with the Angular types, scope `testkit` or `cog`, lowercase imperative description, header at most 72 characters, no AI-attribution trailers. One change per commit. Gate every commit on `uv run --frozen pytest -m tier0 -q` being green.
- With the JetBrains MCP connected, run `mcp__idea__get_file_problems` with `errorsOnly: false` on every file a task changed; fix or explain each finding. If the pihero project is not open in the IDE, say so.
- Commands run from the pihero repository root (`/Users/bkahlert/Development/com.bkahlert/pihero`). `make build`, tier 1 and tier 2 need the podman machine running; one tier 1 or tier 2 run at a time, in the foreground or as a watched background task.
- Documentation prose follows `~/.config/agents/rules/documentation.md` and `~/.config/agents/rules/markdown.md`: file references are links, comments only for what the code cannot say.

## Review Focus

1. The armhf tier 1 container must never be handed the arm64 cog deb; apt would fail the whole install. Pinned in Task 3, `TestInstallable.test_keeps_architecture_independent_debs_and_the_platforms_own`.
2. `make deploy` to a 32-bit board that has Debian's cog must not send the arm64 deb. Pinned in Task 3, `TestSelect.test_leaves_out_debs_built_for_another_architecture`.
3. A build script that builds nothing or prints nothing must fail the build, not return an empty list that every later step accepts. Pinned in Task 2, `TestBuildScript.test_fails_on_a_script_that_prints_no_deb`.
4. The cog build must not run again while its deb exists, or every tier 1 and tier 2 run pays three minutes. Pinned in Task 4, `TestBuildScript.test_reuses_a_deb_that_exists`.
5. apt in the VM must accept the flat repository with `Architectures: all arm64` and prefer Pi Hero's cog over Debian's. Pinned in Task 6 by `packages/cog/tests/test_installed.py` passing under `--target=vm`.

---

### Task 1: The tools module builds and runs images from any Containerfile

**Files:**
- Modify: `testkit/src/pihero_testkit/tools.py`
- Create: `testkit/tests/test_tools.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `tools.image(containerfile: Path = CONTAINERFILE) -> str` returning `localhost/pihero-<containerfile.parent.name>:<first 12 hex digits of the sha256 of the file>`; `tools.ensure_image(containerfile: Path = CONTAINERFILE, platform: str = HOST_PLATFORM) -> str`; `tools.command(args: list[str], *, workdir: str = "/work", env: dict[str, str] | None = None, privileged: bool = False, mounts: list[str] = (), image: str | None = None) -> list[str]` returning the podman command line; `tools.run(...)` gains `image: str | None = None`. The tools image keeps its tag `localhost/pihero-tools:<digest>`.

- [ ] **Step 1: Write the failing tests**

Create `testkit/tests/test_tools.py`:

```python
import hashlib
from pathlib import Path

import pytest

from pihero_testkit import tools

pytestmark = pytest.mark.tier0


class TestImage:
    def test_names_the_tools_image_as_before(self):
        tag = tools.image()

        assert tag == f"localhost/pihero-tools:{hashlib.sha256(tools.CONTAINERFILE.read_bytes()).hexdigest()[:12]}"

    def test_names_another_image_after_its_directory(self, tmp_path):
        containerfile = containerfile_in(tmp_path / "cog", "FROM scratch\n")

        tag = tools.image(containerfile)

        assert tag.startswith("localhost/pihero-cog:")

    def test_changes_with_the_content(self, tmp_path):
        containerfile = containerfile_in(tmp_path / "cog", "FROM scratch\n")
        before = tools.image(containerfile)
        containerfile.write_text("FROM scratch\n# probe\n")

        after = tools.image(containerfile)

        assert after != before


class TestCommand:
    def test_mounts_the_repository_and_ends_with_the_image_and_the_arguments(self):
        command = tools.command(["sh", "-c", "true"], image="localhost/probe:1")

        assert command[: len(tools.PODMAN)] == tools.PODMAN
        assert f"{Path.cwd()}:/work" in command
        assert command[-4:] == ["localhost/probe:1", "sh", "-c", "true"]

    def test_passes_workdir_environment_and_mounts(self):
        command = tools.command(["true"], workdir="/work/packages/cog", env={"A": "1"}, mounts=["/x:/y:ro"], image="localhost/probe:1")

        assert command[command.index("-w") + 1] == "/work/packages/cog"
        assert "A=1" in command
        assert "/x:/y:ro" in command


def containerfile_in(directory: Path, content: str) -> Path:
    directory.mkdir()
    containerfile = directory / "Containerfile"
    containerfile.write_text(content)
    return containerfile
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_tools.py -q`
Expected: `TestImage.test_names_another_image_after_its_directory` fails with `TypeError: image() takes 0 positional arguments`, `TestCommand` fails with `AttributeError: module 'pihero_testkit.tools' has no attribute 'command'`.

- [ ] **Step 3: Implement**

Replace `image`, `ensure_image` and `run` in `testkit/src/pihero_testkit/tools.py` with:

```python
def image(containerfile: Path = CONTAINERFILE) -> str:
    digest = hashlib.sha256(containerfile.read_bytes()).hexdigest()[:12]
    return f"localhost/pihero-{containerfile.parent.name}:{digest}"


def ensure_image(containerfile: Path = CONTAINERFILE, platform: str = HOST_PLATFORM) -> str:
    tag = image(containerfile)
    exists = subprocess.run([*PODMAN, "image", "exists", tag], check=False)
    if exists.returncode != 0:
        subprocess.run(
            [*PODMAN, "build", "--platform", platform, "-t", tag, "-f", str(containerfile), str(containerfile.parent)],
            check=True,
        )
    return tag


def command(
    args: list[str],
    *,
    workdir: str = "/work",
    env: dict[str, str] | None = None,
    privileged: bool = False,
    mounts: list[str] = (),
    image: str | None = None,
) -> list[str]:
    """Returns the podman command running `args` in `image`, the tools image by default, with the repository mounted at /work."""
    cmd = [*PODMAN, "run", "--rm", "-v", f"{Path.cwd()}:/work", "-w", workdir]
    for mount in mounts:
        cmd += ["-v", mount]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    if privileged:
        # podman populates /dev once at container start, so without a live bind mount
        # `losetup --partscan` never sees the loop and partition nodes it creates (tier-2 spike finding).
        cmd += ["--privileged", "-v", "/dev:/dev"]
    cmd += [image or ensure_image(), *args]
    return cmd


def run(
    args: list[str],
    *,
    workdir: str = "/work",
    env: dict[str, str] | None = None,
    privileged: bool = False,
    check: bool = True,
    capture: bool = False,
    mounts: list[str] = (),
    image: str | None = None,
) -> subprocess.CompletedProcess:
    cmd = command(args, workdir=workdir, env=env, privileged=privileged, mounts=mounts, image=image)
    return subprocess.run(cmd, check=check, text=True, capture_output=capture)
```

The module docstring becomes: `"""Runs commands in pinned container images, the tools image by default, building an image on first use."""`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_tools.py testkit/tests/test_build.py -q`
Expected: all pass (the existing build test still runs in the tools image).

- [ ] **Step 5: Inspections and commit**

Run `mcp__idea__get_file_problems` on both files.

```bash
git add testkit/src/pihero_testkit/tools.py testkit/tests/test_tools.py
git commit -m "feat(testkit): build and run images from any containerfile"
```

---

### Task 2: A package directory with a build script builds itself

**Files:**
- Modify: `testkit/src/pihero_testkit/build.py`
- Test: `testkit/tests/test_build.py`

**Interfaces:**
- Consumes: `tools.ensure_image(containerfile, platform)`, `tools.command(args, image=...)` from Task 1.
- Produces: `build.TARGET_PLATFORM = "linux/arm64"`; `build.discover() -> list[Path]` yielding directories with `nfpm.yaml` or with both `build` and `Containerfile`; `build.build_script(pkg_dir: Path, dist: Path = DIST) -> list[Path]`; `build.build_all(version, dist=DIST) -> list[Path]` dispatching per directory. The script contract: the testkit runs `/work/packages/<name>/build --dist /work/<dist relative to the repository>` in the image from the directory's Containerfile, built for `TARGET_PLATFORM`; the script prints the absolute container path of each `.deb` it produced, one per line, and nothing else on stdout.

- [ ] **Step 1: Write the failing tests**

Add to `testkit/tests/test_build.py` after `TestBuild` (keep the existing imports; add `from pihero_testkit import build, tools` if `tools` is missing, it is already imported there):

```python
class TestDiscover:
    def test_finds_manifests_and_build_scripts_but_not_plain_directories(self, tmp_path, monkeypatch):
        (tmp_path / "a-nfpm").mkdir()
        (tmp_path / "a-nfpm" / "nfpm.yaml").write_text("name: a\n")
        (tmp_path / "b-script").mkdir()
        (tmp_path / "b-script" / "build").write_text("#!/bin/sh\n")
        (tmp_path / "b-script" / "Containerfile").write_text("FROM scratch\n")
        (tmp_path / "c-plain").mkdir()
        (tmp_path / "c-plain" / "README.md").write_text("")
        monkeypatch.setattr(build, "PACKAGES", tmp_path)

        found = build.discover()

        assert [p.name for p in found] == ["a-nfpm", "b-script"]


class TestBuildScript:
    def test_runs_the_script_in_its_image_and_returns_the_debs_it_prints(self):
        pkg, dist = probe_script('deb="$1/pihero-zz-probe_9.9.9_arm64.deb"\n: > "$deb"\nprintf "%s\\n" "$deb"\n')
        try:
            debs = build.build_script(pkg, dist=dist)

            assert debs == [dist / "pihero-zz-probe_9.9.9_arm64.deb"]
            assert debs[0].exists()
        finally:
            remove_probe(pkg)

    def test_fails_on_a_script_that_prints_no_deb(self):
        pkg, dist = probe_script('echo building >&2\n')
        try:
            with pytest.raises(RuntimeError, match="pihero-zz-probe"):
                build.build_script(pkg, dist=dist)
        finally:
            remove_probe(pkg)


def probe_script(body: str) -> tuple[Path, Path]:
    pkg = Path("dist") / "probe" / "src" / "pihero-zz-probe"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "Containerfile").write_text(f"FROM {tools.ensure_image()}\nHEALTHCHECK NONE\n")
    script = pkg / "build"
    script.write_text('#!/bin/sh\nset -e\n[ "$1" = --dist ] && shift\n' + body)
    script.chmod(0o755)
    return pkg, Path.cwd() / "dist" / "probe"


def remove_probe(pkg: Path) -> None:
    subprocess.run([*tools.PODMAN, "rmi", "-f", tools.image(pkg / "Containerfile")], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["rm", "-rf", "dist/probe"], check=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_build.py -q`
Expected: `TestDiscover` fails (`b-script` missing from the list), `TestBuildScript` fails with `AttributeError: module 'pihero_testkit.build' has no attribute 'build_script'`.

- [ ] **Step 3: Implement**

In `testkit/src/pihero_testkit/build.py`, after `DIST = Path.cwd() / "dist"` add:

```python
# The devices' architecture; a package that builds itself builds for it, whatever the host is.
TARGET_PLATFORM = "linux/arm64"
```

Replace `discover` and `build_all` with, and add `build_script` between `build` and `build_all`:

```python
def discover() -> list[Path]:
    return sorted(p for p in PACKAGES.iterdir() if (p / "nfpm.yaml").exists() or ((p / "build").exists() and (p / "Containerfile").exists()))


def build_script(pkg_dir: Path, dist: Path = DIST) -> list[Path]:
    """Runs the package directory's build script in the image from its Containerfile; returns the debs the script printed."""
    pkg_dir = pkg_dir.resolve()
    dist = dist.resolve()
    dist.mkdir(parents=True, exist_ok=True)
    image = tools.ensure_image(pkg_dir / "Containerfile", TARGET_PLATFORM)
    script = f"/work/{pkg_dir.relative_to(Path.cwd())}/build"
    # Only the deb paths come through stdout; the build's own output stays on the terminal.
    result = subprocess.run(tools.command([script, "--dist", f"/work/{dist.relative_to(Path.cwd())}"], image=image), check=True, text=True, stdout=subprocess.PIPE)
    debs = [Path.cwd() / line.removeprefix("/work/") for line in result.stdout.splitlines() if line.startswith("/work/")]
    if not debs:
        raise RuntimeError(f"{pkg_dir.name}: the build script printed no .deb path")
    return debs


def build_all(version: str, dist: Path = DIST) -> list[Path]:
    debs = []
    for pkg_dir in discover():
        if (pkg_dir / "nfpm.yaml").exists():
            debs.append(build(pkg_dir, version, dist))
        else:
            debs.extend(build_script(pkg_dir, dist))
    return debs
```

Update the module docstring to: `"""Builds every package under packages/ into dist/: nfpm manifests in the tools container, build scripts in their own image."""`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_build.py -q`
Expected: all pass. `podman images | grep pihero-pihero-zz-probe` lists nothing afterwards.

- [ ] **Step 5: Inspections and commit**

Run `mcp__idea__get_file_problems` on both files.

```bash
git add testkit/src/pihero_testkit/build.py testkit/tests/test_build.py
git commit -m "feat(testkit): build a package from its own build script"
```

---

### Task 3: Architecture-specific debs reach only matching targets

**Files:**
- Modify: `testkit/src/pihero_testkit/podman.py` (`install`, `reinstall`)
- Modify: `testkit/src/pihero_testkit/deploy.py` (`STATUS_QUERY`, `select`, `main`)
- Modify: `testkit/src/pihero_testkit/repo.py` (`release_options`)
- Test: `testkit/tests/test_podman.py`, `testkit/tests/test_deploy.py`, `testkit/tests/test_repo.py`

**Interfaces:**
- Consumes: `podman.ARCHITECTURES` (exists: `{"linux/arm64": "arm64", "linux/arm/v7": "armhf"}`).
- Produces: `podman.installable(debs: list[Path], platform: str) -> list[Path]`; `deploy.architecture(status: str) -> str`; `deploy.select(debs: list[Path], names: set[str], architecture: str) -> list[Path]`; `deploy.STATUS_QUERY` whose first output line is `dpkg --print-architecture`; `repo.release_options(..., architectures: str = "all arm64")`.

- [ ] **Step 1: Write the failing podman tests**

Add to `testkit/tests/test_podman.py` after `TestImageTag` (add `from pathlib import Path` to the imports):

```python
class TestInstallable:
    def test_keeps_architecture_independent_debs_and_the_platforms_own(self):
        debs = [Path("dist/pihero_2.4.0_all.deb"), Path("dist/cog_0.18.4-1+pihero1_arm64.deb"), Path("dist/cog_0.18.4-1+pihero1_armhf.deb")]

        kept = podman.installable(debs, "linux/arm/v7")

        assert kept == [debs[0], debs[2]]

    def test_keeps_the_arm64_deb_on_arm64(self):
        debs = [Path("dist/cog_0.18.4-1+pihero1_arm64.deb")]

        kept = podman.installable(debs, "linux/arm64")

        assert kept == debs
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_podman.py -q`
Expected: `AttributeError: module 'pihero_testkit.podman' has no attribute 'installable'`.

- [ ] **Step 3: Implement the podman filter**

In `testkit/src/pihero_testkit/podman.py`, after `ARCHITECTURES` add:

```python
def installable(debs: list[Path], platform: str) -> list[Path]:
    """The debs apt can install on the platform: architecture-independent ones and those built for its architecture."""
    architectures = {"all", ARCHITECTURES[platform]}
    return [deb for deb in debs if deb.stem.rsplit("_", 1)[1] in architectures]
```

Change `install` and `reinstall` of `SystemdContainer`:

```python
class SystemdContainer:
    def install(self, debs: list[Path]) -> None:
        self._apt("update")
        self._apt("install", *[f"/dist/{deb.name}" for deb in installable(debs, self.platform)])

    def reinstall(self) -> None:
        self._apt("install", "--reinstall", *[f"/dist/{deb.name}" for deb in installable(self.debs, self.platform)])
```

- [ ] **Step 4: Run the podman tests**

Run: `uv run --frozen pytest testkit/tests/test_podman.py -q`
Expected: pass.

- [ ] **Step 5: Write the failing deploy tests**

In `testkit/tests/test_deploy.py` change the fixtures at the top to:

```python
STATUS = "arm64\nbash ii \nkaomoji ii \npihero ii \npihero-avahi ii \npihero-usb-gadget rc \npihero-kiosk iF \n"
DEBS = [Path(f"dist/{name}_2.3.0_all.deb") for name in ["kaomoji", "pihero", "pihero-avahi", "pihero-kiosk", "pihero-usb-gadget"]]
COG = Path("dist/cog_0.18.4-1+pihero1_arm64.deb")
```

Add after `TestInstalled`:

```python
class TestArchitecture:
    def test_is_the_first_line_of_the_status(self):
        architecture = deploy.architecture(STATUS)

        assert architecture == "arm64"
```

Change `TestSelect` to:

```python
class TestSelect:
    def test_keeps_the_debs_of_installed_packages_in_build_order(self):
        debs = deploy.select(DEBS, {"pihero-avahi", "pihero", "kaomoji"}, "arm64")

        assert debs == DEBS[:3]

    def test_tells_a_package_from_the_siblings_sharing_its_prefix(self):
        debs = deploy.select(DEBS, {"pihero"}, "arm64")

        assert debs == [DEBS[1]]

    def test_keeps_a_deb_built_for_the_targets_architecture(self):
        debs = deploy.select([*DEBS, COG], {"pihero", "cog"}, "arm64")

        assert debs == [DEBS[1], COG]

    def test_leaves_out_debs_built_for_another_architecture(self):
        debs = deploy.select([*DEBS, COG], {"pihero", "cog"}, "armhf")

        assert debs == [DEBS[1]]
```

In `TestMain.test_copies_and_reinstalls_only_the_packages_the_target_has` add the assertion `assert "dpkg --print-architecture" in calls[0][2]` after the existing `dpkg-query` one. In `test_exits_2_on_a_target_with_none_of_the_packages` change the status to `"arm64\nbash ii \n"`.

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_deploy.py -q`
Expected: `TestArchitecture` fails with `AttributeError`, `TestSelect` fails with `TypeError: select() takes 2 positional arguments but 3 were given`.

- [ ] **Step 7: Implement deploy**

In `testkit/src/pihero_testkit/deploy.py`:

```python
STATUS_QUERY = "dpkg --print-architecture && dpkg-query -W -f '${Package} ${db:Status-Abbrev}\\n'"
```

```python
def architecture(status: str) -> str:
    return status.splitlines()[0].strip() if status.strip() else ""


def select(debs: list[Path], names: set[str], architecture: str) -> list[Path]:
    return [deb for deb in debs if deb.name.split("_")[0] in names and deb.stem.rsplit("_", 1)[1] in {"all", architecture}]
```

In `main`, replace `chosen = select(debs, installed(status))` with `chosen = select(debs, installed(status), architecture(status))`. `installed` stays as it is: the architecture line has one field and is skipped.

- [ ] **Step 8: Run the deploy tests**

Run: `uv run --frozen pytest testkit/tests/test_deploy.py -q`
Expected: pass.

- [ ] **Step 9: Commit the install filter**

Run `mcp__idea__get_file_problems` on the four files.

```bash
git add testkit/src/pihero_testkit/podman.py testkit/src/pihero_testkit/deploy.py testkit/tests/test_podman.py testkit/tests/test_deploy.py
git commit -m "fix(testkit): install only debs built for the target's architecture"
```

- [ ] **Step 10: Write the failing repo test**

Add to `testkit/tests/test_repo.py`:

```python
def test_release_options_name_the_architectures_the_repository_carries():
    options = repo.release_options()

    assert "APT::FTPArchive::Release::Architectures=all arm64" in options
```

Run: `uv run --frozen pytest testkit/tests/test_repo.py -q`
Expected: the new test fails (`Architectures=all` today).

- [ ] **Step 11: Implement and commit**

In `testkit/src/pihero_testkit/repo.py`:

```python
def release_options(origin: str = "pihero", label: str = "pihero", description: str = "Pi Hero packages", architectures: str = "all arm64") -> list[str]:
    """apt-ftparchive options for the Release file; an application publishing its own repository passes its name."""
    return [
        "-o", f"APT::FTPArchive::Release::Origin={origin}",
        "-o", f"APT::FTPArchive::Release::Label={label}",
        "-o", "APT::FTPArchive::Release::Suite=stable",
        "-o", f"APT::FTPArchive::Release::Architectures={architectures}",
        "-o", f"APT::FTPArchive::Release::Description={description}",
    ]
```

Run: `uv run --frozen pytest testkit/tests/test_repo.py -q`
Expected: pass. Run `mcp__idea__get_file_problems` on both files.

```bash
git add testkit/src/pihero_testkit/repo.py testkit/tests/test_repo.py
git commit -m "fix(testkit): list arm64 in the repository's release file"
```

---

### Task 4: The `cog` package

**Files:**
- Create: `packages/cog/Containerfile`
- Create: `packages/cog/build` (mode 0755)
- Create: `packages/cog/patches/0001-drm-keep-the-renderer-out-of-the-shm-buffer-resource.patch`
- Create: `packages/cog/tests/test_build.py`
- Create: `packages/cog/tests/test_installed.py`

**Interfaces:**
- Consumes: the script contract of Task 2; `tools.ensure_image`, `tools.run(image=...)` of Task 1; `build.TARGET_PLATFORM`.
- Produces: `dist/cog_0.18.4-1+pihero1_arm64.deb`. The version literal `0.18.4-1+pihero1` appears in the script and in the two tests.

- [ ] **Step 1: The Containerfile**

Create `packages/cog/Containerfile`:

```dockerfile
# Builds Debian's cog with Pi Hero's patch: the tools image's base plus cog's build dependencies (debian/control of cog 0.18.4-1).
FROM docker.io/library/debian:trixie-slim@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl build-essential debhelper \
      libcairo-dev libdrm-dev libepoxy-dev libgbm-dev libinput-dev libmanette-0.2-dev libwayland-dev \
      libwpebackend-fdo-1.0-dev libwpewebkit-2.0-dev meson wayland-protocols \
    && rm -rf /var/lib/apt/lists/*
# One-shot build image run with `podman run --rm`; there is no long-running service to probe.
HEALTHCHECK NONE
CMD ["bash"]
```

- [ ] **Step 2: The patch**

Create `packages/cog/patches/0001-drm-keep-the-renderer-out-of-the-shm-buffer-resource.patch`. Blank context lines inside the hunks are a single space; generate the hunks with `diff -u` from the two files in the spike's scratch directory (`cog-drm-modeset-renderer.orig.c`, `cog-drm-modeset-renderer.patched.c`) rather than typing them, then put this header above them:

```
Description: drm: keep the renderer out of the SHM buffer resource
 The modeset renderer stored its own pointer in the wl_buffer resource's
 user data. For an SHM buffer libwayland keeps the wl_shm_buffer there, so
 the second attach of the same buffer handed the copy garbage and cog
 crashed on the third software-rendered frame. The renderer now lives in
 cog's own buffer record, and the client's SHM buffer is released as soon
 as its pixels are copied, so a client-side pool resize is never deferred
 behind cog's reference.
Origin: backport, https://github.com/Igalia/cog/pull/794
Bug: https://github.com/Igalia/cog/issues/742
Last-Update: 2026-10-01
---
--- a/platform/drm/cog-drm-modeset-renderer.c
+++ b/platform/drm/cog-drm-modeset-renderer.c
```

The hunks, for reference (six of them; `@@ -74,6 +74,7 @@` adds `    void               *renderer;` after `struct wl_resource *buffer_resource;`; `@@ -137,14 +138,13 @@` replaces `wl_resource_get_user_data(buffer->buffer_resource)` with `buffer->renderer` and drops `wl_resource_set_user_data(buffer->buffer_resource, NULL);`; `@@ -216,7 +216,7 @@` and `@@ -271,7 +271,7 @@` replace `wl_resource_set_user_data(buffer_resource, self);` with `buffer->renderer = self;`; `@@ -534,7 +534,7 @@` and `@@ -543,7 +543,7 @@` replace `buffer->export.shm_buffer = exported_buffer;` with `wpe_view_backend_exportable_fdo_dispatch_release_shm_exported_buffer(self->exportable, exported_buffer);`).

- [ ] **Step 3: The build script**

Create `packages/cog/build` and `chmod 755` it:

```bash
#!/usr/bin/env bash
# Purpose: Build Debian's cog 0.18.4-1 with the DRM SHM export fix as cog 0.18.4-1+pihero1 for this machine's architecture.
# Usage:   build --dist <directory>
#
# Options:
#   --dist <directory>   Where the .deb and the build tree (<directory>/cog/) go; an existing .deb is reused.
#   -h, --help           Show this help.
#
# Runs inside the image built from the Containerfile next to this script, with the repository mounted at /work.
# Prints the path of the .deb on stdout and nothing else; everything else goes to stderr.

set -euo pipefail

usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"; }
die()   { printf '%s: %s\nSee '\''%s --help'\''\n' "${0##*/}" "$1" "${0##*/}" >&2; exit 2; }

readonly UPSTREAM=0.18.4
readonly DEBIAN=1
readonly PIHERO=1
readonly VERSION="${UPSTREAM}-${DEBIAN}+pihero${PIHERO}"
readonly POOL=https://deb.debian.org/debian/pool/main/c/cog
declare -rA SHA256=(
  ["cog_${UPSTREAM}-${DEBIAN}.dsc"]=d3e583c063584067dc0f65b4c4b6e8b953df8f2f93fde44a3abc88832402a399
  ["cog_${UPSTREAM}.orig.tar.xz"]=31d7079db2eeed790899d2f1f824dd6a54bf30d072d196d737be572f105d99b1
  ["cog_${UPSTREAM}.orig.tar.xz.asc"]=f578744a2d6aa6a9643c9ecfb9c98fe97e9a4011c5ba1eee188f7ade3c5c1e5a
  ["cog_${UPSTREAM}-${DEBIAN}.debian.tar.xz"]=5ffe778db83fe92327694c1baaa90ab3cb2db2bc0c9a4661b2a07ae890281e40
)

dist=""
while (( $# )); do
  case $1 in
    -h|--help) usage; exit 0 ;;
    --dist)    dist=${2?--dist: missing value}; shift 2 ;;
    --dist=*)  dist=${1#*=}; shift ;;
    -?*)       die "unknown option: $1" ;;
    *)         die "unexpected argument: $1" ;;
  esac
done
[[ -n $dist ]] || { usage >&2; exit 2; }

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
arch=$(dpkg --print-architecture)
deb="$dist/cog_${VERSION}_${arch}.deb"
if [[ -f $deb ]]; then
  printf '%s\n' "$deb"
  exit 0
fi

work="$dist/cog"
rm -rf "$work"
mkdir -p "$work"
for file in "${!SHA256[@]}"; do
  curl -fsSL -o "$work/$file" "$POOL/$file" || die "download failed: $POOL/$file"
  printf '%s  %s\n' "${SHA256[$file]}" "$work/$file" | sha256sum -c --quiet - || die "checksum mismatch: $file"
done

cd "$work"
dpkg-source -x "cog_${UPSTREAM}-${DEBIAN}.dsc" src >&2
cd src
mkdir -p debian/patches
for patch in "$here"/patches/*.patch; do
  cp "$patch" debian/patches/
  basename "$patch" >> debian/patches/series
done
{
  printf 'cog (%s) trixie; urgency=medium\n\n' "$VERSION"
  printf '  * drm: keep the renderer out of the SHM buffer resource and release the\n'
  printf '    buffer after the copy (Igalia/cog#794): software-rendered frames no\n'
  printf '    longer crash the modeset renderer.\n\n'
  printf ' -- Björn Kahlert <bkahlert@users.noreply.github.com>  %s\n\n' "$(date -R)"
  cat debian/changelog
} > debian/changelog.pihero
mv debian/changelog.pihero debian/changelog
dpkg-buildpackage -b -uc -us >&2
mv "../cog_${VERSION}_${arch}.deb" "$deb"
printf '%s\n' "$deb"
```

- [ ] **Step 4: shellcheck and the first build**

Run: `uv run --frozen pytest testkit/tests/test_static.py -q -k "shellcheck and cog"`
Expected: `packages/cog/build` passes.

Run: `make build` (the image build downloads the build dependencies, then the package builds; about three to five minutes; run it in the foreground or as a watched background task)
Expected: the last printed line is `/Users/bkahlert/Development/com.bkahlert/pihero/dist/cog_0.18.4-1+pihero1_arm64.deb`; `dist/cog/` holds the sources and the `.changes` file.

Verify the deb:

```bash
uv run --frozen python -c "
from pihero_testkit import tools
print(tools.run(['dpkg-deb', '--info', '/work/dist/cog_0.18.4-1+pihero1_arm64.deb'], capture=True).stdout)
print(tools.run(['sh', '-c', 'dpkg-deb --contents /work/dist/cog_0.18.4-1+pihero1_arm64.deb | grep -E \"modules/|changelog.Debian.gz\"'], capture=True).stdout)
"
```
Expected: `Version: 0.18.4-1+pihero1`, `Architecture: arm64`, `Depends:` naming `libwpewebkit-2.0-1`, the three `libcogplatform-*.so` modules.

Run `make build` again.
Expected: returns within seconds, the cog line printed from the existing deb.

- [ ] **Step 5: The tier 0 test that the deb is reused**

Create `packages/cog/tests/test_build.py`:

```python
import subprocess
from pathlib import Path

import pytest

from pihero_testkit import build, tools

pytestmark = pytest.mark.tier0
PACKAGE = Path(__file__).resolve().parents[1]
VERSION = "0.18.4-1+pihero1"


class TestBuildScript:
    def test_reuses_a_deb_that_exists(self):
        dist = Path.cwd() / "dist" / "probe-cog"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / f"cog_{VERSION}_arm64.deb").write_bytes(b"")
        try:
            result = tools.run(["/work/packages/cog/build", "--dist", "/work/dist/probe-cog"], image=tools.ensure_image(PACKAGE / "Containerfile", build.TARGET_PLATFORM), capture=True)

            assert result.stdout.strip() == f"/work/dist/probe-cog/cog_{VERSION}_arm64.deb"
            assert not (dist / "cog").exists()
        finally:
            subprocess.run(["rm", "-rf", str(dist)], check=True)
```

Run: `uv run --frozen pytest packages/cog/tests/test_build.py -q`
Expected: pass in a few seconds (the image exists from Step 4). Then break the reuse on purpose, by renaming `deb=` to `deb2=` in the `if [[ -f $deb ]]` line of the script, and run the test again: it must fail (the script starts downloading); revert the rename.

- [ ] **Step 6: The installed tests**

Create `packages/cog/tests/test_installed.py`:

```python
import pytest

pytestmark = pytest.mark.installed
VERSION = "0.18.4-1+pihero1"


class TestPackage:
    def test_is_installed(self, host):
        assert host.package("cog").is_installed

    def test_is_pi_heros_build_on_arm64(self, host):
        if host.check_output("dpkg --print-architecture") != "arm64":
            pytest.skip("the 32-bit boards keep Debian's cog")

        version = host.package("cog").version

        assert version == VERSION
```

Run: `make test-tier1`
Expected: both tests pass in the arm64 container, the existing kiosk tests pass as before (`cog` comes from `/dist/` now, `pihero-kiosk` depends on it unversioned).

- [ ] **Step 7: Tier 0, inspections, commit**

Run: `make test-tier0`
Expected: green, including shellcheck over `packages/cog/build`.

Run `mcp__idea__get_file_problems` on the five new files.

```bash
git add packages/cog
git commit -m "feat(cog): ship cog 0.18.4 with the drm shm export fix"
```

Check `git show --stat HEAD` lists `packages/cog/build` with mode `100755`.

---

### Task 5: Documentation

**Files:**
- Modify: `docs/design.md:66-118` (repository layout), `docs/design.md:28-46` (decisions), `docs/design.md:174-206` (`pihero-kiosk`), `docs/design.md:282-310` (Operations, development loop)
- Modify: `docs/testing.md:51-76` (tools container, tier 1)
- Modify: `README.md:11-19` (packages table), `README.md:90-96` (repository layout)

- [ ] **Step 1: design.md**

In the layout tree, after the `kaomoji/` block and before `testkit/`, add:

```
  cog/                                                    # Debian's cog rebuilt with one patch, see pihero-kiosk; no nfpm.yaml
    Containerfile  build                                  # its own build image and script: dpkg-buildpackage on the pinned Debian source
    patches/0001-*.patch                                  # DEP-3, the two hunks of Igalia/cog#794 that matter
    tests/test_build.py  tests/test_installed.py          # tier 0; tiers 1, 2, and ssh
```

In the bullet **Manifest**, after the kaomoji sentence, add: "`cog` has no manifest: a package directory with an executable `build` next to a `Containerfile` builds itself in that image, and the testkit takes the `.deb` paths the script prints."

In the decisions table, change the **Package build** row's choice to `` `nfpm`; `cog` rebuilds Debian's source package with `dpkg-buildpackage` in its own image `` and append to its why: "; the one package that is not Pi Hero's own code keeps Debian's packaging and adds a patch". Add a row after it:

```
| Kiosk browser | Debian's `cog` 0.18.4-1 rebuilt as `0.18.4-1+pihero1` with the DRM SHM export fix, arm64 only | Software-rendered frames, which the tier 2 VM produces on its virtual GPU, crash the stock modeset renderer; the fix is unreleased upstream ([Igalia/cog#794](https://github.com/Igalia/cog/pull/794)); the same package name lets devices take it with `apt upgrade`; the 32-bit boards keep Debian's, see [`pihero-kiosk`](#pihero-kiosk) |
```

In the `pihero-kiosk` section, after the paragraph on the SPI panel, add:

"cog itself comes from this repository since 2026-10-01: [packages/cog](../packages/cog) rebuilds trixie's 0.18.4-1 as
`0.18.4-1+pihero1` with one patch, the two hunks of [Igalia/cog#794](https://github.com/Igalia/cog/pull/794) that keep the
modeset renderer's pointer out of the SHM buffer resource's user data, where libwayland keeps the `wl_shm_buffer`, and
release the client's buffer once its pixels are copied. Without them cog segfaults on the third frame wherever WPE renders
in software and hands cog `wl_shm` buffers, which is what the tier 2 VM does on its virtual GPU (macOS QEMU has no virgl).
A board renders on its GPU and exports dmabufs, so it never ran that code; it takes the package on its next upgrade because
apt prefers the higher version, and behaves as before. The package is arm64 only, the 32-bit boards keep Debian's, and it
goes away once Debian ships a cog whose SHM path works. The gles renderer has no SHM path at all
([Igalia/cog#722](https://github.com/Igalia/cog/issues/722)), so a device file that selects it for a panel renders its VM
copy without that setting. Design: [2026-10-01-cog-package-design.md](superpowers/specs/2026-10-01-cog-package-design.md)."

In Operations, **Development loop**, change "reinstalls those over SSH" to "reinstalls those of its architecture over SSH".

- [ ] **Step 2: testing.md**

In the **Tools container** section, append the paragraph:

"A package directory with a `build` script next to a `Containerfile` builds itself: `make build` builds that image for
`linux/arm64` whatever the host is, runs the script with the repository mounted at `/work`, and takes the `.deb` paths it
prints. [packages/cog](../packages/cog) is the one such package; its image carries cog's build dependencies, which would
double the tools image. The script reuses a `.deb` that exists, so the three-minute build runs once per `make clean`."

In the **Tier 1** section, change "The built packages are mounted and installed with `apt install ./pkg.deb`" to "The built packages are mounted and those marked `all` or built for the container's architecture are installed with `apt install ./pkg.deb`; the arm64 `cog` stays out of the armhf container, which takes Debian's through `pihero-kiosk`".

- [ ] **Step 3: README.md**

Add to the packages table after `pihero-kiosk`:

```
| `cog`                 | Debian's cog 0.18.4 rebuilt with the fix that keeps software-rendered frames from crashing it, for arm64; the kiosk's browser from this repository until Debian carries the fix          |
```

In the repository layout table, change the `packages/` cell to: "One directory per Debian package: what it installs under `root/`, its `nfpm.yaml` manifest, its tests; [kaomoji/](packages/kaomoji/README.md) holds the kaomoji cast; [cog/](packages/cog) rebuilds Debian's cog with its own build script and image".

- [ ] **Step 4: Inspections and commit**

Run `mcp__idea__get_file_problems` on the three files; a Markdown table alignment warning is fixed by realigning.

```bash
git add docs/design.md docs/testing.md README.md
git commit -m "docs: pi hero's own cog build and packages that build themselves"
```

---

### Task 6: Prove it on the targets

**Files:** none; a failing run reopens the task that owns the code.

- [ ] **Step 1: Tier 0 and tier 1 once more from a clean dist**

Run: `make clean && make build && make test-tier0 && make test-tier1`
Expected: the cog build runs once (minutes), tiers 0 and 1 pass, `packages/cog/tests/test_installed.py` reports two passed.

- [ ] **Step 2: Tier 2**

Run: `make test-tier2` (about ten minutes; one VM at a time)
Expected: pass. In particular `packages/cog/tests/test_installed.py::TestPackage::test_is_pi_heros_build_on_arm64` passes on the VM, which proves apt accepted the flat repository with `Architectures: all arm64` and preferred `0.18.4-1+pihero1` over Debian's `0.18.4-1+b1`. The kiosk tests stay skipped (no `/dev/dri` yet). If apt rejected the index, `dist/vm/all-features/serial.log` and cloud-init's log name the `Release` file; the fix belongs in Task 3's `release_options`.

- [ ] **Step 3: The armhf view**

The armhf tier 1 runs only in CI (`make test-tier1 PLATFORM=linux/arm/v7` needs a `qemu-arm` binfmt the podman machine lacks). Ask before pushing the branch; CI's tier1 matrix then shows `test_is_pi_heros_build_on_arm64` skipped and `test_is_installed` passed on `linux/arm/v7`.

- [ ] **Step 4: Hand-over**

Report the deb's size and build time, the tier results, and what follows: the virtual GPU design for the testkit, then `make release VERSION=2.4.0`.
