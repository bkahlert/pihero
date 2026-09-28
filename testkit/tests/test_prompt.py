import pytest

from pihero_testkit import prompt

pytestmark = pytest.mark.tier0


class TestChoose:
    def test_returns_the_index_of_the_number_entered(self):
        index = prompt.choose("Card:", ["a", "b", "c"], read=answers("3"))

        assert index == 2

    def test_returns_the_first_on_enter(self):
        index = prompt.choose("Card:", ["a", "b"], read=answers(""))

        assert index == 0

    def test_asks_again_on_a_line_that_is_not_a_listed_number(self):
        index = prompt.choose("Card:", ["a", "b"], read=answers("x", "9", "0", "2"))

        assert index == 1

    def test_asks_again_on_a_digit_that_is_no_number(self):
        index = prompt.choose("Card:", ["a", "b"], read=answers("\u00b3", "2"))

        assert index == 1

    def test_prints_the_title_and_numbered_options(self, capsys):
        prompt.choose("Card:", ["disk9  SD  31.9 GB", "disk10  SD  63.9 GB"], read=answers("1"))

        out = capsys.readouterr().out
        assert out == "Card:\n  1) disk9  SD  31.9 GB\n  2) disk10  SD  63.9 GB\n"


class TestConfirm:
    def test_accepts_y(self):
        result = prompt.confirm("Go?", read=answers("y"))

        assert result is True

    def test_accepts_yes_in_any_case(self):
        result = prompt.confirm("Go?", read=answers("YES"))

        assert result is True

    def test_rejects_enter(self):
        result = prompt.confirm("Go?", read=answers(""))

        assert result is False

    def test_rejects_anything_else(self):
        result = prompt.confirm("Go?", read=answers("n"))

        assert result is False


class TestAsk:
    def test_returns_the_first_non_empty_answer(self):
        answer = prompt.ask("Name", read=answers("", "   ", "mypi"))

        assert answer == "mypi"


def answers(*lines: str):
    it = iter(lines)
    return lambda _prompt: next(it)
