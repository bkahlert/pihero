"""The session record: what a preview started, so a killed one is cleaned up by the next and a second one is refused."""

import json
import os
import shutil
import signal
import time
from collections.abc import Callable
from pathlib import Path

from . import process

ENDED_BY = (("qemu", "terminate"), ("dev_server", "terminate-group"), ("tunnel", "terminate"))


class AlreadyRunning(RuntimeError):
    """Raised when a second preview is started next to a running one."""


def stale_actions(record: dict, alive=process.alive) -> list[tuple[str, object]]:
    """Return what a killed preview left behind that must be ended; raise AlreadyRunning while its owner still runs."""
    owner = record.get("owner")
    if owner and alive(owner):
        raise AlreadyRunning(f"a preview is already running (process {owner[0]}); end it with Ctrl-C first")
    actions: list[tuple[str, object]] = []
    for key, action in ENDED_BY:
        entry = record.get(key)
        if entry and alive(entry):
            actions.append((action, entry[0]))
    if record.get("device"):
        actions.append(("restore-device", record["device"]))
    if record.get("backend"):
        actions.append(("stop-backend", None))
    return actions


def carry_out(actions, stop_backend: Callable[[], None], restore_board: Callable[[str], bool], *, kill=os.kill, killpg=os.killpg, getpgid=os.getpgid, info=process.info, sleep=time.sleep, clock=time.monotonic) -> str | None:
    """Carry out `actions`, wait until the ended processes are gone, and return the board whose restore failed (None when none did); a process that ended meanwhile is skipped."""
    ended = []
    failed = None
    for action, subject in actions:
        try:
            if action == "terminate":
                kill(subject, signal.SIGTERM)
                ended.append(subject)
            elif action == "terminate-group":
                killpg(getpgid(subject), signal.SIGTERM)
                ended.append(subject)
            elif action == "restore-device":
                if not restore_board(subject):
                    failed = subject
            elif action == "stop-backend":
                stop_backend()
        except ProcessLookupError:
            pass
    process.wait_until_gone(ended, info, sleep=sleep, clock=clock)
    return failed


class Record:
    """The record under one app's state directory: `session.json`, and the session directory next to it."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "session.json"
        self.session_dir = directory / "session"

    def read(self) -> dict:
        """Return the record, empty when missing, unreadable or not a JSON object."""
        try:
            content = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return content if isinstance(content, dict) else {}

    def claim(self, stop_backend: Callable[[], None], restore_board: Callable[[str], bool], *, alive=process.alive, info=process.info, kill=os.kill, killpg=os.killpg, getpgid=os.getpgid, sleep=time.sleep, clock=time.monotonic) -> None:
        """End what a killed preview left behind, delete its session directory, and record this process as the owner, keeping a board whose restore failed; raise AlreadyRunning next to a live one."""
        self.directory.mkdir(parents=True, exist_ok=True)
        device = None
        if self.path.exists():
            device = carry_out(stale_actions(self.read(), alive), stop_backend, restore_board, kill=kill, killpg=killpg, getpgid=getpgid, info=info, sleep=sleep, clock=clock)
            shutil.rmtree(self.session_dir, ignore_errors=True)
        owner = {"owner": process.entry(os.getpid(), info)}
        self._write({**owner, "device": device} if device else owner)

    def update(self, **fields) -> None:
        """Add `fields` to the record."""
        self._write({**self.read(), **fields})

    def forget(self) -> None:
        """Delete the record, keeping only a board that still runs the session so the next start retries its restore."""
        device = self.read().get("device")
        if device:
            self._write({"device": device})
        else:
            self.path.unlink(missing_ok=True)

    def _write(self, content: dict) -> None:
        # A preview killed mid-write must leave the previous record, not a truncated one the next start reads as empty.
        temporary = self.directory / "session.json.tmp"
        temporary.write_text(json.dumps(content))
        os.replace(temporary, self.path)
