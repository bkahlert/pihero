# Tier-2 repository on a free port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two tier-2 runs on one Mac, from two repositories, no longer collide on the apt repository's port 8000.

**Architecture:** The harness serves the flat repository from a free localhost port instead of 8000. The URL a device
file writes, `http://10.0.2.2:8000/`, stays what it is and becomes the documented meaning of "the harness's repository":
when the harness stages `user-data` for the boot image, it replaces that URL's port with the one it bound. QEMU's
user-mode network maps guest `10.0.2.2:P` to the host's `127.0.0.1:P` for any `P`, and the SSH and QMP forwards already use
free ports, so after this two runs share nothing but CPU and the read-only base image. The VM exposes the port as
`target.repo_port`; the boot test asserts apt sees it.

**Tech Stack:** Python standard library (`http.server`, `shutil`), pytest, the existing testkit; QEMU for the tier-2 proof.

**Spec:** none. This is a bounded change designed in chat; the Architecture paragraph above is the agreed design.
Evidence that motivated it: while pihero's tier 2 was running in one session, netmon's tier-2 soak run in another session
held 127.0.0.1:8000, and the pihero run failed after its package build with 65 "Address already in use" setup errors.

## Global Constraints

- The testkit's fixtures, markers, options, `load_script`, and the attributes apps read from `target` (`key`, `port`,
  `user`) are an API pinned by tag from other repositories. This change is additive: nothing existing is renamed or
  removed except the module constant `vm.REPO_PORT` and `repo.Server`'s `port` parameter, which nothing outside `vm.py`
  reads or passes.
- Device files keep writing `http://10.0.2.2:8000/` exactly in that form, with the trailing slash. The harness rewrites
  that string and nothing else; a device file without it is copied unchanged.
- Standard library only in the testkit, as today.
- New tier-0 tests need no podman and no network beyond localhost.
- Docs change in the same commit: [docs/testing.md](../../testing.md) "Tier 2" and "Writing tests",
  [docs/design.md](../../design.md) "Applications".
- One commit, Conventional Commits with scope: `fix(testkit): serve the tier-2 repository on a free port`. Branch
  `fix/tier2-repo-free-port` from `main`; `main` takes it through a pull request.

## Review Focus

- A device file that writes the URL in another form (`http://10.0.2.2:8000` without the slash, a different host
  spelling) is not rewritten; apt in the VM then fails with "connection refused" on port 8000. The docs name the exact
  form, and Task 2 tests that the testkit's own device file uses it. An app's device file is the app's test's job.
- QEMU's mapping of guest `10.0.2.2:P` to host loopback for arbitrary `P` is exercised only by the tier-2 run in Task 3,
  never at tier 0. Task 3 does not end until that run is green.
- `--keep` leaves the VM running but the repository server dies with pytest, as before; the kept-VM message now names the
  repository URL so a person sees which port the VM expects.
- Two runs of the same device directory inside one checkout still share `dist/vm/<device>/`. Out of scope; unchanged.
- The boot test asserts `10.0.2.2:<port>` rather than the full URL, as the existing assertion does for 8000, so it
  matches whether or not `apt-cache policy` prints the trailing slash.

## File structure

- Modify [testkit/src/pihero_testkit/repo.py](../../../testkit/src/pihero_testkit/repo.py): `HOST`, `URL`, `url(port)`;
  `Server` binds port 0, exposes `port` and `url`.
- Modify [testkit/src/pihero_testkit/bootfs.py](../../../testkit/src/pihero_testkit/bootfs.py): the staging loop moves
  into `stage(device_dir, stock_boot, staging, repo_port)`, which rewrites `user-data`; `build_bootfs` takes `repo_port`.
- Modify [testkit/src/pihero_testkit/vm.py](../../../testkit/src/pihero_testkit/vm.py): drop `REPO_PORT`; `Vm` gains
  `repo_port`; `provisioned_vm` wires server, bootfs, and VM; the `--keep` message names the repository.
- Modify [testkit/tests/test_repo.py](../../../testkit/tests/test_repo.py): `TestServer`.
- Modify [testkit/tests/test_bootfs.py](../../../testkit/tests/test_bootfs.py): `TestStage`.
- Modify [testkit/tests/test_boot.py](../../../testkit/tests/test_boot.py): the apt source assertion uses
  `target.repo_port`.
- Modify [docs/testing.md](../../testing.md), [docs/design.md](../../design.md).

Tasks 1 and 2 leave their changes staged but uncommitted: `provisioned_vm` is consistent only once Task 3 wires the new
pieces together, and one changelog line describes the whole fix. Task 3 commits.

---

### Task 1: The repository server binds a free port

**Files:**
- Modify: `testkit/src/pihero_testkit/repo.py:43-54`
- Test: `testkit/tests/test_repo.py`

**Interfaces:**
- Produces: `repo.HOST = "10.0.2.2"`, `repo.URL = "http://10.0.2.2:8000/"`, `repo.url(port: int) -> str`,
  `repo.Server(directory: Path)` with attributes `port: int` and `url: str` (the source as the guest reaches it) and
  `close()`.

- [ ] **Step 1: Create the branch**

```bash
git switch -c fix/tier2-repo-free-port main
```

- [ ] **Step 2: Write the failing tests**

Append to `testkit/tests/test_repo.py` (add `import urllib.request` at the top, after `import pytest`):

```python
class TestServer:
    def test_runs_next_to_another_server(self, server, tmp_path):
        second = repo.Server(tmp_path)
        second.close()

        assert second.port != server.port

    def test_serves_the_directory(self, server):
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/Packages") as response:
            body = response.read()

        assert body == b"Package: pihero\n"

    def test_names_the_source_as_the_guest_reaches_it(self, server):
        assert server.url == f"http://10.0.2.2:{server.port}/"

    @pytest.fixture
    def server(self, tmp_path):
        (tmp_path / "Packages").write_text("Package: pihero\n")
        server = repo.Server(tmp_path)
        yield server
        server.close()
```

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_repo.py -q`
Expected: `test_runs_next_to_another_server` FAILS with `OSError: [Errno 48] Address already in use`, since the
fixture's server holds 8000, and `test_names_the_source_as_the_guest_reaches_it` with `AttributeError: 'Server' object
has no attribute 'url'`. While another process holds 8000, the fixture itself raises and all three ERROR instead. The
three existing `release_options` tests pass either way.

- [ ] **Step 4: Implement**

In `testkit/src/pihero_testkit/repo.py`, add below the imports:

```python
HOST = "10.0.2.2"  # the host as QEMU's user-mode network presents it to the guest
URL = f"http://{HOST}:8000/"
"""The source a device file writes for the harness's repository. Tier 2 serves on a free port and points this URL at it
when it stages user-data, so tier-2 runs of several repositories share a Mac."""


def url(port: int) -> str:
    return f"http://{HOST}:{port}/"
```

Replace the `Server` class:

```python
class Server:
    """Serves a repository directory from a free localhost port; `url` is the source as the guest reaches it."""

    def __init__(self, directory: Path):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.url = url(self.port)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_repo.py -q`
Expected: 6 passed.

- [ ] **Step 6: Stage**

```bash
git add testkit/src/pihero_testkit/repo.py testkit/tests/test_repo.py
```

### Task 2: Staging the boot image points the device file's source at the served port

**Files:**
- Modify: `testkit/src/pihero_testkit/bootfs.py:1-28`
- Test: `testkit/tests/test_bootfs.py`

**Interfaces:**
- Consumes: `repo.URL`, `repo.url(port)` from Task 1.
- Produces: `bootfs.stage(device_dir: Path, stock_boot: Path, staging: Path, repo_port: int) -> Path` (the staging
  directory); `bootfs.build_bootfs(device_dir: Path, stock_boot: Path, out: Path, repo_port: int) -> Path`.

- [ ] **Step 1: Write the failing tests**

In `testkit/tests/test_bootfs.py`, change the import to `from pihero_testkit import bootfs, repo, vm`, add the class below
`TestKernelArgs`, and the constant at the end of the file:

```python
class TestStage:
    def test_points_the_harness_repository_source_at_the_served_port(self, device, stock, tmp_path):
        staged = bootfs.stage(device, stock, tmp_path / "bootfs.d", repo_port=54321)

        user_data = (staged / "user-data").read_text()
        assert "      URIs: http://10.0.2.2:54321/\n" in user_data
        assert "8000" not in user_data

    def test_copies_the_other_files_unchanged(self, device, stock, tmp_path):
        staged = bootfs.stage(device, stock, tmp_path / "bootfs.d", repo_port=54321)

        assert (staged / "network-config").read_text() == "version: 2\n"
        assert (staged / "config.txt").read_text() == "arm_64bit=1\n"
        assert (staged / "cmdline.txt").read_text() == STOCK

    def test_leaves_a_user_data_without_the_source_as_it_is(self, device, stock, tmp_path):
        (device / "user-data").write_text("#cloud-config\nhostname: plain\n")

        staged = bootfs.stage(device, stock, tmp_path / "bootfs.d", repo_port=54321)

        assert (staged / "user-data").read_text() == "#cloud-config\nhostname: plain\n"

    def test_writes_a_meta_data_for_a_device_without_one(self, device, stock, tmp_path):
        staged = bootfs.stage(device, stock, tmp_path / "bootfs.d", repo_port=54321)

        assert (staged / "meta-data").read_text() == "instance-id: pihero-sample-1\nlocal-hostname: sample\n"

    def test_rewrites_the_source_the_all_features_device_writes(self):
        user_data = (vm.DEFAULT_DEVICE / "user-data").read_text()

        assert f"      URIs: {repo.URL}\n" in user_data

    @pytest.fixture
    def device(self, tmp_path):
        device = tmp_path / "sample"
        device.mkdir()
        (device / "user-data").write_text(USER_DATA)
        (device / "network-config").write_text("version: 2\n")
        return device

    @pytest.fixture
    def stock(self, tmp_path):
        stock = tmp_path / "boot"
        stock.mkdir()
        (stock / "config.txt").write_text("arm_64bit=1\n")
        (stock / "cmdline.txt").write_text(STOCK)
        return stock


USER_DATA = """\
#cloud-config
write_files:
  - path: /etc/apt/sources.list.d/pihero.sources
    content: |
      Types: deb
      URIs: http://10.0.2.2:8000/
      Suites: ./
      Trusted: yes
"""
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest testkit/tests/test_bootfs.py -q`
Expected: 4 FAIL with `AttributeError: module 'pihero_testkit.bootfs' has no attribute 'stage'`;
`test_rewrites_the_source_the_all_features_device_writes` and the three `TestKernelArgs` tests pass.

- [ ] **Step 3: Implement**

In `testkit/src/pihero_testkit/bootfs.py`, change the import to `from . import repo, tools` and replace `build_bootfs`:

```python
def build_bootfs(device_dir: Path, stock_boot: Path, out: Path, repo_port: int) -> Path:
    staging = stage(device_dir, stock_boot, out.parent / f"{out.stem}.d", repo_port)
    out.parent.mkdir(parents=True, exist_ok=True)
    tools.run(
        ["sh", "-c", f"rm -f /out/{out.name} && mkfs.vfat -n bootfs -C /out/{out.name} {SIZE_KIB} >/dev/null && mcopy -i /out/{out.name} -s /staging/* ::/"],
        mounts=[f"{out.parent}:/out", f"{staging}:/staging:ro"],
    )
    return out


def stage(device_dir: Path, stock_boot: Path, staging: Path, repo_port: int) -> Path:
    """Collects the boot partition under staging: the stock config.txt and cmdline.txt, the device directory's files with
    user-data's harness repository source pointed at repo_port, and a meta-data when the device has none."""
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    for name in ("config.txt", "cmdline.txt"):
        shutil.copy(stock_boot / name, staging / name)
    for file in device_dir.iterdir():
        if file.is_file():
            shutil.copy(file, staging / file.name)
    user_data = staging / "user-data"
    if user_data.exists():
        user_data.write_text(user_data.read_text().replace(repo.URL, repo.url(repo_port)))
    if not (staging / "meta-data").exists():
        (staging / "meta-data").write_text(f"instance-id: pihero-{device_dir.name}-1\nlocal-hostname: {device_dir.name}\n")
    return staging
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --frozen pytest testkit/tests/test_bootfs.py -q`
Expected: 8 passed.

- [ ] **Step 5: Stage**

```bash
git add testkit/src/pihero_testkit/bootfs.py testkit/tests/test_bootfs.py
```

### Task 3: Tier 2 wires it together, the boot test proves it, the docs say it

**Files:**
- Modify: `testkit/src/pihero_testkit/vm.py:26` (drop `REPO_PORT`), `:69-70` (`Vm.__init__`), `:189-209`
  (`provisioned_vm`)
- Modify: `testkit/tests/test_boot.py:29-31`
- Modify: `docs/testing.md:34-35`, `docs/testing.md:115-116`; `docs/design.md:371-372`

**Interfaces:**
- Consumes: `repo.Server(directory)` with `port`, `url` (Task 1); `bootfs.build_bootfs(..., repo_port)` (Task 2).
- Produces: `Vm.repo_port: int`, read by tests as `target.repo_port`.

- [ ] **Step 1: Change the boot test first**

In `testkit/tests/test_boot.py`, replace the apt source test:

```python
    def test_apt_knows_the_pihero_source(self, host, target):
        assert host.file("/etc/apt/sources.list.d/pihero.sources").exists
        assert f"10.0.2.2:{target.repo_port}" in host.check_output("apt-cache policy")
```

This test runs only at tier 2 (Step 6). Its failure mode before the implementation: `AttributeError: 'Vm' object has no
attribute 'repo_port'`.

- [ ] **Step 2: Wire the VM**

In `testkit/src/pihero_testkit/vm.py`:

Delete the line `REPO_PORT = 8000`.

Change the `Vm` constructor's signature and first body line to:

```python
    def __init__(self, base: prepare.BaseImage, bootfs: Path, workdir: Path, accel: str = "hvf", user: str = "pihero", memory_mb: int = 1024, debs: list[Path] = (), display: str = DEFAULT_DISPLAY, *, repo_port: int):
        self.base, self.bootfs, self.workdir, self.accel, self.user, self.memory_mb, self.debs = base, bootfs, workdir, accel, user, memory_mb, list(debs)
        self.repo_port = repo_port
```

Replace the body of `provisioned_vm` from the `server = ...` line to the end:

```python
    # A repo inside the recreated workdir holds only this run's debs, so no stale build can outrank them in apt's eyes.
    server = repo.Server(repo.build_repo(debs, workdir / "repo"))
    try:
        image = bootfs_mod.build_bootfs(device, base.boot, workdir / "bootfs.img", server.port)
        vm = Vm(base, image, workdir, accel=accel, debs=debs, display=display, repo_port=server.port).start()
        try:
            vm.wait_provisioned()
            yield vm
        finally:
            if keep:
                print(f"\nVM kept running. Connect with:\n  {vm.ssh_command()}\nSerial log: {vm.serial_log}\nQMP port: {vm.qmp_port}\nRepository: {server.url}", file=sys.stderr)
            else:
                vm.stop()
    finally:
        server.close()
```

- [ ] **Step 3: Confirm nothing else names the old constant**

Run: `grep -rn "REPO_PORT" testkit/ packages/ docs/ README.md`
Expected: no output.

- [ ] **Step 4: Tier 0 and the static checks**

Run: `make test-tier0`
Expected: all passed (tier 0 collected 453 tests before this change; now 461).

- [ ] **Step 5: Docs**

`docs/testing.md`, the "Writing tests" fixture sentence: change

> `target` is the container, VM, or ssh target with `install_extra`, `purge`, `reinstall`, and `reboot`;

to

> `target` is the container, VM, or ssh target with `install_extra`, `purge`, `reinstall`, and `reboot`, and on the VM
> `repo_port`, the Mac port its repository is served on;

`docs/testing.md`, the "Tier 2" **Repository** bullet, replace the whole bullet with:

> - **Repository.** The run builds every package, generates a flat unsigned repository under `dist/vm/<device>/repo`, and
>   serves it from the Mac on a free port, so tier-2 runs of several repositories share a Mac. A device file writes the
>   source as `http://10.0.2.2:8000/` with `Trusted: yes`, exactly in that form: the QEMU host address at the conventional
>   port. The harness points that URL at the port it bound when it stages `user-data` for the boot image, and
>   `target.repo_port` is that port.

`docs/design.md`, "Applications", change

> with a tier-2 device file that adds the app's apt source to a copy of the all-features device.

to

> with a tier-2 device file that adds the app's apt source, `http://10.0.2.2:8000/` with `Trusted: yes`, to a copy of the
> all-features device; the harness serves that repository on a free port and rewrites the URL's port when it stages the
> file, so tier-2 runs of several repositories share a Mac.

- [ ] **Step 6: Tier 2, ideally while another tier-2 run is live**

Run: `lsof -nP -iTCP:8000 -sTCP:LISTEN` first. If netmon's tier 2 holds the port, keep it running: that is the proof.
Then: `make test-tier2`
Expected: all passed, `test_apt_knows_the_pihero_source` included, with 8000 busy or not. The serial log under
`dist/vm/all-features/` shows apt fetching from `http://10.0.2.2:<port>/`.

If apt in the VM reports "connection refused" or hangs on the source: QEMU's mapping of the guest port did not reach the
server. Check the rewritten `dist/vm/all-features/bootfs.d/user-data` carries the server's port and that
`curl http://127.0.0.1:<port>/Packages` answers on the Mac before concluding anything about QEMU.

- [ ] **Step 7: Commit and open the pull request**

```bash
git add testkit/src/pihero_testkit/vm.py testkit/tests/test_boot.py docs/testing.md docs/design.md docs/superpowers/plans/2026-10-02-tier2-repo-free-port.md
git commit -m "fix(testkit): serve the tier-2 repository on a free port" -m "Two tier-2 runs on one Mac, from two repositories, collided on
127.0.0.1:8000: the second failed after its package build with an
\"Address already in use\" in every test's setup. The harness now binds
a free port and points the device file's http://10.0.2.2:8000/ source
at it when it stages user-data, so that URL stays what device files
write and runs no longer share anything but CPU. target.repo_port
tells a test which port the VM uses."
git push -u origin fix/tier2-repo-free-port
gh pr create --title "fix(testkit): serve the tier-2 repository on a free port" --body "$(git log -1 --format=%b)"
```

Expected: CI (tiers 0 and 1) green; squash-merge with the title as the header. The fix ships to apps with the next
`v*` release; netmon's device file needs no change, and it keeps working on its current pin as well.

## QA for the whole change

Tier 0: the six new tests in `TestServer` and `TestStage` fail before and pass after their tasks. Tier 2: `make test-tier2`
is green with netmon's tier 2 holding port 8000 at the same time, and `test_apt_knows_the_pihero_source` sees the bound
port in `apt-cache policy`. That concurrent green run is the observable outcome that confirms the change.
