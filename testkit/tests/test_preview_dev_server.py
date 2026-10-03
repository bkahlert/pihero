import re
import signal
import subprocess
from types import SimpleNamespace

import pytest

from pihero_testkit.preview import dev_server
from pihero_testkit.preview.api import DevServer

pytestmark = pytest.mark.tier0
SERVER = DevServer(["./gradlew", "--console=plain", "jsBrowserDevelopmentRun", "--continuous"], 8081, {"NETMON_STATS_PROXY": "http://netmon.local"})


class TestStart:
    def test_runs_the_command_in_the_root_in_its_own_session_with_the_env_added(self, tmp_path):
        calls = []

        dev_server.start(SERVER, tmp_path, tmp_path / "dist" / "preview" / "dev-server.log", environ={"PATH": "/bin", "NETMON_STATS_PROXY": "http://old"}, popen=lambda argv, **kw: calls.append((argv, kw)))

        argv, kw = calls[0]
        assert argv == SERVER.argv
        assert kw["cwd"] == tmp_path
        assert kw["env"] == {"PATH": "/bin", "NETMON_STATS_PROXY": "http://netmon.local"}
        assert kw["start_new_session"] is True
        assert kw["stderr"] is subprocess.STDOUT
        assert (tmp_path / "dist" / "preview").is_dir()


class TestWaitUntilServing:
    def test_returns_once_the_port_answers(self, tmp_path):
        answers = iter([False, False, True])

        dev_server.wait_until_serving(SimpleNamespace(poll=lambda: None), 8081, tmp_path / "log", answers=lambda h, p: next(answers), sleep=lambda s: None, clock=counter())

    def test_fails_early_when_the_process_ends(self, tmp_path):
        with pytest.raises(RuntimeError, match=f"dev server exited with status 1; see {tmp_path / 'log'}"):
            dev_server.wait_until_serving(SimpleNamespace(poll=lambda: 1, returncode=1), 8081, tmp_path / "log", answers=lambda h, p: False, sleep=lambda s: None, clock=counter())

    def test_times_out_naming_the_log(self, tmp_path):
        with pytest.raises(TimeoutError, match=re.escape(f"nothing answers on port 8081 after 900 s; see {tmp_path / 'log'}")):
            dev_server.wait_until_serving(SimpleNamespace(poll=lambda: None), 8081, tmp_path / "log", answers=lambda h, p: False, sleep=lambda s: None, clock=counter(step=500))


class TestEnsure:
    def test_refuses_a_port_something_already_answers_on(self, tmp_path):
        with pytest.raises(RuntimeError, match="something already answers on port 8081; end it first"):
            dev_server.ensure(SERVER, tmp_path, tmp_path / "log", answers=lambda h, p: True, start=lambda *a, **k: pytest.fail("started"))

    def test_starts_and_waits(self, tmp_path):
        proc = SimpleNamespace(poll=lambda: None)
        waited = []

        result = dev_server.ensure(SERVER, tmp_path, tmp_path / "log", answers=lambda h, p: False, start=lambda *a, **k: proc, wait=lambda p, port, log: waited.append(port))

        assert result is proc
        assert waited == [8081]

    def test_stops_the_process_when_the_wait_fails(self, tmp_path):
        proc = SimpleNamespace(poll=lambda: None)
        stopped = []

        def wait(p, port, log):
            raise TimeoutError("no")

        with pytest.raises(TimeoutError):
            dev_server.ensure(SERVER, tmp_path, tmp_path / "log", answers=lambda h, p: False, start=lambda *a, **k: proc, wait=wait, stop=stopped.append)

        assert stopped == [proc]


class TestStop:
    def test_terminates_the_process_group(self):
        calls = []
        proc = SimpleNamespace(pid=77, poll=lambda: None, wait=lambda t: None)

        dev_server.stop(proc, killpg=lambda pgid, sig: calls.append((pgid, sig)))

        assert calls == [(77, signal.SIGTERM)]

    def test_kills_the_group_when_it_does_not_end(self):
        calls = []

        def wait(timeout):
            raise subprocess.TimeoutExpired("gradle", timeout)

        dev_server.stop(SimpleNamespace(pid=77, poll=lambda: None, wait=wait), killpg=lambda pgid, sig: calls.append(sig))

        assert calls == [signal.SIGTERM, signal.SIGKILL]

    def test_does_nothing_for_an_ended_process(self):
        dev_server.stop(SimpleNamespace(pid=77, poll=lambda: 0), killpg=lambda pgid, sig: pytest.fail("killed"))


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
