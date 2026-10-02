import re
import signal
import time
import unicodedata

import pytest

CNORM, CUU1 = "\x1b[?25h", "\x1b[A"

pytestmark = pytest.mark.tier0

HERO = "─=≡▰▩▩[ 蓬•ｏ•]━"


class TestCommandLine:
    def test_help_names_the_cast(self, kaomoji):
        result = kaomoji().run("--help")

        assert result.returncode == 0
        assert result.stdout.startswith("Usage: kaomoji <character>")
        assert "hero, wizard, and visitor" in result.stdout

    def test_a_characters_help_is_its_header_with_its_moods(self, kaomoji):
        result = kaomoji("hero").run("--help")

        assert result.returncode == 0
        assert result.stdout.startswith("Purpose: Render the Pi Hero kaomoji")
        assert kaomoji("hero").moods() == ["neutral", "happy", "sad", "unknown"]

    def test_version_is_what_the_build_linked_in(self, kaomoji):
        result = kaomoji().run("--version")

        assert result.returncode == 0
        assert result.stdout == "test\n"

    def test_needs_a_character(self, kaomoji):
        result = kaomoji().run()

        assert result.returncode == 2
        assert result.stderr == "kaomoji: character missing\nSee 'kaomoji --help'\n"

    def test_rejects_an_unknown_character(self, kaomoji):
        result = kaomoji().run("dragon")

        assert result.returncode == 2
        assert result.stderr == "kaomoji: unknown character: dragon\nSee 'kaomoji --help'\n"

    def test_rejects_unknown_options_with_a_hint(self, kaomoji):
        result = kaomoji("hero").run("--bogus")

        assert result.returncode == 2
        assert result.stderr == "kaomoji: unknown option: --bogus\nSee 'kaomoji hero --help'\n"

    def test_rejects_unknown_moods(self, kaomoji):
        result = kaomoji("hero").run("--mood", "grumpy")

        assert result.returncode == 2
        assert "unknown mood: grumpy" in result.stderr

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            (["--loops", "many"], "--loops: not a number: many"),
            (["--frame-ms", "-1"], "--frame-ms: not a number: -1"),
            (["--mood"], "--mood: missing value"),
            (["--color=always"], "--color: takes no value"),
            (["--exit=no", "--loops", "0"], "--exit: takes no value"),
        ],
    )
    def test_rejects_a_bad_option_value(self, kaomoji, args, message):
        result = kaomoji("hero").run(*args)

        assert result.returncode == 2
        assert result.stderr == f"kaomoji: {message}\nSee 'kaomoji hero --help'\n"

    def test_renders_the_first_mood_by_default(self, kaomoji):
        assert kaomoji("hero").run().stdout == HERO + "\n"

    def test_is_plain_when_stdout_is_no_terminal(self, kaomoji):
        assert kaomoji("hero").run("--mood", "happy").stdout == "─=≡▰▩▩[✿＾ｖ＾]━\n"

    class TestAnimate:
        def test_is_off_by_default(self, kaomoji):
            assert "\r" not in kaomoji("hero").run("--mood", "happy").stdout

        @pytest.mark.parametrize("option", [["--no-entrance"], ["--exit"], ["--frame-ms", "0"], ["--animate"]])
        def test_is_implied_by_the_animation_options(self, kaomoji, option):
            result = kaomoji("hero").run(*option, "--loops", "1", "--frame-ms", "0")

            assert result.returncode == 0
            assert result.stdout.count("\r") > 1


class TestColor:
    def test_paints_the_heros_palette_by_index_on_a_256_color_terminal(self, kaomoji):
        out = kaomoji("hero").run("--mood", "happy", "--color").stdout

        assert "\x1b[38;5;214m" in out and "\x1b[48;5;221m" in out
        assert out.startswith("\x1b[2m─=≡\x1b[0m")  # the dim tail, one sequence for the three graphemes

    def test_paints_it_by_value_when_colorterm_says_truecolor(self, kaomoji):
        out = kaomoji("hero", env={"COLORTERM": "truecolor"}).run("--color").stdout

        assert "\x1b[38;2;246;181;53m" in out and "\x1b[48;2;247;220;56m" in out
        assert "38;5" not in out

    def test_drops_hex_colors_on_a_terminal_without_256_colors_but_keeps_the_basic_ones(self, kaomoji):
        hero = kaomoji("hero", term="xterm").run("--color").stdout
        wizard = kaomoji("wizard", term="xterm").run("--color").stdout

        assert "38;5" not in hero and "48;5" not in hero
        assert "\x1b[37m(" in wizard and "\x1b[91m｡" in wizard  # gray, and bright pink as 91

    def test_drops_the_whole_style_of_a_grapheme_when_the_terminal_lacks_one_of_its_colors(self, kaomoji):
        hero = kaomoji("hero", term="linux").run("--color").stdout  # the Pi's console: sixteen colors

        assert "\x1b[30m" not in hero  # black eyes on a yellow face that is not painted would vanish on a dark theme
        assert hero.startswith("\x1b[2m─=≡\x1b[0m")  # the dim tail needs no color and stays
        assert kaomoji.plain(hero) == HERO + "\n"

    def test_paints_fbterm_in_its_own_256_color_sequences(self, kaomoji):
        hero = kaomoji("hero", term="fbterm").run("--color").stdout  # the framebuffer terminal on shishakli's LCD
        wizard = kaomoji("wizard", term="fbterm").run("--color").stdout

        assert "\x1b[1;214}" in hero and "\x1b[2;221}" in hero  # fbterm ignores the standard 38;5 form
        assert "38;5" not in hero and "\x1b[0m" in hero
        assert "\x1b[1;7}(" in wizard

    def test_paints_the_basic_sixteen_as_the_terminal_sets_them(self, kaomoji):
        out = kaomoji("visitor").run("--color").stdout

        assert out.startswith("\x1b[2m┴┬┴┤\x1b[0m\x1b[97m")  # the dim wall, then white

    def test_survives_an_unset_term(self, kaomoji):
        result = kaomoji("hero", term="").run("--color")

        assert result.returncode == 0
        assert kaomoji.plain(result.stdout) == HERO + "\n"

    def test_no_color_wins_over_color(self, kaomoji):
        assert kaomoji("hero").run("--color", "--no-color").stdout == HERO + "\n"


class TestLine:
    """The cells a frame's line has, which the hero's exit crosses."""

    def test_follows_columns_less_the_last_one_without_a_terminal(self, kaomoji):
        frames = kaomoji("hero", columns=30).frames("--no-entrance", "--loops", "1", "--exit")

        assert len(frames) == 12 + 29

    def test_kaomoji_columns_zero_keeps_the_hero_to_its_own_width(self, kaomoji):
        frames = kaomoji("hero", env={"KAOMOJI_COLUMNS": "0"}).frames("--no-entrance", "--loops", "1", "--exit")

        assert len(frames) == 12 + 16
        assert frames[-2] == " " * 15 + "-" and frames[-1] == ""

    def test_kaomoji_columns_that_is_no_number_is_ignored(self, kaomoji):
        frames = kaomoji("hero", columns=30, env={"KAOMOJI_COLUMNS": "wide"}).frames("--no-entrance", "--loops", "1", "--exit")

        assert len(frames) == 12 + 29

    def test_a_line_narrower_than_the_hero_still_sees_it_leave(self, kaomoji):
        frames = kaomoji("hero", columns=10).frames("--loops", "1", "--exit")

        assert len(frames) == 1 + 16 + 12 + 9
        assert frames[-1] == ""


class TestPacing:
    def test_holds_every_frame_for_the_frame_time(self, kaomoji):
        started = time.monotonic()
        frames = kaomoji("hero").frames("--no-entrance", "--loops", "1", "--frame-ms", "40")
        elapsed = time.monotonic() - started

        assert len(frames) == 12
        assert elapsed >= 11 * 0.040

    def test_shows_the_first_frame_at_once(self, kaomoji):
        started = time.monotonic()
        kaomoji("hero").run("--no-color", "--no-entrance", "--loops", "0", "--frame-ms", "1000")
        elapsed = time.monotonic() - started

        assert elapsed < 0.5  # no warm-up: the landed frame is the whole animation with zero loops

    @pytest.mark.parametrize(("character", "entrance", "exit_"), [("hero", 16, 8), ("wizard", 15, 8), ("visitor", 9, 5)])
    def test_leaves_in_half_as_many_frame_times_as_it_entered(self, kaomoji, character, entrance, exit_):
        started = time.monotonic()
        frames = kaomoji(character).frames("--loops", "0", "--exit", "--frame-ms", "60")
        elapsed = time.monotonic() - started

        assert frames[0] == "" and frames[-1] == ""
        assert (entrance + exit_) * 0.06 - 0.1 <= elapsed < (entrance + exit_) * 0.06 + 0.15


class TestStopping:
    @pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM])
    def test_an_endless_animation_with_exit_plays_the_exit_when_stopped(self, kaomoji, stop):
        result = kaomoji("visitor").stopped("--exit", "--no-entrance", "--frame-ms", "20", signals=[stop])

        assert result.returncode == 0
        assert kaomoji.split_frames(result.stdout)[-4:] == ["┬┴┤", "┴┤", "┤", ""]
        assert result.stdout.endswith("\n" + CNORM)

    @pytest.mark.parametrize("character", ["wizard", "visitor"])
    def test_an_exit_begun_during_the_entrance_runs_it_backwards_from_there(self, kaomoji, character):
        result = kaomoji(character).stopped("--exit", "--frame-ms", "100", signals=[signal.SIGINT], after=5)

        frames = kaomoji.split_frames(result.stdout)
        rise = frames[: frames.index(max(frames, key=len)) + 1]
        assert result.returncode == 0
        assert 5 <= len(rise) <= 7, "the signal arrived while the character was still entering"
        assert frames == rise + rise[-2::-1]

    def test_quits_at_once_on_a_second_interrupt(self, kaomoji):
        result = kaomoji("visitor").stopped("--exit", "--no-entrance", "--frame-ms", "50", signals=[signal.SIGINT] * 2)

        drawn = [frame for frame in kaomoji.split_frames(result.stdout) if frame]
        assert result.returncode == 130
        assert drawn[-1].startswith("┴┬┴┤")

    @pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM])
    def test_an_animation_without_exit_quits_at_once(self, kaomoji, stop):
        result = kaomoji("hero").stopped("--no-entrance", "--frame-ms", "20", signals=[stop])

        assert result.returncode == 130
        assert result.stdout.endswith("\n" + CNORM)

    class TestSlowTerminal:
        """A signal arrives while a write to a full pipe blocks; the frame is completed and the signal handled."""

        def test_the_preview_finishes_the_redraw_and_quits(self, kaomoji):
            result = kaomoji("hero").blocked("--preview", signals=[signal.SIGINT])

            assert result.stderr == ""
            assert result.returncode == 130
            assert len(kaomoji.split_grid(result.stdout, 4)[-1]) == 1 + 4
            assert kaomoji.plain(result.stdout).endswith("\n\n") and result.stdout.endswith(CNORM)

        def test_an_endless_animation_plays_the_exit(self, kaomoji):
            result = kaomoji("visitor").blocked("--exit", "--no-entrance", signals=[signal.SIGTERM])

            assert result.stderr == ""
            assert result.returncode == 0
            assert kaomoji.split_frames(result.stdout)[-4:] == ["┬┴┤", "┴┤", "┤", ""]

        def test_an_animation_quits_at_once(self, kaomoji):
            result = kaomoji("hero").blocked("--no-entrance", signals=[signal.SIGINT])

            assert result.stderr == ""
            assert result.returncode == 130
            assert result.stdout.endswith("\n" + CNORM)


class TestPreview:
    def test_shows_a_grid_of_every_mood(self, kaomoji):
        header, *rows = kaomoji("hero").grid("--loops", "1")[-1]

        assert header.split()[0] == "mood"
        assert [row.split()[0] for row in rows] == ["neutral", "happy", "sad", "unknown"]

    def test_narrows_to_the_given_mood(self, kaomoji):
        header, *rows = kaomoji("hero").grid("--mood", "happy", "--loops", "1")[-1]

        assert [row.split()[0] for row in rows] == ["happy"]

    @pytest.mark.parametrize("args", [[], ["--exit"]])
    def test_quits_at_once_when_interrupted_and_leaves_the_cursor_below_the_grid(self, kaomoji, args):
        result = kaomoji("hero").stopped("--preview", *args, "--frame-ms", "20", signals=[signal.SIGINT], frame_mark=CUU1.encode())

        assert result.returncode == 130
        assert len(kaomoji.split_grid(result.stdout, 4)[-1]) == 1 + 4  # the header and every row, redrawn completely
        assert kaomoji.plain(result.stdout).endswith("\n\n") and result.stdout.endswith(CNORM)

    def test_lines_up_a_face_narrower_than_the_titles_under_them(self, kaomoji):
        header, *rows = kaomoji("visitor").grid("--loops", "1")[-1]

        titles = ["static plain", "static color", "animated plain", "animated color"]
        title_columns = [columns(header[: header.index(title)]) for title in titles]
        for row in rows:
            assert [columns(row[: wall.start()]) for wall in re.finditer("┴┬┴┤", row)] == title_columns

    def test_colors_the_color_columns_whatever_stdout_is(self, kaomoji):
        out = kaomoji("hero").run("--preview", "--mood", "happy", "--no-entrance", "--loops", "0", "--frame-ms", "0").stdout

        assert out.count("\x1b[38;5;214m") == 4  # one redraw: the [ and the ] of the static and the animated colored hero


def columns(text: str) -> int:
    """Display width, counting East Asian wide and fullwidth characters twice like the engine does."""
    return sum(2 if unicodedata.east_asian_width(c) in "FW" else 1 for c in text)
