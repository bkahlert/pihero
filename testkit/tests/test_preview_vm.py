import re
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from pihero_testkit.preview import kiosk, layer
from pihero_testkit.preview import vm as preview_vm

pytestmark = pytest.mark.tier0
LAYER = layer.Layer(Path("/cache/preview/abc/rootfs.qcow2"), Path("/cache/preview/abc/bootfs.img"))


class TestStart:
    def test_boots_a_windowed_vm_on_an_overlay_of_the_layer_at_the_apps_display(self, tmp_path):
        (tmp_path / "layer").mkdir()
        bootfs = tmp_path / "layer" / "bootfs.img"
        bootfs.write_bytes(b"boot")
        made = {}
        fake = FakeVm()

        def make_vm(base, bootfs_copy, workdir, **kwargs):
            made.update(base=base, bootfs=bootfs_copy, workdir=workdir, **kwargs)
            return fake

        session = preview_vm.Session(layer.Layer(tmp_path / "layer" / "rootfs.qcow2", bootfs), tmp_path / "session", (480, 320), make_vm=make_vm, prepare_base=lambda: "BASE")
        pids = []

        started = session.start(on_qemu=pids.append)

        assert started is fake
        assert made["base"] == "BASE"
        assert made["bootfs"] == tmp_path / "session" / "bootfs.img" and made["bootfs"].read_bytes() == b"boot"
        assert (made["accel"], made["display"], made["window"], made["backing"], made["repo_port"]) == ("hvf", "480x320", True, tmp_path / "layer" / "rootfs.qcow2", 0)
        assert pids == [4242]
        assert fake.waited_ssh

    def test_keeps_the_serial_log_when_ssh_never_answers(self, tmp_path):
        (tmp_path / "layer").mkdir()
        (tmp_path / "layer" / "bootfs.img").write_bytes(b"boot")
        fake = FakeVm(ssh_fails=True)
        fake.serial_log = tmp_path / "session" / "serial.log"
        fake.serial_log.parent.mkdir()
        fake.serial_log.write_text("boot messages")
        session = preview_vm.Session(layer.Layer(tmp_path / "layer" / "rootfs.qcow2", tmp_path / "layer" / "bootfs.img"), tmp_path / "session", (800, 480), make_vm=lambda *a, **k: fake, prepare_base=lambda: "BASE")

        with pytest.raises(RuntimeError, match=re.escape(str(tmp_path / "serial.log"))):
            session.start()

        assert (tmp_path / "serial.log").read_text() == "boot messages"


class TestConfigureKiosk:
    def test_writes_the_session_conf_over_the_guests_and_restarts_the_kiosk(self, tmp_path):
        fake = FakeVm(conf='URL=http://localhost/\nCOG_ARGS="--doc-viewer"\n')
        runs = []
        session = session_with(fake, tmp_path, run=lambda argv, **kw: runs.append((argv, kw)) or CompletedProcess(argv, 0, "", ""))

        session.configure_kiosk("http://10.0.2.2:8081/")

        argv, kw = runs[0]
        assert argv[-1] == f"sudo tee {kiosk.CONF} >/dev/null"
        assert kw["input"] == kiosk.session_conf('URL=http://localhost/\nCOG_ARGS="--doc-viewer"\n', "http://10.0.2.2:8081/", video_mode="800x480")
        assert f"sudo systemctl restart {kiosk.UNIT}" in fake.commands


class TestRestartKiosk:
    def test_returns_once_the_journal_shows_the_page_loaded(self, tmp_path):
        fake = FakeVm(loaded=iter(["0\n", "0\n", "1\n"]))
        session = session_with(fake, tmp_path)

        session.restart_kiosk()

        assert fake.commands[0] == kiosk.since_command()
        assert fake.commands[1] == f"sudo systemctl restart {kiosk.UNIT}"
        assert fake.commands[2] == kiosk.loaded_command("2026-10-03 10:00:00")

    def test_raises_naming_the_kept_serial_log_when_the_page_never_loads(self, tmp_path):
        fake = FakeVm(loaded=iter(["0\n"] * 100))
        session = session_with(fake, tmp_path, clock=counter(step=50))
        fake.serial_log.parent.mkdir(parents=True)
        fake.serial_log.write_text("boot messages")

        with pytest.raises(TimeoutError, match=re.escape(f"did not load its page within 90 s; see {tmp_path / 'serial.log'}")):
            session.restart_kiosk()

        assert (tmp_path / "serial.log").read_text() == "boot messages"


class TestOpenTunnel:
    def test_forwards_the_local_port_to_the_guests_inspector(self, tmp_path):
        fake = FakeVm()
        opened = []
        session = session_with(fake, tmp_path, popen=lambda argv, **kw: opened.append(argv) or SimpleNamespace(poll=lambda: None, terminate=lambda: None))

        session.open_tunnel(54321)

        argv = opened[0]
        assert argv[:2] == ["ssh", "-i"]
        assert "-N" in argv and argv[argv.index("-L") + 1] == "127.0.0.1:54321:127.0.0.1:2999"
        assert argv[-1] == "pihero@127.0.0.1"


class TestStop:
    def test_removes_the_directory_of_a_session_that_never_started(self, tmp_path):
        directory = tmp_path / "session"
        directory.mkdir()

        preview_vm.Session(LAYER, directory, (800, 480)).stop()

        assert not directory.exists()

    def test_powers_the_guest_off_closes_the_tunnel_and_deletes_the_directory(self, tmp_path):
        fake = FakeVm()
        session = session_with(fake, tmp_path)
        ended = []
        session.tunnel = SimpleNamespace(poll=lambda: None, terminate=lambda: ended.append("tunnel"))
        (tmp_path / "session").mkdir(exist_ok=True)

        session.stop()

        assert ended == ["tunnel"]
        assert fake.commands[-1] == "sudo poweroff"
        assert fake.stopped
        assert not (tmp_path / "session").exists()

    def test_ends_qemu_and_deletes_the_directory_when_the_guest_ignores_poweroff(self, tmp_path):
        fake = FakeVm(hangs=True)
        session = session_with(fake, tmp_path)
        (tmp_path / "session").mkdir(exist_ok=True)

        session.stop()

        assert fake.stopped
        assert not (tmp_path / "session").exists()

    def test_ends_qemu_at_once_when_the_guest_does_not_answer_poweroff(self, tmp_path):
        fake = FakeVm(poweroff_status=255)
        session = session_with(fake, tmp_path)

        session.stop()

        assert fake.waited_exit == []
        assert fake.stopped

    def test_deletes_the_directory_and_raises_when_qemu_will_not_end(self, tmp_path):
        fake = FakeVm(stop_fails=True)
        session = session_with(fake, tmp_path)
        (tmp_path / "session").mkdir(exist_ok=True)

        with pytest.raises(subprocess.TimeoutExpired):
            session.stop()

        assert not (tmp_path / "session").exists()


class FakeVm:
    def __init__(self, conf: str = "URL=http://localhost/\n", loaded=None, ssh_fails: bool = False, hangs: bool = False, stop_fails: bool = False, poweroff_status: int = 0):
        self.conf, self.loaded, self.ssh_fails, self.hangs, self.stop_fails, self.poweroff_status = conf, loaded or iter(["1\n"]), ssh_fails, hangs, stop_fails, poweroff_status
        self.commands, self.waited_exit = [], []
        self.waited_ssh = self.stopped = False
        self.process = SimpleNamespace(pid=4242, poll=lambda: None)
        self.serial_log = Path("/nonexistent/serial.log")
        self.key, self.port, self.user = Path("/k"), 2222, "pihero"

    def start(self):
        return self

    def wait_ssh(self):
        if self.ssh_fails:
            raise TimeoutError("no SSH after 300s")
        self.waited_ssh = True

    def ssh(self, command, timeout=120):
        self.commands.append(command)
        if command == kiosk.since_command():
            return CompletedProcess(command, 0, "2026-10-03 10:00:00\n", "")
        if command.startswith("sudo journalctl"):
            return CompletedProcess(command, 0, next(self.loaded), "")
        if command == f"cat {kiosk.CONF}":
            return CompletedProcess(command, 0, self.conf, "")
        if command == "sudo poweroff":
            return CompletedProcess(command, self.poweroff_status, "", "")
        return CompletedProcess(command, 0, "", "")

    def wait_exit(self, timeout=180):
        self.waited_exit.append(timeout)
        if self.hangs:
            raise subprocess.TimeoutExpired("qemu", timeout)

    def stop(self):
        self.stopped = True
        if self.stop_fails:
            raise subprocess.TimeoutExpired("qemu", 15)


def session_with(fake: FakeVm, tmp_path: Path, **injected) -> preview_vm.Session:
    fake.serial_log = tmp_path / "session" / "serial.log"
    session = preview_vm.Session(LAYER, tmp_path / "session", (800, 480), sleep=lambda s: None, **({"clock": counter()} | injected))
    session.vm = fake
    return session


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
