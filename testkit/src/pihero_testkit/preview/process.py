"""Helpers for the preview's processes: probing a port, a process's start time, ending on Ctrl-C or SIGTERM, waiting."""

import signal
import socket
import subprocess
import time
from collections.abc import Callable


def answers(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return whether something accepts a TCP connection at host:port within `timeout` seconds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def info(pid: int, run=subprocess.run) -> tuple[str, str] | None:
    """Return the start time and state of the running process `pid` as `ps` prints them, or None when it is gone or a zombie."""
    result = run(["ps", "-p", str(pid), "-o", "lstart=,stat="], capture_output=True, text=True, check=False)
    line = result.stdout.strip()
    if not line:
        return None
    started, _, state = line.rpartition(" ")
    if state.startswith("Z"):
        return None
    return started.strip(), state


def entry(pid: int, info=info) -> list | None:
    """Return `[pid, start time]` for the record, or None when the process is gone."""
    found = info(pid)
    return [pid, found[0]] if found else None


def alive(entry, info=info) -> bool:
    """Return whether the record entry `[pid, start time]` still names a running process; False for any other value."""
    if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], int):
        return False
    found = info(entry[0])
    return bool(found) and found[0] == entry[1]


def wait_until_gone(pids: list[int], info=info, timeout: float = 30, sleep=time.sleep, clock=time.monotonic) -> None:
    """Return once none of `pids` runs any more; raise TimeoutError after `timeout` seconds."""
    deadline = clock() + timeout
    running = [pid for pid in pids if info(pid)]
    while running:
        if clock() >= deadline:
            raise TimeoutError(f"process {running[0]} of a killed preview did not end within {timeout:g} s")
        sleep(0.5)
        running = [pid for pid in running if info(pid)]


def raise_on_sigterm() -> None:
    """Make SIGTERM end the program the way Ctrl-C does, so exit stacks run."""

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)


def until_interrupted(
    watch: Callable[[], str | None] | None = None, interval: float = 1.0, sleep=time.sleep, pause=signal.pause
) -> None:
    """Wait for Ctrl-C; with a `watch`, ask it every `interval` seconds and raise RuntimeError with the problem it reports."""
    try:
        if watch is None:
            pause()
            return
        while True:
            problem = watch()
            if problem:
                raise RuntimeError(problem)
            sleep(interval)
    except KeyboardInterrupt:
        pass


def free_port() -> int:
    """Return a TCP port that was free on 127.0.0.1 a moment ago."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
