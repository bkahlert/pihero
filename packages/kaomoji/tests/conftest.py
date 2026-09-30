import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\(B")
CUU1 = "\x1b[A"


class Kaomoji:
    """Runs a kaomoji script on a 256-color terminal and takes its output apart."""

    def __init__(self, script: str, term: str = "xterm-256color", path: Path | None = None):
        self.script = PACKAGE / script
        self.term = term
        self.path = path  # prepended to PATH, for a fake tput

    def run(self, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run([str(self.script), *args], capture_output=True, env=self.env())
        # decoded by hand: text mode would turn the \r between frames into newlines
        return subprocess.CompletedProcess(result.args, result.returncode, result.stdout.decode(), result.stderr.decode())

    def stopped(self, *args: str, signals: list[int], frame_mark: bytes = b"\r") -> subprocess.CompletedProcess:
        """Runs an endless animation and sends each signal once two more frames have shown."""
        proc = subprocess.Popen(
            [str(self.script), "--no-color", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env(), bufsize=0
        )
        out = b""
        for sig in signals:
            seen = out.count(frame_mark)
            while out.count(frame_mark) < seen + 2:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                out += chunk
            proc.send_signal(sig)
        rest, err = proc.communicate(timeout=10)
        return subprocess.CompletedProcess(proc.args, proc.returncode, (out + rest).decode(), err.decode())

    def static(self, mood: str) -> str:
        return self.run("--mood", mood, "--no-color").stdout.rstrip("\n")

    def frames(self, *args: str, color: bool = False) -> list[str]:
        """The frames of a single-line animation, one per step; --frame-ms implies --animate."""
        out = self.run("--color" if color else "--no-color", "--frame-ms", "0", *args).stdout
        return self.split_frames(out, color)

    @staticmethod
    def split_frames(out: str, color: bool = False) -> list[str]:
        """Splits an animation's output into its frames, escape sequences stripped unless colored."""
        chunks = out.split("\r")[1:]  # before the first \r the cursor is only hidden
        chunks[-1] = chunks[-1].split("\n")[0]  # the newline and the returning cursor end the animation
        return [c if color else ESCAPES.sub("", c) for c in chunks]

    def grid(self, *args: str) -> list[list[str]]:
        """The frames of the preview grid, each as its header line followed by one line per mood."""
        out = self.run("--preview", "--frame-ms", "0", *args).stdout
        return self.split_grid(out, 1 if "--mood" in args else len(self.moods()))

    @staticmethod
    def split_grid(out: str, moods: int) -> list[list[str]]:
        """Splits a preview's output at the cursor moving back up, into the non-empty lines of each redraw."""
        frames = []
        for chunk in out.split(CUU1 * (1 + 2 * moods)):
            lines = [line for line in ESCAPES.sub("", chunk).split("\n") if line.strip()]
            frames.append(lines)
        return frames

    def moods(self) -> list[str]:
        line = next(l for l in self.run("--help").stdout.splitlines() if l.strip().startswith("--mood <mood>"))
        return line.split("One of", 1)[1].split(" (")[0].strip(" .").split(", ")

    def env(self) -> dict[str, str]:
        env = {**os.environ, "TERM": self.term}
        env.pop("NO_COLOR", None)
        if self.path:
            env["PATH"] = f"{self.path}:{env['PATH']}"
        return env


class TputLog:
    """A tput on PATH that logs every call before running the real one."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.log = directory / "calls"
        fake = directory / "tput"
        fake.write_text(f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{self.log}"\nexec {shutil.which("tput")} "$@"\n')
        fake.chmod(0o755)

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []


@pytest.fixture
def kaomoji():
    return Kaomoji


@pytest.fixture
def tput_log(tmp_path):
    return TputLog(tmp_path)
