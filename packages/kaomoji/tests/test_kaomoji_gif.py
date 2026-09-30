import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier0

SCRIPT = Path(__file__).resolve().parents[1] / "kaomoji-gif"
ESCAPES = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\(B")


class TestArguments:
    def test_wants_the_character_first(self):
        result = run("--mood", "happy")

        assert result.returncode == 2
        assert "the character comes first: --mood" in result.stderr

    def test_rejects_unknown_characters(self):
        result = run("dragon")

        assert result.returncode == 2
        assert "no such character: dragon" in result.stderr

    def test_refuses_endless_animations(self):
        result = run("hero", "--mood", "happy", "--animate", "--loops", "-1")

        assert result.returncode == 2
        assert "endless animations can't be rendered" in result.stderr


@pytest.mark.skipif(shutil.which("agg") is None, reason="needs agg")
class TestRendering:
    def test_writes_the_gif_and_a_cast_of_every_frame(self, tmp_path):
        gif, cast = tmp_path / "wizard.gif", tmp_path / "wizard.cast"

        result = run("wizard", "--output", str(gif), "--cast", str(cast), "--mood", "happy", "--animate", "--no-entrance")

        assert result.returncode == 0, result.stderr
        assert gif.read_bytes().startswith(b"GIF89a")
        header, *events = [json.loads(line) for line in cast.read_text().splitlines()]
        assert header["width"] == 19 and header["height"] == 3
        assert len(events) == 21
        assert "(＾∀＾)つ─" in ESCAPES.sub("", events[-1][2])


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True)
