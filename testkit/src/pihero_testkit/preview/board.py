"""One preview session on a real board: its kiosk's session files under /run, the ssh tunnel to the Mac, and their removal."""

import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from .. import ssh
from . import kiosk, process

LOG_NAME = "tunnel.log"
DROPIN_DIR = f"/run/systemd/system/{kiosk.UNIT}.service.d"
REMOTE_OFFSET = 10000
CHANNEL_NOISE = re.compile(r"channel \d+: open failed")
APP_NAME = re.compile(r"[A-Za-z0-9._-]+")


def remote_port(mac_port: int) -> int:
    """Return the board's port for the Mac's `mac_port`, ten thousand above it; raise ValueError above 55535."""
    if mac_port > 65535 - REMOTE_OFFSET:
        raise ValueError(f"a Mac port of {mac_port} cannot be forwarded to the board; use one up to {65535 - REMOTE_OFFSET}")
    return mac_port + REMOTE_OFFSET


def forwards(mac_ports: list[int], inspector_local: int) -> list[str]:
    """Return the ssh forwards of a session: a reverse one per Mac port, and the inspector from the Mac's `inspector_local`."""
    args = []
    for port in mac_ports:
        args += ["-R", f"127.0.0.1:{remote_port(port)}:127.0.0.1:{port}"]
    return args + ["-L", f"127.0.0.1:{inspector_local}:127.0.0.1:{kiosk.INSPECTOR_PORT}"]


def tunnel_command(target: str, forward_args: list[str]) -> list[str]:
    """Return the `ssh -N` command carrying `forward_args` to `target` (user@host[:port]) over IPv4, ending when a forward fails."""
    user_host, _, port = target.partition(":")
    return ["ssh", "-N", "-4", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=10", *ssh.KEEPALIVE, *(["-p", port] if port else []), *forward_args, user_host]


class Session:
    """One preview session on a real board reached over ssh, with its kiosk files and tunnel on it; the app's `name` is letters, digits, '-', '_' or '.'."""

    def __init__(self, target: str, name: str, tunnel_log: Path, *, run=subprocess.run, popen=subprocess.Popen, answers=process.answers, sleep=time.sleep, clock=time.monotonic, report: Callable[[str], None] = lambda message: print(message, file=sys.stderr)):
        if not APP_NAME.fullmatch(name):
            raise ValueError(f"the app's name must be letters, digits, '-', '_' or '.', not {name!r}")
        self.target, self.tunnel_log = target, tunnel_log
        self.run_dir = f"/run/{name}-preview"
        self.conf = f"{self.run_dir}/kiosk.conf"
        self.dropin = f"{DROPIN_DIR}/{name}-preview.conf"
        self._run, self._popen, self._answers, self._sleep, self._clock, self._report = run, popen, answers, sleep, clock, report

    def ssh(self, remote: str, input: str | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
        """Run `remote` on the board; raise TimeoutError when it does not answer within `timeout` seconds."""
        try:
            return self._run(ssh.command(self.target, remote), input=input, text=True, capture_output=True, check=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"{self.target} did not answer within {timeout:g} s") from None

    def check_kiosk(self) -> None:
        """Raise RuntimeError when the board cannot be reached or has no pihero-kiosk."""
        result = self.ssh(f"dpkg-query -W {kiosk.PACKAGE}")
        if result.returncode == 255:
            raise RuntimeError(f"cannot reach {self.target} over ssh: {result.stderr.strip()}")
        if result.returncode != 0:
            raise RuntimeError(f"{self.target} has no {kiosk.PACKAGE}; flash a Pi Hero device file first")

    def session_conf(self, url: str) -> str:
        """Return the board's kiosk.conf rewritten for the session, changing nothing on the board."""
        current = self.ssh(f"cat {kiosk.CONF}")
        if current.returncode != 0:
            raise RuntimeError(f"cannot read {kiosk.CONF} on {self.target}: {current.stderr.strip()}")
        return kiosk.session_conf(current.stdout, url)

    def install_command(self) -> str:
        """Return the command that writes stdin as the session's conf, adds the drop-in and restarts the kiosk."""
        return (
            f"sudo install -d {self.run_dir} {DROPIN_DIR} && sudo tee {self.conf} >/dev/null && "
            f"printf '[Service]\\nEnvironmentFile={self.conf}\\n' | sudo tee {self.dropin} >/dev/null && "
            f"sudo systemctl daemon-reload && sudo systemctl restart {kiosk.UNIT}"
        )

    def restore_command(self) -> str:
        """Return the command that removes the session's files and restarts the kiosk."""
        return (
            f"sudo rm -rf {self.run_dir} {self.dropin}; sudo rmdir --ignore-fail-on-non-empty {DROPIN_DIR} 2>/dev/null; "
            f"sudo systemctl daemon-reload && sudo systemctl restart {kiosk.UNIT}"
        )

    def end_forwards_command(self, remote_ports: list[int]) -> str:
        """Return the command ending the board's sshd processes that still listen on `remote_ports` for a dead tunnel."""
        ports = "|".join(str(port) for port in remote_ports)
        return f"sudo ss -ltnpH | grep -E '127\\.0\\.0\\.1:({ports}) ' | grep sshd | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u | xargs -r sudo kill"

    def install(self, conf: str, tunnel: subprocess.Popen, timeout: float = 90) -> None:
        """Put the session on the board and wait for the kiosk to load its page, failing early with the tunnel's message if the tunnel ends."""
        since = self.ssh(kiosk.since_command()).stdout.strip()
        result = self.ssh(self.install_command(), input=conf)
        if result.returncode != 0:
            raise RuntimeError(f"could not put the session on {self.target}: {result.stderr.strip()}")
        self.wait_loaded(since, tunnel, timeout)

    def wait_loaded(self, since: str, tunnel: subprocess.Popen, timeout: float) -> None:
        """Return once the kiosk's journal shows a page load after `since`; raise when the tunnel ends or `timeout` passes."""
        deadline = self._clock() + timeout
        while self._clock() < deadline:
            if tunnel.poll() is not None:
                raise RuntimeError(self.tunnel_ended(tunnel))
            if kiosk.loaded(self.ssh(kiosk.loaded_command(since)).stdout):
                return
            self._sleep(1)
        raise TimeoutError(f"the kiosk on {self.target} did not load its page within {timeout:g} s; is the dev server up and the tunnel open?")

    def restore(self) -> bool:
        """Remove the session's files and restart the kiosk; return whether the board answered, else warn."""
        try:
            result = self.ssh(self.restore_command(), timeout=30)
        except (OSError, TimeoutError) as error:
            self._report(f"could not restore the kiosk on {self.target}: {error}; a reboot of the board removes the session's files")
            return False
        if result.returncode != 0:
            self._report(f"could not restore the kiosk on {self.target}: {result.stderr.strip()}; a reboot of the board removes the session's files")
        return result.returncode == 0

    def open_tunnel(self, forward_args: list[str], inspector_local: int, remote_ports: list[int]) -> subprocess.Popen:
        """Open the tunnel after ending the board's side of a dead one; raise RuntimeError when it ends early, TimeoutError after 15 s."""
        if remote_ports:
            self.ssh(self.end_forwards_command(remote_ports), timeout=30)
        self.tunnel_log.parent.mkdir(parents=True, exist_ok=True)
        with self.tunnel_log.open("w") as log:
            tunnel = self._popen(tunnel_command(self.target, forward_args), stdout=subprocess.DEVNULL, stderr=log, text=True)
        try:
            deadline = self._clock() + 15
            while self._clock() < deadline:
                if tunnel.poll() is not None:
                    raise RuntimeError(self.tunnel_ended(tunnel))
                if self._answers("127.0.0.1", inspector_local):
                    return tunnel
                self._sleep(0.25)
            raise TimeoutError(f"the ssh tunnel to {self.target} did not come up within 15 s; see {self.tunnel_log}")
        except BaseException:
            self.close_tunnel(tunnel)
            raise

    def tunnel_problem(self, tunnel: subprocess.Popen) -> str | None:
        """Return why the tunnel ended, or None while it runs."""
        return self.tunnel_ended(tunnel) if tunnel.poll() is not None else None

    def tunnel_ended(self, tunnel: subprocess.Popen) -> str:
        """Return the tunnel log's last message that is not channel noise, or the exit status and the log's path."""
        lines = self.tunnel_log.read_text(errors="replace").strip().splitlines() if self.tunnel_log.exists() else []
        reasons = [line for line in lines if not CHANNEL_NOISE.match(line)]
        if reasons:
            return f"the ssh tunnel to {self.target} ended: {reasons[-1]}"
        return f"the ssh tunnel to {self.target} ended with status {tunnel.poll()} and no message; see {self.tunnel_log}"

    def close_tunnel(self, tunnel: subprocess.Popen) -> None:
        """End the tunnel, killing it after five seconds."""
        if tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(5)
            except subprocess.TimeoutExpired:
                tunnel.kill()
