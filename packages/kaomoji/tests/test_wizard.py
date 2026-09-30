import pytest

pytestmark = pytest.mark.tier0

STATIC = {
    "neutral": "(つ◕౪◕)つ─｡ﾟ․☆･*ﾟ",
    "happy": "(＾∀＾)つ─｡ﾟ․☆･*ﾟ",
    "sad": "( ◕︿◕)つ─｡ﾟ․☆･*ﾟ",
    "unknown": "( ⊙﹏⊙)つ─｡ﾟ․☆･*ﾟ",
}
BODY, MAGIC, CYCLE = 8, 7, 21  # neutral: graphemes of the body, particles, hover steps
ENTRANCE = EXIT = BODY + MAGIC


@pytest.fixture
def wizard(kaomoji):
    return kaomoji("wizard")


class TestStatic:
    @pytest.mark.parametrize("mood", STATIC)
    def test_renders_the_mood_at_rest(self, wizard, mood):
        assert wizard.static(mood) == STATIC[mood]


class TestAnimation:
    @pytest.fixture
    def frames(self, wizard):
        return wizard.frames("--mood", "neutral", "--loops", "1", "--exit")

    def test_runs_entrance_one_cycle_and_exit(self, frames):
        assert len(frames) == 1 + ENTRANCE + CYCLE + EXIT

    def test_slides_in_from_the_left_then_conjures_the_magic(self, frames):
        assert frames[0] == ""
        assert frames[1] == "─"
        assert frames[BODY] == "(つ◕౪◕)つ─"
        assert frames[BODY + 1] == "(つ◕౪◕)つ─｡"
        assert frames[ENTRANCE] == STATIC["neutral"]

    def test_keeps_still_while_hovering_in_plain_output(self, frames):
        assert set(frames[ENTRANCE : ENTRANCE + CYCLE + 1]) == {STATIC["neutral"]}

    def test_loses_the_magic_from_the_right_then_slides_out_to_the_left(self, frames):
        exit_step = ENTRANCE + CYCLE

        assert frames[exit_step + 1] == STATIC["neutral"][:-1]
        assert frames[exit_step + MAGIC] == "(つ◕౪◕)つ─"
        assert frames[exit_step + MAGIC + 1] == "つ◕౪◕)つ─"
        assert frames[-1] == ""

    def test_runs_the_colors_along_the_magic_and_is_back_after_a_cycle(self, wizard):
        frames = wizard.frames("--mood", "neutral", "--loops", "1", color=True)

        assert frames[ENTRANCE] == frames[ENTRANCE + 1] == frames[ENTRANCE + 2]
        assert frames[ENTRANCE + 3] != frames[ENTRANCE]
        assert frames[ENTRANCE + CYCLE] == frames[ENTRANCE]


class TestGrid:
    def test_shows_every_mood_in_four_columns(self, wizard):
        header, *rows = wizard.grid("--loops", "1")[-1]

        assert header.split()[0] == "mood"
        assert [row.split()[0] for row in rows] == list(STATIC)
        assert all(row.count(STATIC[mood]) == 4 for mood, row in zip(STATIC, rows))
