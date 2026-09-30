import os
import signal
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

    def test_renders_the_first_mood_by_default(self, kaomoji):
        result = kaomoji("hero").run()

        assert result.stdout == "─=≡▰▩▩[ 蓬•ｏ•]⊐\n"

    def test_is_plain_when_stdout_is_no_terminal(self, kaomoji):
        result = kaomoji("hero").run("--mood", "happy")

        assert result.stdout == "─=≡▰▩▩[✿＾ｖ＾]⊐\n"

    def test_colors_on_request(self, kaomoji):
        result = kaomoji("hero").run("--mood", "happy", "--color")

        assert "\x1b[38;5;214m" in result.stdout

    class TestAnimate:
        def test_is_off_by_default(self, kaomoji):
            result = kaomoji("hero").run("--mood", "happy")

            assert "\r" not in result.stdout

        @pytest.mark.parametrize("option", [["--no-entrance"], ["--exit"], ["--frame-ms", "0"]])
        def test_is_implied_by_the_animation_options(self, kaomoji, option):
            result = kaomoji("hero").run(*option, "--loops", "1")

            assert result.returncode == 0
            assert result.stdout.count("\r") > 1

        def test_is_implied_by_loops(self, kaomoji):
            result = kaomoji("hero").run("--loops", "1", "--frame-ms", "0")

            assert result.stdout.count("\r") > 1

    class TestExitWhileEndless:
        @pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM])
        def test_plays_the_exit_when_stopped(self, kaomoji, stop):
            result = kaomoji("visitor").stopped("--exit", "--no-entrance", "--frame-ms", "20", signals=[stop])

            assert result.returncode == 0
            assert kaomoji.split_frames(result.stdout)[-4:] == ["┬┴┤", "┴┤", "┤", ""]

        def test_quits_at_once_on_a_second_interrupt(self, kaomoji):
            result = kaomoji("visitor").stopped("--exit", "--no-entrance", "--frame-ms", "50", signals=[signal.SIGINT] * 2)

            drawn = [frame for frame in kaomoji.split_frames(result.stdout) if frame]
            assert result.returncode == 130
            assert drawn[-1].startswith("┴┬┴┤")

    class TestPreview:
        def test_shows_a_grid_of_every_mood(self, kaomoji):
            header, *rows = kaomoji("hero").grid("--loops", "1")[-1]

            assert header.split()[0] == "mood"
            assert [row.split()[0] for row in rows] == ["neutral", "happy", "sad", "unknown"]

        def test_narrows_to_the_given_mood(self, kaomoji):
            header, *rows = kaomoji("hero").grid("--mood", "happy", "--loops", "1")[-1]

            assert [row.split()[0] for row in rows] == ["happy"]


def bash(snippet: str, term: str = "xterm-256color") -> str:
    env = {**os.environ, "TERM": term}
    return subprocess.run(["bash", "-c", f". '{ENGINE}'; {snippet}"], capture_output=True, text=True, env=env, check=True).stdout
