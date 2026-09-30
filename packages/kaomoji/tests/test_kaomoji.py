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

    def test_count_paints_that_many_graphemes(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint --offset 1 --count 1 sprite{self.RESULT}") == "蓬 2"

    def test_clips_the_padding_of_a_negative_offset_too(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint --offset -2 --clip 3 sprite{self.RESULT}") == "  a 3"

    def test_drops_the_padding_once_nothing_is_left_to_position(self):
        assert bash(f"{self.SPRITE}; kaomoji_paint --offset -3 --clip 3 sprite{self.RESULT}") == " 0"

    def test_measures_each_grapheme_once_for_all_paintings_of_a_sprite(self):
        out = bash(
            f'{self.SPRITE}; eval "original_$(declare -f kaomoji_text_width)"; measured=0; '
            'kaomoji_text_width() { measured=$((measured + 1)); original_kaomoji_text_width "$@"; }; '
            "kaomoji_paint sprite; kaomoji_paint --offset 1 sprite; kaomoji_paint --clip 3 --color sprite; "
            'printf "%s %s" "$measured" "$KAOMOJI_TEXT"'
        )

        assert out == "3 a\x1b(B\x1b[m\x1b[31m蓬\x1b(B\x1b[m"

    class TestColor:
        def test_applies_the_styles(self):
            out = bash(f"{TestPaint.SPRITE}; kaomoji_paint --color sprite{TestPaint.RESULT}")

            assert out.startswith("a\x1b(B\x1b[m\x1b[31m蓬\x1b(B\x1b[m\x1b[2mb")
            assert out.endswith(" 4")

        def test_skips_colors_the_terminal_lacks(self):
            out = bash("sprite=(\"9/\"$'\\t'x); kaomoji_paint --color sprite" + TestPaint.RESULT, term="xterm")

            assert out == "x\x1b(B\x1b[m 1"


class TestSprite:
    def test_builds_a_sprite_once_for_the_same_arguments(self):
        out = bash(
            "builds=0; build() { builds=$((builds + 1)); local -n into=$3; into=(\"/\"$'\\t'\"$2\"); }; "
            "kaomoji_sprite a build --text x; kaomoji_sprite b build --text x; kaomoji_sprite c build --text y; "
            "printf '%s %s%s%s' \"$builds\" \"${a[0]#*$'\\t'}\" \"${b[0]#*$'\\t'}\" \"${c[0]#*$'\\t'}\""
        )

        assert out == "2 xxy"

    @pytest.mark.parametrize("name, poses", [("hero", 4), ("wizard", 7), ("visitor", 3)])
    def test_a_character_builds_one_sprite_per_pose(self, name, poses):
        out = bash(
            f". '{PACKAGE}/{name}'; "
            f'eval "original_$(declare -f {name}_sprite)"; builds=0; '
            f'{name}_sprite() {{ builds=$((builds + 1)); original_{name}_sprite "$@"; }}; '
            f'kaomoji_animate {name} --loops 1 --exit --frame-ms 0 >/dev/null; printf %s "$builds"'
        )

        assert out == str(poses)


class TestWarm:
    def test_builds_and_lays_out_every_pose_of_a_mood(self):
        out = bash(f". '{PACKAGE}/visitor'; kaomoji_warm visitor neutral; printf '%s %s %s' \"${{#KAOMOJI_SPRITES[@]}}\" \"${{#KAOMOJI_LAYOUTS[@]}}\" \"${{#KAOMOJI_COLORED[@]}}\"")

        assert out == "3 3 0"

    def test_colors_the_layouts_on_request(self):
        out = bash(f". '{PACKAGE}/hero'; kaomoji_warm hero neutral --color; printf '%s %s' \"${{#KAOMOJI_SPRITES[@]}}\" \"${{#KAOMOJI_COLORED[@]}}\"")

        assert out == "4 4"

    def test_an_animation_builds_every_pose_before_its_first_frame(self):
        out = bash(
            f". '{PACKAGE}/hero'; "
            'eval "original_$(declare -f hero_sprite)"; builds=0; '
            'hero_sprite() { builds=$((builds + 1)); original_hero_sprite "$@"; }; '
            'at_first_pause=""; kaomoji_sleep_ms() { at_first_pause=${at_first_pause:-$builds}; }; '
            'kaomoji_animate hero --loops 1 --exit --frame-ms 0 >/dev/null; printf "%s %s" "$at_first_pause" "$builds"'
        )

        assert out == "4 4"


class TestFrameCache:
    COUNTING_HERO = (
        f". '{PACKAGE}/hero'; "
        'eval "original_$(declare -f hero_frame)"; renders=0; '
        'hero_frame() { renders=$((renders + 1)); original_hero_frame "$@"; }; '
    )

    def test_renders_each_hover_frame_once_however_many_loops(self):
        out = bash(self.COUNTING_HERO + 'kaomoji_animate hero --no-entrance --loops 3 --frame-ms 0 >/dev/null; printf %s "$renders"')

        assert out == "12"

    def test_renders_ahead_while_there_is_time(self):
        out = bash(
            "SLOW_MOODS=(only); slow_timeline() { local -n out=$3; out=(2 4 3); }; slow_pose() { local -n s=$3; s=(); }; rendered=(); "
            'slow_frame() { local step; while [ $# -gt 0 ]; do case $1 in --step) step=$2; shift 2 ;; *) shift ;; esac; done; rendered+=("$step"); KAOMOJI_TEXT=x; KAOMOJI_WIDTH=1; }; '
            'pauses=(); kaomoji_sleep_ms() { pauses+=("${rendered[*]}"); }; '  # no waiting: the whole frame time is left for rendering ahead
            'kaomoji_animate slow --loops 1 --exit --frame-ms 40 >/dev/null; printf "%s" "${pauses[0]}"'
        )

        assert out == "0 1 2 3 4 5 6 7 8 9"  # everything up to the last frame, at the first pause

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
            "SLOW_MOODS=(only); slow_timeline() { local -n out=$3; out=(0 10 0); }; slow_pose() { local -n s=$3; s=(); }; "
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

    class TestSlowTerminal:
        """A signal interrupts a write the terminal has not taken yet; the frame is completed and the signal handled."""

        def test_the_preview_finishes_the_redraw_and_quits(self, kaomoji):
            result = kaomoji("hero").blocked("--preview", signals=[signal.SIGINT])

            assert result.stderr == ""
            assert result.returncode == 130
            assert len(kaomoji.split_grid(result.stdout, 4)[-1]) == 1 + 4
            assert kaomoji.plain(result.stdout).endswith("\n\n") and result.stdout.endswith(tput("cnorm"))

        def test_an_endless_animation_plays_the_exit(self, kaomoji):
            result = kaomoji("visitor").blocked("--exit", "--no-entrance", signals=[signal.SIGTERM])

            assert result.stderr == ""
            assert result.returncode == 0
            assert kaomoji.split_frames(result.stdout)[-4:] == ["┬┴┤", "┴┤", "┤", ""]

        def test_an_animation_quits_at_once(self, kaomoji):
            result = kaomoji("hero").blocked("--no-entrance", signals=[signal.SIGINT])

            assert result.stderr == ""
            assert result.returncode == 130
            assert result.stdout.endswith("\n" + tput("cnorm"))

    class TestPreview:
        def test_shows_a_grid_of_every_mood(self, kaomoji):
            header, *rows = kaomoji("hero").grid("--loops", "1")[-1]

            assert header.split()[0] == "mood"
            assert [row.split()[0] for row in rows] == ["neutral", "happy", "sad", "unknown"]

        def test_narrows_to_the_given_mood(self, kaomoji):
            header, *rows = kaomoji("hero").grid("--mood", "happy", "--loops", "1")[-1]

            assert [row.split()[0] for row in rows] == ["happy"]

        def test_leaves_the_cursor_below_the_grid_when_interrupted(self, kaomoji):
            result = kaomoji("hero").stopped("--preview", "--frame-ms", "20", signals=[signal.SIGINT], frame_mark=tput("cuu1").encode())

            assert result.returncode == 130
            assert len(kaomoji.split_grid(result.stdout, 4)[-1]) == 1 + 4  # the header and every row, redrawn completely
            assert kaomoji.plain(result.stdout).endswith("\n\n") and result.stdout.endswith(tput("cnorm"))

        def test_lines_up_a_face_narrower_than_the_titles_under_them(self, kaomoji):
            header, *rows = kaomoji("visitor").grid("--loops", "1")[-1]

            titles = ["static plain", "static color", "animated plain", "animated color"]
            title_columns = [columns(header[: header.index(title)]) for title in titles]
            for row in rows:
                assert [columns(row[: wall.start()]) for wall in re.finditer("┴┬┴┤", row)] == title_columns


class TestEngineLookup:
    @pytest.mark.parametrize("face", ["hero", "wizard", "visitor"])
    def test_a_face_started_without_a_directory_looks_for_the_installed_engine(self, face):
        if Path("/usr/lib/kaomoji/kaomoji.bash").exists():
            pytest.skip("the installed engine would be found")

        result = subprocess.run(["bash", face, "--no-color"], cwd=PACKAGE, capture_output=True, text=True)

        assert result.returncode == 1
        assert "/usr/lib/kaomoji/kaomoji.bash" in result.stderr


def columns(text: str) -> int:
    """Display width, counting East Asian wide and fullwidth characters twice like the engine does."""
    return sum(2 if unicodedata.east_asian_width(c) in "FW" else 1 for c in text)


def tput(capability: str, term: str = "xterm-256color") -> str:
    return subprocess.run(["tput", capability], capture_output=True, text=True, env={**os.environ, "TERM": term}).stdout


def bash(snippet: str, term: str = "xterm-256color") -> str:
    env = {**os.environ, "TERM": term}
    return subprocess.run(["bash", "-c", f". '{ENGINE}'; {snippet}"], capture_output=True, text=True, env=env, check=True).stdout
