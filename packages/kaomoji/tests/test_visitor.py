import pytest

pytestmark = pytest.mark.tier0

STATIC = {
    "neutral": "┴┬┴┤´Ｏ´)ﾉ",
    "happy": "┴┬┴┤ ･‿･)ﾉ",
    "sad": "┴┬┴┤◕︿◕)ﾉ",
    "unknown": "┴┬┴┤⊙﹏⊙)ﾉ",
}
WALL, PERSON, CYCLE = 4, 5, 36  # neutral: graphemes of the wall, of the person, hover steps
ENTRANCE = EXIT = WALL + PERSON
SWING, BLINK_AT = 6, 30


@pytest.fixture
def visitor(kaomoji):
    return kaomoji("visitor")


class TestStatic:
    @pytest.mark.parametrize("mood", STATIC)
    def test_renders_the_mood_at_rest(self, visitor, mood):
        assert visitor.static(mood) == STATIC[mood]


class TestAnimation:
    @pytest.fixture
    def frames(self, visitor):
        return visitor.frames("--mood", "neutral", "--loops", "1", "--exit")

    def test_runs_entrance_one_cycle_and_exit(self, frames):
        assert len(frames) == 1 + ENTRANCE + CYCLE + EXIT

    def test_slides_the_wall_in_then_peeks_out_from_behind_it(self, frames):
        assert frames[0] == ""
        assert frames[1] == "┤"
        assert frames[WALL] == "┴┬┴┤"
        assert frames[WALL + 1] == "┴┬┴┤ﾉ"
        assert frames[WALL + 2] == "┴┬┴┤)ﾉ"
        assert frames[ENTRANCE] == STATIC["neutral"]

    def test_waves_while_hovering(self, frames):
        assert frames[ENTRANCE + SWING - 1].endswith("ﾉ")
        assert frames[ENTRANCE + SWING].endswith("ノ")
        assert frames[ENTRANCE + 2 * SWING].endswith("ﾉ")

    def test_blinks_once_per_cycle(self, frames):
        assert frames[ENTRANCE + BLINK_AT - 1] == "┴┬┴┤´Ｏ´)ﾉ"
        assert frames[ENTRANCE + BLINK_AT] == "┴┬┴┤-Ｏ-)ノ"
        assert frames[ENTRANCE + BLINK_AT + 1] == "┴┬┴┤-Ｏ-)ノ"
        assert frames[ENTRANCE + BLINK_AT + 2] == "┴┬┴┤´Ｏ´)ノ"

    def test_rests_after_a_cycle(self, frames):
        assert frames[ENTRANCE + CYCLE] == STATIC["neutral"]

    def test_ducks_behind_the_wall_then_the_wall_slides_out(self, frames):
        exit_step = ENTRANCE + CYCLE

        assert frames[exit_step + 1] == "┴┬┴┤Ｏ´)ﾉ"
        assert frames[exit_step + PERSON] == "┴┬┴┤"
        assert frames[exit_step + PERSON + 1] == "┬┴┤"
        assert frames[-1] == ""


class TestGrid:
    def test_shows_every_mood_in_four_columns(self, visitor):
        header, *rows = visitor.grid("--loops", "1")[-1]

        assert header.split()[0] == "mood"
        assert [row.split()[0] for row in rows] == list(STATIC)
        assert all(row.count(STATIC[mood]) == 4 for mood, row in zip(STATIC, rows))
