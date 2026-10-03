"""Boots the tier-2 VM: QEMU virt with the prepared base image, a bootfs image built from a device directory, and a local apt repo.

The harness plays the firmware: it reads cmdline.txt from the bootfs image on every boot and QEMU runs with
-no-reboot, so a guest reboot returns here and the next boot picks up edited boot files.
"""

import argparse
import re
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

import testinfra

from . import bootfs as bootfs_mod
from . import build, prepare, qmp, repo

PACKAGE_DIR = Path(str(files("pihero_testkit")))
KEY = PACKAGE_DIR / "keys" / "pihero-testkit"
DEFAULT_DEVICE = PACKAGE_DIR / "devices" / "all-features"
# IdentitiesOnly keeps an ssh-agent with several keys from exhausting sshd's attempts before ours is offered.
SSH_OPTS = ["-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "LogLevel=ERROR"]
SSH_CONNECTION_FAILED = 255
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


def qemu_command(base: prepare.BaseImage, overlay: Path, bootfs: Path, serial_log: Path, append: str, accel: str, memory_mb: int, port: int, qmp_port: int, display: tuple[int, int] | None, window: bool = False) -> list[str]:
    """The qemu-system-aarch64 argument list for one boot: the headless virt machine, the disks, the network, the serial log, the QMP port, and the virtual display if any.

    With `window`, the display is shown in a macOS window that scales it. The window's size still reaches the guest as the connector's preferred mode, even with `edid=off`, and the kernel command line sets only the console's mode, so a kiosk that must keep its size pins it with COG_PLATFORM_DRM_VIDEO_MODE.
    """
    if window and not display:
        raise ValueError("a window needs a display")
    cpu = ["-cpu", "host"] if accel == "hvf" else ["-cpu", "cortex-a72"]
    gpu = ["-device", f"virtio-gpu-pci,xres={display[0]},yres={display[1]}{',edid=off' if window else ''}"] if display else []
    shown = ["-display", "cocoa,zoom-to-fit=on"] if window else ["-display", "none"]
    if window:
        append = f"{append} video=Virtual-1:{display[0]}x{display[1]}M@60e"
    return [
        "qemu-system-aarch64", "-M", "virt", "-accel", accel, *cpu, "-m", str(memory_mb), "-smp", "2",
        "-no-reboot", *shown, "-monitor", "none",
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


class QemuExited(RuntimeError):
    pass


class Vm:
    def __init__(self, base: prepare.BaseImage, bootfs: Path, workdir: Path, accel: str = "hvf", user: str = "pihero", memory_mb: int = 1024, debs: list[Path] = (), display: str = DEFAULT_DISPLAY, *, repo_port: int, window: bool = False, backing: Path | None = None):
        self.base, self.bootfs, self.workdir, self.accel, self.user, self.memory_mb, self.debs = base, bootfs, workdir, accel, user, memory_mb, list(debs)
        self.repo_port = repo_port
        self.overlay = workdir / "overlay.qcow2"
        self.serial_log = workdir / "serial.log"
        # git stores only 644/755, so a fresh checkout's private key is one ssh rejects as UNPROTECTED; use a 0600 copy.
        self.key = workdir / KEY.name
        shutil.copy(KEY, self.key)
        self.key.chmod(0o600)
        self.port = _free_port()
        self.qmp_port = _free_port()
        self.display = parse_display(display)
        if window and not self.display:
            raise ValueError("a window needs a display")
        self.window = window
        self.process: subprocess.Popen | None = None
        self.boots = 0
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-b", str(backing or base.rootfs), "-F", "qcow2", str(self.overlay)], check=True)

    def start(self) -> "Vm":
        append = bootfs_mod.kernel_args(bootfs_mod.read_cmdline(self.bootfs))
        command = qemu_command(self.base, self.overlay, self.bootfs, self.serial_log, append, self.accel, self.memory_mb, self.port, self.qmp_port, self.display, window=self.window)
        self.boots += 1
        with self.serial_log.open("a") as log:
            log.write(f"\n===== boot {self.boots}: {append}\n")
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        return self

    def ssh(self, command: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(["ssh", "-i", str(self.key), "-p", str(self.port), *SSH_OPTS, f"{self.user}@127.0.0.1", command], capture_output=True, text=True, timeout=timeout, check=False)

    def wait_ssh(self, timeout: int = 300) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise QemuExited(f"QEMU exited during boot {self.boots}; see {self.serial_log}\n{self.process.stderr.read()}")
            if self.ssh("true", timeout=15).returncode == 0:
                return
            time.sleep(2)
        raise TimeoutError(f"no SSH after {timeout}s; see {self.serial_log}")

    def wait_exit(self, timeout: int = 180) -> None:
        self.process.wait(timeout)

    def wait_provisioned(self, timeout: int = 1800) -> None:
        """Follows cloud-init to the end, including the reboot its power_state requests, until no reboot is pending."""
        # The budget is for TCG, where the kiosk's WebKit install stretches cloud-init; under HVF it is over in minutes.
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.wait_ssh(timeout=max(30, int(deadline - time.time())))
            except QemuExited:
                # Under -no-reboot a guest reboot before the first login also ends QEMU, with exit status 0.
                if self.process.returncode != 0:
                    raise
                self.start()
                continue
            status = self.ssh("cloud-init status --wait --long", timeout=1200)
            if self._recovered(status):
                continue
            if status.returncode != 0:
                raise RuntimeError(f"cloud-init failed (exit {status.returncode}):\n{status.stdout}{status.stderr}\n{self.ssh('sudo tail -n 60 /var/log/cloud-init.log').stdout}")
            pending = self.ssh("test -f /run/reboot-required")
            if self._recovered(pending):
                continue
            if pending.returncode == 0:
                self.reboot()
                continue
            return
        raise TimeoutError(f"provisioning did not settle within {timeout}s; see {self.serial_log}")

    def _recovered(self, result: subprocess.CompletedProcess) -> bool:
        """Restarts QEMU if it exited around this SSH call; returns whether the caller must go around again."""
        # Under -no-reboot QEMU exits only after the guest reboot drops SSH; a QEMU started earlier loses the hostfwd port race.
        dropped = result.returncode == SSH_CONNECTION_FAILED
        exited = self._exited_within(60 if dropped else 15)
        if exited:
            self.start()
            return True
        return dropped

    def _exited_within(self, seconds: int) -> bool:
        try:
            self.process.wait(seconds)
            return True
        except subprocess.TimeoutExpired:
            return False

    def reboot(self) -> None:
        self.ssh("sudo systemctl reboot")
        self.wait_exit()
        self.start()
        self.wait_ssh()

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(15)

    @property
    def host(self):
        return testinfra.get_host(f"ssh://{self.user}@127.0.0.1:{self.port}", ssh_identity_file=str(self.key), ssh_extra_args=" ".join(SSH_OPTS), sudo=True)

    def install_extra(self, names: list[str]) -> None:
        self.ssh("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q " + " ".join(names), timeout=900)

    def purge(self, names: list[str]) -> None:
        self.ssh("sudo DEBIAN_FRONTEND=noninteractive apt-get purge -y -q " + " ".join(names), timeout=600)

    def reinstall(self) -> None:
        self.ssh("sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --reinstall " + " ".join(d.name.split("_")[0] for d in self.debs), timeout=900)

    def ssh_command(self) -> str:
        return f"ssh -i {self.key} -p {self.port} {' '.join(SSH_OPTS)} {self.user}@127.0.0.1"

    def screenshot(self, path: Path) -> Path:
        """Saves what the virtual display shows as a PNG at path and returns it; fails without a display."""
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        qmp.execute(self.qmp_port, "screendump", {"filename": str(path), "format": "png"})
        return path


@contextmanager
def provisioned_vm(debs: list[Path], device_dir: str | Path | None, accel: str, keep: bool, display: str = DEFAULT_DISPLAY):
    device = Path(device_dir) if device_dir else DEFAULT_DEVICE
    base = prepare.prepare()
    workdir = build.DIST / "vm" / device.name
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)
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


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Boot the tier-2 VM from a device directory and keep it running.")
    parser.add_argument("--device", default=None)
    parser.add_argument("--qemu-accel", default="hvf")
    parser.add_argument("--display", default=DEFAULT_DISPLAY)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    debs = build.build_all(build.version_from_git())
    with provisioned_vm(debs, args.device, args.qemu_accel, keep=args.keep, display=args.display) as vm:
        print(vm.ssh_command())
        if args.keep:
            print("Press Ctrl-C to stop the VM.", file=sys.stderr)
            try:
                vm.process.wait()
            except KeyboardInterrupt:
                vm.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
