import os
import platform
import re
import subprocess
import time
from pathlib import Path

import pytest

from pihero_testkit import tools

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE / "kaomoji.go"
BINARY = PACKAGE / ".build" / "kaomoji"
ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[78]")  # CSI sequences, save and restore cursor
CIVIS, CNORM, CUU1 = "\x1b[?25l", "\x1b[?25h", "\x1b[A"


@pytest.fixture(scope="session")
def binary() -> Path:
    """The binary for this machine, built through the tools image when the source is newer than the last build."""
    if not BINARY.exists() or BINARY.stat().st_mtime < SOURCE.stat().st_mtime:
        BINARY.parent.mkdir(exist_ok=True)
        goos = {"Darwin": "darwin", "Linux": "linux"}[platform.system()]
        goarch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}[platform.machine()]
        tools.run(
            ["env", f"GOOS={goos}", f"GOARCH={goarch}", "CGO_ENABLED=0", "go", "build", "-trimpath", "-ldflags", "-s -w -X main.version=test",
             "-o", f"/work/{BINARY.relative_to(Path.cwd())}", f"/work/{SOURCE.relative_to(Path.cwd())}"],
            mounts=[tools.GO_CACHE],
        )
    return BINARY


class Kaomoji:
    """Runs the binary for one character, or without one, on a 256-color terminal and takes its output apart."""

    def __init__(self, binary: Path, character: str | None = None, term: str = "xterm-256color", columns: int = 80, env: dict[str, str] | None = None):
        self.binary = binary
        self.character = character
        self.term = term
        self.columns = columns  # the terminal's width, as COLUMNS reports it to a program without a terminal
        self.extra_env = env or {}

    def command(self, *args: str) -> list[str]:
        return [str(self.binary), *([self.character] if self.character else []), *args]

    def run(self, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(self.command(*args), capture_output=True, env=self.env())
        # decoded by hand: text mode would turn the \r between frames into newlines
        return subprocess.CompletedProcess(result.args, result.returncode, result.stdout.decode(), result.stderr.decode())

    def stopped(self, *args: str, signals: list[int], frame_mark: bytes = b"\r") -> subprocess.CompletedProcess:
        """Runs an endless animation and sends each signal once two more frames have shown."""
        proc = subprocess.Popen(self.command("--no-color", *args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env(), bufsize=0)
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

    def blocked(self, *args: str, signals: list[int]) -> subprocess.CompletedProcess:
        """Runs an animation into a pipe nobody reads, so that it blocks in a write, and sends each signal there."""
        proc = subprocess.Popen(self.command("--no-color", "--frame-ms", "0", *args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env(), bufsize=0)
        for sig in signals:
            time.sleep(0.5)  # the pipe is full and the program blocked long before that
            proc.send_signal(sig)
        out, err = proc.communicate(timeout=10)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out.decode(), err.decode())

    @staticmethod
    def plain(out: str) -> str:
        """The output without escape sequences."""
        return ESCAPES.sub("", out)

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
        env = {**os.environ, "TERM": self.term, "COLUMNS": str(self.columns)}
        for key in ("NO_COLOR", "COLORTERM", "KAOMOJI_COLUMNS"):
            env.pop(key, None)
        return {**env, **self.extra_env}


@pytest.fixture
def kaomoji(binary):
    def factory(character: str | None = None, **kwargs) -> Kaomoji:
        return Kaomoji(binary, character, **kwargs)

    factory.split_frames = Kaomoji.split_frames
    factory.split_grid = Kaomoji.split_grid
    factory.plain = Kaomoji.plain
    return factory
