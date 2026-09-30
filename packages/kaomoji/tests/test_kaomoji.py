import os
import re
import signal
import subprocess
import time
import unicodedata
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier0

PACKAGE = Path(__file__).resolve().parents[1]
ENGINE = PACKAGE / "kaomoji.bash"


class TestTextWidth:
    @pytest.mark.parametrize(("text", "cells"), [("蓬", 2), ("ノ", 2), ("Ｏ", 2), ("ﾉ", 1), ("◕", 1), ("a", 1), ("", 0)])
    def test_counts_wide_characters_twice(self, text, cells):
        assert bash(f'kaomoji_text_width "{text}"; printf %s "$REPLY"') == str(cells)

    def test_sums_a_string(self):
        assert bash('kaomoji_text_width "─=≡▰▩▩[ 蓬•ｏ•]⊐"; printf %s "$REPLY"') == "16"


class TestPaint:
    SPRITE = "sprite=(\"/\"$'\\t'a \"1/\"$'\\t'蓬 dim$'\\t'b)"
    RESULT = '; printf "%s %s" "$KAOMOJI_TEXT" "$KAOMOJI_WIDTH"'

    def test_leaves_the_text_and_its_width_in_cells(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint sprite{self.RESULT}") == "a蓬b 4"

    def test_offset_drops_graphemes_from_the_left(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint --offset 1 sprite{self.RESULT}") == "蓬b 3"

    def test_negative_offset_pads_the_left(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint --offset -2 sprite{self.RESULT}") == "  a蓬b 6"

    def test_clip_drops_what_does_not_fit(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint --clip 3 sprite{self.RESULT}") == "a蓬 3"

    class TestColor:
        def test_applies_the_styles(self):
            out = bash(f"{TestPaint.SPRITE}; kaomoji_paint --color sprite{TestPaint.RESULT}")

            assert out.startswith("a\x1b(B\x1b[m\x1b[31m蓬\x1b(B\x1b[m\x1b[2mb")
            assert out.endswith(" 4")

        def test_skips_colors_the_terminal_lacks(self):
            out = bash("sprite=(\"9/\"$'\\t'x); kaomoji_paint --color sprite" + TestPaint.RESULT, term="xterm")

            assert out == "x\x1b(B\x1b[m 1"


class TestFrameCache:
    COUNTING_HERO = (
        f". '{PACKAGE}/hero'; "
        'eval "original_$(declare -f hero_frame)"; renders=0; '
        'hero_frame() { renders=$((renders + 1)); original_hero_frame "$@"; }; '
    )

    def test_renders_each_hover_frame_once_however_many_loops(self):
        out = bash(self.COUNTING_HERO + 'kaomoji_animate hero --no-entrance --loops 3 --frame-ms 0 >/dev/null; printf %s "$renders"')

        assert out == "12"

    def test_renders_the_preview_frames_once_however_many_loops(self):
        out = bash(self.COUNTING_HERO + 'kaomoji_grid hero --mood happy --no-entrance --loops 2 --frame-ms 0 >/dev/null; printf %s "$renders"')

        assert out == str(1 + 1 + 12 + 12 + 1)  # static plain and color, a hover cycle plain and color, the landing frame measured


class TestCapabilities:
    def test_fetches_several_in_one_tput_call(self):
        out = bash('kaomoji_tput civis el cuu1; printf "%s|%s|%s" "${KAOMOJI_CAP[civis]}" "${KAOMOJI_CAP[el]}" "${KAOMOJI_CAP[cuu1]}"')

        assert out == "|".join(tput(cap) for cap in ["civis", "el", "cuu1"])

    def test_counts_the_colors(self):
        assert bash('kaomoji_tput colors; printf %s "${KAOMOJI_CAP[colors]}"') == "256"

    def test_static_plain_output_runs_no_tput(self, kaomoji, tput_log):
        kaomoji("hero", path=tput_log.directory).run("--no-color")

        assert tput_log.calls() == []

    def test_a_colored_frame_takes_three_calls(self, kaomoji, tput_log):
        kaomoji("hero", path=tput_log.directory).run("--mood", "happy", "--color")

        assert len(tput_log.calls()) == 3  # sgr0 as the separator, the color count, the palette

    def test_a_colored_animation_takes_three_calls(self, kaomoji, tput_log):
        kaomoji("hero", path=tput_log.directory).run("--color", "--no-entrance", "--loops", "1", "--frame-ms", "0")

        assert len(tput_log.calls()) == 3


class TestPacing:
    def test_holds_every_frame_for_the_frame_time(self, kaomoji):
        started = time.monotonic()
        frames = kaomoji("hero").frames("--no-entrance", "--loops", "1", "--frame-ms", "40")
        elapsed = time.monotonic() - started

        assert len(frames) == 12
        assert elapsed >= 11 * 0.040

    def test_absorbs_the_render_time_of_a_frame(self):
        started = time.monotonic()
        out = bash(
            "SLOW_MOODS=(only); slow_timeline() { local -n out=$3; out=(0 10 0); }; "
            "slow_frame() { sleep 0.03; printf x; }; "
            "kaomoji_animate slow --no-entrance --loops 1 --frame-ms 40 | tr -cd x | wc -c"
        )
        elapsed = time.monotonic() - started

        assert out.strip() == "10"
        assert 9 * 0.040 <= elapsed < 10 * 0.070 - 0.05


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

        def test_lines_up_a_face_narrower_than_the_titles_under_them(self, kaomoji):
            header, *rows = kaomoji("visitor").grid("--loops", "1")[-1]

            titles = ["static plain", "static color", "animated plain", "animated color"]
            title_columns = [columns(header[: header.index(title)]) for title in titles]
            for row in rows:
                assert [columns(row[: wall.start()]) for wall in re.finditer("┴┬┴┤", row)] == title_columns


def columns(text: str) -> int:
    """Display width, counting East Asian wide and fullwidth characters twice like the engine does."""
    return sum(2 if unicodedata.east_asian_width(c) in "FW" else 1 for c in text)


def tput(capability: str, term: str = "xterm-256color") -> str:
    return subprocess.run(["tput", capability], capture_output=True, text=True, env={**os.environ, "TERM": term}).stdout


def bash(snippet: str, term: str = "xterm-256color") -> str:
    env = {**os.environ, "TERM": term}
    return subprocess.run(["bash", "-c", f". '{ENGINE}'; {snippet}"], capture_output=True, text=True, env=env, check=True).stdout
