import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.tier0, pytest.mark.usefixtures("binary")]

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE / "kaomoji-gif"
BINARY = str(PACKAGE / ".build" / "kaomoji")
HERO, WIZARD = [BINARY, "hero"], [BINARY, "wizard"]
ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
CIVIS, CNORM = "\x1b[?25l", "\x1b[?25h"
needs_asciinema = pytest.mark.skipif(shutil.which("asciinema") is None, reason="needs asciinema")
needs_agg = pytest.mark.skipif(shutil.which("agg") is None, reason="needs agg")


class TestArguments:
    def test_prints_the_usage_without_a_command(self):
        result = run()

        assert result.returncode == 2
        assert "Usage:" in result.stderr

    def test_rejects_unknown_options(self):
        result = run("--margin", "5", "--", *HERO)

        assert result.returncode == 2
        assert "unknown option: --margin" in result.stderr

    @needs_asciinema
    def test_fails_with_the_commands_message(self, fake_agg):
        result = run("--", *HERO, "--mood", "dragon", path=fake_agg.directory)

        assert result.returncode == 2
        assert "unknown mood: dragon" in result.stderr


@needs_asciinema
class TestCast:
    def test_holds_every_frame_at_the_pictures_size(self, tmp_path, fake_agg):
        cast = tmp_path / "wizard.cast"

        result = run("--cast", str(cast), "--output", str(tmp_path / "wizard.gif"), "--", *WIZARD, "--mood", "happy", "--animate", "--no-entrance", "--loops", "1", path=fake_agg.directory)

        assert result.returncode == 0, result.stderr
        header, events = read_cast(cast)
        frames = [data for _, data in events if ESCAPES.sub("", data).strip()]
        assert header["width"] == 19 and header["height"] == 3
        assert len(frames) == 21
        assert "(＾∀＾)つ─" in ESCAPES.sub("", frames[-1])
        assert CNORM not in events[-1][1] and not events[-1][1].endswith("\n")
        assert events[-1][1].endswith(CIVIS)

    def test_holds_the_last_frame_for_the_frames_it_repeats_and_one_more(self, tmp_path, fake_agg):
        cast = tmp_path / "hero.cast"

        result = run("--cast", str(cast), "--output", str(tmp_path / "hero.gif"), "--", *HERO, "--animate", "--no-entrance", "--loops", "1", path=fake_agg.directory)

        assert result.returncode == 0, result.stderr
        _, events = read_cast(cast)
        times, frames = [t for t, _ in events], [data.removesuffix(CIVIS) for _, data in events]
        repeated = next(i for i in range(len(frames) - 1, -1, -1) if frames[i] != frames[-1]) + 1
        expected = times[-1] - times[-2] + times[-1] - times[repeated]
        assert repeated < len(frames) - 1, "the hero's last pose is held for several frames"
        assert abs(fake_agg.option("--last-frame-duration") - expected) < 0.002

    def test_keeps_a_leaving_hero_in_its_own_box(self, tmp_path, fake_agg):
        cast = tmp_path / "hero.cast"

        result = run("--cast", str(cast), "--output", str(tmp_path / "hero.gif"), "--padding", "0", "--", *HERO, "--no-color", "--loops", "1", "--exit", "--frame-ms", "0", path=fake_agg.directory)

        assert result.returncode == 0, result.stderr
        header, events = read_cast(cast)
        # at --frame-ms 0 the pty may hand asciinema two writes as one event, so frames are split at their carriage return
        drawn = [frame for _, data in events for frame in ESCAPES.sub("", data).split("\r") if frame.strip()]
        assert header["width"] == 16
        assert drawn[-1] == " " * 15 + "-"

    def test_hides_the_cursor_in_a_still_and_holds_it_for_a_second(self, tmp_path, fake_agg):
        cast = tmp_path / "hero.cast"

        result = run("--cast", str(cast), "--output", str(tmp_path / "hero.gif"), "--padding", "2x1", "--", *HERO, "--mood", "happy", path=fake_agg.directory)

        assert result.returncode == 0, result.stderr
        header, events = read_cast(cast)
        assert header["width"] == 16 + 4 and header["height"] == 1 + 2
        assert len(events) == 1
        assert ESCAPES.sub("", events[0][1]) == "\r\n  ─=≡▰▩▩[✿＾ｖ＾]━"
        assert events[0][1].endswith(CIVIS)
        assert fake_agg.option("--last-frame-duration") == 1.0

    def test_passes_the_look_on_to_agg(self, tmp_path, fake_agg):
        gif = tmp_path / "hero.gif"

        result = run("--output", str(gif), "--font-family", "Menlo,Apple Symbols", "--font-size", "24", "--line-height", "1.2", "--theme", "nord", "--hold", "0.5", "--", *HERO, path=fake_agg.directory)

        assert result.returncode == 0, result.stderr
        args = fake_agg.calls()
        assert args[-1] == str(gif)
        assert args[args.index("--font-family") + 1] == "Menlo,Apple Symbols"
        assert args[args.index("--font-size") + 1] == "24"
        assert args[args.index("--line-height") + 1] == "1.2"
        assert args[args.index("--theme") + 1] == "nord"
        assert fake_agg.option("--last-frame-duration") == 0.5
        assert result.stdout == f"{gif}: 1 event on 18x3 cells\n"


    def test_names_the_gif_after_the_character_when_the_command_is_the_binary(self, tmp_path, fake_agg, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = run("--", *HERO, "--mood", "happy", path=fake_agg.directory)

        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith("hero.gif: ")


@needs_asciinema
@needs_agg
class TestRendering:
    def test_writes_the_gif(self, tmp_path):
        gif = tmp_path / "hero.gif"

        result = run("--output", str(gif), "--", *HERO, "--mood", "happy")

        assert result.returncode == 0, result.stderr
        assert gif.read_bytes().startswith(b"GIF89a")


def run(*args: str, path: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if path:
        env["PATH"] = f"{path}:{env['PATH']}"
    return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, env=env)


def read_cast(path: Path) -> tuple[dict, list[tuple[float, str]]]:
    header, *events = [json.loads(line) for line in path.read_text().splitlines()]
    return header, [(time, data) for time, kind, data in events if kind == "o"]


class FakeAgg:
    """An agg on PATH that logs its arguments and writes an empty GIF."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.log = directory / "calls"
        fake = directory / "agg"
        fake.write_text(f'#!/bin/sh\nprintf \'%s\\n\' "$@" > "{self.log}"\nfor last; do :; done\n: > "$last"\n')
        fake.chmod(0o755)

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines()

    def option(self, name: str) -> float:
        args = self.calls()
        return float(args[args.index(name) + 1])


@pytest.fixture
def fake_agg(tmp_path):
    return FakeAgg(tmp_path)
