"""One preview session in a VM: a throwaway overlay of the layer, its window, the kiosk's settings and the inspector's tunnel."""

import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .. import prepare
from ..vm import SSH_OPTS, Vm
from . import kiosk, window
from .layer import Layer


class Session:
    """A preview session in a windowed VM booted from a throwaway overlay of a layer; `stop()` deletes everything but the serial log kept on failure."""

    def __init__(self, layer: Layer, directory: Path, display: tuple[int, int], accel: str = "hvf", *, make_vm=Vm, prepare_base=prepare.prepare, place=window.place, run=subprocess.run, popen=subprocess.Popen, sleep=time.sleep, clock=time.monotonic):
        self.layer, self.directory, self.display, self.accel = layer, directory, display, accel
        self._make_vm, self._prepare, self._place, self._run, self._popen, self._sleep, self._clock = make_vm, prepare_base, place, run, popen, sleep, clock
        self.vm: Vm | None = None
        self.tunnel: subprocess.Popen | None = None

    def start(self, on_qemu: Callable[[int], None] | None = None) -> Vm:
        """Boot the VM in a window on a fresh overlay of the layer and wait for ssh; `on_qemu` gets QEMU's pid as soon as it runs."""
        self.directory.mkdir(parents=True, exist_ok=True)
        bootfs = self.directory / "bootfs.img"
        shutil.copy(self.layer.bootfs, bootfs)
        bootfs.chmod(0o644)
        self.vm = self._make_vm(self._prepare(), bootfs, self.directory, accel=self.accel, display=f"{self.display[0]}x{self.display[1]}", window=True, backing=self.layer.rootfs, repo_port=0).start()
        if on_qemu:
            on_qemu(self.vm.process.pid)
        try:
            self.vm.wait_ssh()
        except Exception as error:
            raise RuntimeError(f"{error}\nthe serial log is kept at {self.keep_serial_log()}") from error
        return self.vm

    def place_window(self) -> bool:
        """Place QEMU's window for the display; return whether macOS allowed it."""
        return self._place(self.vm.process.pid, self.display)

    def configure_kiosk(self, url: str) -> None:
        """Write the session's kiosk.conf over the guest's and restart the kiosk until it loads `url`."""
        current = self.vm.ssh(f"cat {kiosk.CONF}").stdout
        updated = kiosk.session_conf(current, url, video_mode=f"{self.display[0]}x{self.display[1]}")
        self._run(self.ssh_argv(f"sudo tee {kiosk.CONF} >/dev/null"), input=updated, text=True, check=True, capture_output=True)
        self.restart_kiosk()

    def restart_kiosk(self, timeout: float = 90) -> None:
        """Restart the kiosk and return once its journal shows the page loaded; raise TimeoutError naming the kept serial log."""
        since = self.vm.ssh(kiosk.since_command()).stdout.strip()
        self.vm.ssh(f"sudo systemctl restart {kiosk.UNIT}")
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            if kiosk.loaded(self.vm.ssh(kiosk.loaded_command(since)).stdout):
                return
            self._sleep(1)
        raise TimeoutError(f"the kiosk did not load its page within {timeout:g} s; see {self.keep_serial_log()}")

    def keep_serial_log(self) -> Path:
        """Copy the guest's serial log next to the session directory, which stop() deletes, and return the copy."""
        kept = self.directory.parent / "serial.log"
        kept.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.vm.serial_log, kept)
        return kept

    def open_tunnel(self, local_port: int) -> None:
        """Forward 127.0.0.1:`local_port` on the Mac to the guest's inspector until stop()."""
        forward = f"127.0.0.1:{local_port}:127.0.0.1:{kiosk.INSPECTOR_PORT}"
        self.tunnel = self._popen(self.ssh_argv(None, "-N", "-L", forward), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self) -> None:
        """Close the tunnel, power the guest off (or end QEMU), and delete the session directory even when QEMU will not end, raising then."""
        if self.tunnel and self.tunnel.poll() is None:
            self.tunnel.terminate()
        vm = self.vm
        try:
            if vm and vm.process and vm.process.poll() is None:
                try:
                    vm.ssh("sudo poweroff", timeout=15)
                    vm.wait_exit(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
                vm.stop()
        finally:
            shutil.rmtree(self.directory, ignore_errors=True)

    def ssh_argv(self, command: str | None, *options: str) -> list[str]:
        """Return the ssh command for the guest with `options`, running `command` if given."""
        argv = ["ssh", "-i", str(self.vm.key), "-p", str(self.vm.port), *SSH_OPTS, *options, f"{self.vm.user}@127.0.0.1"]
        return argv + [command] if command else argv
