import pytest

pytestmark = pytest.mark.tier0

STATIC = {
    "neutral": "─=≡▰▩▩[ 蓬•ｏ•]⊐",
    "happy": "─=≡▰▩▩[✿＾ｖ＾]⊐",
    "sad": "─=≡▰▩▩[ ༶◕︿◕ ]⊐",
    "unknown": "─=≡▰▩▩[༶´⊙﹏⊙`]⊐",
}
COLUMNS = 40
ENTRANCE, CYCLE, EXIT = 14, 12, 16  # neutral: graphemes, hover steps, cells


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

    def test_flies_in_from_the_left_one_grapheme_per_step(self, frames):
        assert frames[0] == ""
        assert frames[1] == "⊐"
        assert frames[2] == "]⊐"
        assert frames[ENTRANCE] == STATIC["neutral"]

    def test_rests_where_it_landed_after_a_cycle(self, frames):
        assert frames[ENTRANCE + CYCLE] == STATIC["neutral"]

    def test_flickers_the_tail_and_flexes_the_hand_while_hovering(self, frames):
        hovering = frames[ENTRANCE + 1 : ENTRANCE + CYCLE]

        assert {f[:3] for f in hovering} == {"-─=", " -─", "─=≡"}
        assert {f[-1] for f in hovering} == {"⫎", "⊐"}

    def test_flies_out_through_the_right_edge_of_the_terminal(self, frames):
        exit_step = ENTRANCE + CYCLE

        assert frames[exit_step + 1] == "  -─=▰▩▩[ 蓬•ｏ•]⫎"
        assert frames[exit_step + CYCLE] == " " * 29 + "─=≡▰▩▩[ 蓬"
        assert frames[exit_step + EXIT - 1] == " " * 36 + "-─="
        assert frames[-1] == ""

    def test_crosses_a_wider_terminal_in_the_same_steps(self, kaomoji):
        frames = kaomoji("hero", columns=3 * COLUMNS).frames("--mood", "neutral", "--loops", "1", "--exit")

        assert len(frames) == 1 + ENTRANCE + CYCLE + EXIT
        assert frames[ENTRANCE + CYCLE + 1] == " " * 7 + "-─=▰▩▩[ 蓬•ｏ•]⫎"
        assert frames[-1] == ""

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
