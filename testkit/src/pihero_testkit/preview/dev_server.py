"""The app's dev server for a session: started in its own process group, waited for on its port, ended as a group."""

import os
import signal
import subprocess
import time
from pathlib import Path

from . import process
from .api import DevServer

LOG_NAME = "dev-server.log"


def start(server: DevServer, root: Path, log: Path, environ=os.environ, popen=subprocess.Popen) -> subprocess.Popen:
    """Start `server` in `root` with its env added, output to `log`, in a new session so its whole group can be ended."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as output:
        return popen(server.argv, cwd=root, env={**environ, **server.env}, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)


def wait_until_serving(proc, port: int, log: Path, timeout: float = 900, answers=process.answers, sleep=time.sleep, clock=time.monotonic) -> None:
    """Return once `port` answers; raise RuntimeError when the process ends first, TimeoutError after `timeout` seconds."""
    deadline = clock() + timeout
    while clock() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"the dev server exited with status {proc.returncode}; see {log}")
        if answers("127.0.0.1", port):
            return
        sleep(1)
    raise TimeoutError(f"nothing answers on port {port} after {timeout:g} s; see {log}")


def stop(proc: subprocess.Popen, killpg=os.killpg, timeout: float = 30) -> None:
    """End the process group of `proc` with SIGTERM, then SIGKILL after `timeout` seconds; nothing for an ended process or group."""
    if proc.poll() is not None:
        return
    try:
        killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def ensure(server: DevServer, root: Path, log: Path, *, answers=process.answers, start=start, wait=wait_until_serving, stop=stop, on_start=None) -> subprocess.Popen:
    """Start `server`, hand its process to `on_start` before waiting, and return it once it serves; raise RuntimeError when something already answers on its port."""
    if answers("127.0.0.1", server.port):
        raise RuntimeError(f"something already answers on port {server.port}; end it first")
    proc = start(server, root, log)
    try:
        if on_start:
            on_start(proc)
        wait(proc, server.port, log)
    except BaseException:
        stop(proc)
        raise
    return proc
