import signal
import socket
from subprocess import CompletedProcess

import pytest

from pihero_testkit.preview import process

pytestmark = pytest.mark.tier0
STARTED = "Fri Oct  3 10:11:12 2026"


class TestAnswers:
    def test_is_true_for_a_listening_port(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()

            assert process.answers("127.0.0.1", sock.getsockname()[1])

    def test_is_false_for_a_closed_port(self):
        assert not process.answers("127.0.0.1", process.free_port(), timeout=0.2)


class TestInfo:
    def test_is_the_start_time_and_state_of_a_running_process(self):
        started, state = process.info(42, run=ps(f"{STARTED} S+\n"))

        assert (started, state) == (STARTED, "S+")

    def test_asks_ps_for_the_start_time_and_state_of_the_pid(self):
        calls = []
        process.info(42, run=ps("", calls))

        assert calls == [["ps", "-p", "42", "-o", "lstart=,stat="]]

    def test_is_none_for_a_process_that_is_gone(self):
        assert process.info(42, run=ps("")) is None

    def test_is_none_for_a_zombie(self):
        assert process.info(42, run=ps(f"{STARTED} Z\n")) is None


class TestEntry:
    def test_is_the_pid_and_its_start_time(self):
        assert process.entry(42, info=lambda pid: (STARTED, "S")) == [42, STARTED]

    def test_is_none_for_a_process_that_is_gone(self):
        assert process.entry(42, info=lambda pid: None) is None


class TestAlive:
    def test_is_true_while_the_pid_runs_with_the_recorded_start_time(self):
        assert process.alive([42, STARTED], info=lambda pid: (STARTED, "S"))

    def test_is_false_for_a_pid_reused_by_a_process_started_later(self):
        assert not process.alive([42, STARTED], info=lambda pid: ("Sat Oct  4 00:00:00 2026", "S"))

    def test_is_false_for_a_pid_that_is_gone(self):
        assert not process.alive([42, STARTED], info=lambda pid: None)

    @pytest.mark.parametrize("entry", [None, 42, "42", [42], {"pid": 42}])
    def test_is_false_for_anything_but_a_pid_and_start_time(self, entry):
        assert not process.alive(entry, info=lambda pid: (STARTED, "S"))


class TestWaitUntilGone:
    def test_returns_once_every_pid_is_gone(self):
        remaining = {1: 2, 2: 1}

        def info(pid):
            remaining[pid] -= 1
            return (STARTED, "S") if remaining[pid] > 0 else None

        process.wait_until_gone([1, 2], info=info, sleep=lambda s: None, clock=counter())

        assert remaining == {1: 0, 2: 0}

    def test_raises_when_a_pid_outlives_the_timeout(self):
        with pytest.raises(TimeoutError, match="process 7 of a killed preview did not end within 30 s"):
            process.wait_until_gone([7], info=lambda pid: (STARTED, "S"), sleep=lambda s: None, clock=counter(step=20))


class TestUntilInterrupted:
    def test_returns_on_keyboard_interrupt_from_the_watch(self):
        def watch():
            raise KeyboardInterrupt

        process.until_interrupted(watch, sleep=lambda s: None)

    def test_raises_the_problem_the_watch_reports(self):
        answers = iter([None, "the tunnel ended"])

        with pytest.raises(RuntimeError, match="the tunnel ended"):
            process.until_interrupted(lambda: next(answers), sleep=lambda s: None)

    def test_pauses_once_and_returns_without_a_watch(self):
        pauses = []

        process.until_interrupted(pause=lambda: pauses.append("paused"))

        assert pauses == ["paused"]

    def test_returns_on_keyboard_interrupt_while_paused(self):
        def pause():
            raise KeyboardInterrupt

        process.until_interrupted(pause=pause)


class TestRaiseOnSigterm:
    def test_makes_sigterm_a_keyboard_interrupt(self):
        before = signal.getsignal(signal.SIGTERM)
        try:
            process.raise_on_sigterm()

            with pytest.raises(KeyboardInterrupt):
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        finally:
            signal.signal(signal.SIGTERM, before)


def ps(stdout: str, calls: list | None = None):
    def run(args, **kwargs):
        if calls is not None:
            calls.append(args)
        return CompletedProcess(args, 0, stdout=stdout, stderr="")

    return run


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
