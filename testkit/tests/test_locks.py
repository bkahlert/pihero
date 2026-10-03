import threading

import pytest

from pihero_testkit import locks

pytestmark = pytest.mark.tier0


class TestHeld:
    def test_creates_the_lock_file_and_its_directory(self, tmp_path):
        path = tmp_path / "cache" / "a.lock"

        with locks.held(path):
            pass

        assert path.exists()

    def test_makes_a_second_holder_wait_until_the_first_leaves(self, tmp_path):
        path = tmp_path / "a.lock"
        order = []
        first_inside, release_first = threading.Event(), threading.Event()

        def first():
            with locks.held(path):
                order.append("first in")
                first_inside.set()
                release_first.wait(5)
                order.append("first out")

        def second():
            with locks.held(path):
                order.append("second in")

        a = threading.Thread(target=first)
        a.start()
        first_inside.wait(5)
        b = threading.Thread(target=second)
        b.start()
        b.join(0.3)
        assert order == ["first in"]
        release_first.set()
        a.join(5)
        b.join(5)

        assert order == ["first in", "first out", "second in"]
