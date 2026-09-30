import os
import re
import subprocess
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\(B")
CUU1 = "\x1b[A"


class Kaomoji:
    """Runs a kaomoji script on a 256-color terminal and takes its output apart."""

    def __init__(self, script: str, term: str = "xterm-256color"):
        self.script = PACKAGE / script
        self.term = term

    def run(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "TERM": self.term}
        env.pop("NO_COLOR", None)
        result = subprocess.run([str(self.script), *args], capture_output=True, env=env)
        # decoded by hand: text mode would turn the \r between frames into newlines
        return subprocess.CompletedProcess(result.args, result.returncode, result.stdout.decode(), result.stderr.decode())

    def static(self, mood: str) -> str:
        return self.run("--mood", mood, "--no-color").stdout.rstrip("\n")

    def frames(self, *args: str, color: bool = False) -> list[str]:
        """The frames of a single-line animation, one per step, escape sequences stripped unless colored."""
        out = self.run("--animate", "--color" if color else "--no-color", "--frame-ms", "0", *args).stdout
        chunks = out.split("\r")[1:]  # before the first \r the cursor is only hidden
        chunks[-1] = chunks[-1].split("\n")[0]  # the newline and the returning cursor end the animation
        return [c if color else ESCAPES.sub("", c) for c in chunks]

    def grid(self, *args: str) -> list[list[str]]:
        """The frames of a grid, each as its header line followed by one line per mood."""
        out = self.run("--frame-ms", "0", *args).stdout
        rows = 1 + 2 * len(self.moods())
        frames = []
        for chunk in out.split(CUU1 * rows):
            lines = [line for line in ESCAPES.sub("", chunk).split("\n") if line.strip()]
            frames.append(lines)
        return frames

    def moods(self) -> list[str]:
        line = next(l for l in self.run("--help").stdout.splitlines() if l.strip().startswith("--mood <mood>"))
        return line.split("One of", 1)[1].strip(" .").split(", ")


@pytest.fixture
def kaomoji():
    return Kaomoji
