import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier0

ENGINE = Path(__file__).resolve().parents[1] / "kaomoji.bash"


class TestTextWidth:
    @pytest.mark.parametrize(("text", "cells"), [("蓬", 2), ("ノ", 2), ("Ｏ", 2), ("ﾉ", 1), ("◕", 1), ("a", 1), ("", 0)])
    def test_counts_wide_characters_twice(self, text, cells):
        assert bash(f'kaomoji_text_width "{text}"; printf %s "$REPLY"') == str(cells)

    def test_sums_a_string(self):
        assert bash('kaomoji_text_width "─=≡▰▩▩[ 蓬•ｏ•]⊐"; printf %s "$REPLY"') == "16"


class TestPaint:
    SPRITE = "sprite=(\"/\"$'\\t'a \"1/\"$'\\t'蓬 dim$'\\t'b)"

    def test_prints_the_graphemes_and_reports_their_width(self):
        assert bash(f'{self.SPRITE}; kaomoji_paint sprite; printf " %s" "$REPLY"') == "a蓬b 4"

    def test_offset_drops_graphemes_from_the_left(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint --offset 1 sprite") == "蓬b"

    def test_negative_offset_pads_the_left(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint --offset -2 sprite") == "  a蓬b"

    def test_width_pads_the_right_and_is_reported(self):
        assert bash(f'{self.SPRITE}; kaomoji_paint --width 6 sprite; printf " %s" "$REPLY"') == "a蓬b   6"

    def test_clip_drops_what_does_not_fit(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint --clip 3 sprite") == "a蓬"

    class TestColor:
        def test_applies_the_styles(self):
            out = bash(f"{TestPaint.SPRITE}; kaomoji_paint --color sprite")

            assert out.startswith("a\x1b(B\x1b[m\x1b[31m蓬\x1b(B\x1b[m\x1b[2mb")

        def test_skips_colors_the_terminal_lacks(self):
            out = bash("sprite=(\"9/\"$'\\t'x); kaomoji_paint --color sprite", term="xterm")

            assert out == "x\x1b(B\x1b[m"


class TestMain:
    def test_help_prints_the_calling_scripts_header(self, kaomoji):
        result = kaomoji("hero").run("--help")

        assert result.returncode == 0
        assert result.stdout.startswith("Purpose: Render the Pi Hero kaomoji")

    def test_rejects_unknown_options_with_a_hint(self, kaomoji):
        result = kaomoji("hero").run("--bogus")

        assert result.returncode == 2
        assert result.stderr == "hero: unknown option: --bogus\nSee 'hero --help'\n"

    def test_rejects_unknown_moods(self, kaomoji):
        result = kaomoji("hero").run("--mood", "grumpy")

        assert result.returncode == 2
        assert "unknown mood: grumpy" in result.stderr

    def test_exit_needs_loops(self, kaomoji):
        result = kaomoji("hero").run("--mood", "happy", "--animate", "--exit")

        assert result.returncode == 2
        assert "--exit needs --loops" in result.stderr

    def test_is_plain_when_stdout_is_no_terminal(self, kaomoji):
        result = kaomoji("hero").run("--mood", "happy")

        assert result.stdout == "─=≡▰▩▩[✿＾ｖ＾]⊐\n"

    def test_colors_on_request(self, kaomoji):
        result = kaomoji("hero").run("--mood", "happy", "--color")

        assert "\x1b[38;5;214m" in result.stdout


def bash(snippet: str, term: str = "xterm-256color") -> str:
    env = {**os.environ, "TERM": term}
    return subprocess.run(["bash", "-c", f". '{ENGINE}'; {snippet}"], capture_output=True, text=True, env=env, check=True).stdout
