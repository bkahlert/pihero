import time

import pytest

pytestmark = pytest.mark.tier0

STATIC = {
    "neutral": "─=≡▰▩▩[ 蓬•ｏ•]⊐",
    "happy": "─=≡▰▩▩[✿＾ｖ＾]⊐",
    "sad": "─=≡▰▩▩[ ༶◕︿◕ ]⊐",
    "unknown": "─=≡▰▩▩[༶´⊙﹏⊙`]⊐",
}
COLUMNS = 40
ENTRANCE, CYCLE, EXIT = 16, 12, COLUMNS - 1  # neutral: cells, hover steps, cells before the last column


@pytest.fixture
def hero(kaomoji):
    return kaomoji("hero", columns=COLUMNS)


class TestStatic:
    @pytest.mark.parametrize("mood", STATIC)
    def test_renders_the_mood_at_rest(self, hero, mood):
        assert hero.static(mood) == STATIC[mood]


class TestAnimation:
    @pytest.fixture
    def frames(self, hero):
        return hero.frames("--mood", "neutral", "--loops", "1", "--exit")

    def test_runs_entrance_one_cycle_and_exit(self, frames):
        assert len(frames) == 1 + ENTRANCE + CYCLE + EXIT

    def test_flies_in_from_the_left_one_cell_per_step(self, frames):
        assert frames[0] == ""
        assert frames[1] == "⊐"
        assert frames[2] == "]⊐"
        assert frames[3] == "•]⊐"
        assert frames[4] == " •]⊐"  # the wide ｏ straddles the edge and waits a step
        assert frames[5] == "ｏ•]⫎"
        assert frames[ENTRANCE] == STATIC["neutral"]

    def test_rests_where_it_landed_after_a_cycle(self, frames):
        assert frames[ENTRANCE + CYCLE] == STATIC["neutral"]

    def test_flickers_the_tail_and_flexes_the_hand_while_hovering(self, frames):
        hovering = frames[ENTRANCE + 1 : ENTRANCE + CYCLE]

        assert {f[:3] for f in hovering} == {"-─=", " -─", "─=≡"}
        assert {f[-1] for f in hovering} == {"⫎", "⊐"}

    def test_flies_out_through_the_right_edge_of_the_terminal_one_cell_per_step(self, frames):
        exit_step = ENTRANCE + CYCLE

        assert frames[exit_step + 1] == " -─=▰▩▩[ 蓬•ｏ•]⫎"
        assert frames[exit_step + CYCLE] == " " * CYCLE + STATIC["neutral"]
        assert frames[exit_step + 24] == " " * 24 + "─=≡▰▩▩[ 蓬•ｏ•]"
        assert frames[exit_step + 36] == " " * 36 + "─=≡"
        assert frames[-1] == ""

    def test_exit_takes_the_same_time_however_wide_the_terminal(self, kaomoji):
        def timed(columns):
            started = time.monotonic()
            frames = kaomoji("hero", columns=columns).frames("--no-entrance", "--loops", "1", "--exit", "--frame-ms", "20")
            return len(frames), time.monotonic() - started

        narrow, wide = timed(COLUMNS), timed(3 * COLUMNS)

        assert (narrow[0], wide[0]) == (CYCLE + COLUMNS - 1, CYCLE + 3 * COLUMNS - 1)
        assert 0.35 <= narrow[1] < 0.7 and 0.35 <= wide[1] < 0.7  # 12 hover and 8 exit frame times of 20 ms, plus startup

    def test_no_entrance_hovers_where_it_is(self, hero):
        frames = hero.frames("--mood", "neutral", "--loops", "1", "--no-entrance")

        assert len(frames) == CYCLE
        assert frames[-1] == STATIC["neutral"]


class TestGrid:
    def test_shows_every_mood_in_four_columns(self, hero):
        header, *rows = hero.grid("--loops", "1")[-1]

        assert header.split() == ["mood", "static", "plain", "static", "color", "animated", "plain", "animated", "color"]
        assert [row.split()[0] for row in rows] == list(STATIC)
        assert all(row.count(STATIC[mood]) == 4 for mood, row in zip(STATIC, rows))

    def test_animated_columns_are_empty_after_the_exit(self, hero):
        rows = hero.grid("--loops", "1", "--exit")[-1][1:]

        assert all(row.count(STATIC[mood]) == 2 for mood, row in zip(STATIC, rows))
