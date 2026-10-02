import subprocess
import sys

import pytest

from pihero_testkit import checkpoint

pytestmark = pytest.mark.tier0


class TestBoards:
    def test_takes_the_names_given(self):
        names = checkpoint.boards(["a", "b"])

        assert names == ["a", "b"]

    def test_falls_back_to_checkpoints_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("CHECKPOINTS", "checkpoint checkpoint32")

        names = checkpoint.boards([])

        assert names == ["checkpoint", "checkpoint32"]

    def test_exits_with_the_usage_without_names(self, monkeypatch):
        monkeypatch.setenv("CHECKPOINTS", "")

        with pytest.raises(SystemExit, match="CHECKPOINTS"):
            checkpoint.boards([])


class TestUriFor:
    def test_is_pi_at_the_boards_name_dot_local(self):
        uri = checkpoint.uri_for("checkpoint32")

        assert uri == "pi@checkpoint32.local"


class TestMain:
    def test_runs_the_ssh_tier_against_every_reachable_board(self, monkeypatch, capsys):
        calls = fake_ssh(monkeypatch)

        rc = checkpoint.main(["a", "b"])

        assert rc == 0
        assert calls[0] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "pi@a.local", "true"]
        assert calls[1] == [sys.executable, "-m", "pytest", "-m", "installed", "--target=ssh", "--target-uri=pi@a.local"]
        assert calls[3][-1] == "--target-uri=pi@b.local"
        assert capsys.readouterr().out.splitlines() == ["a: passed", "b: passed"]

    def test_reports_an_unreachable_board_and_fails(self, monkeypatch, capsys):
        calls = fake_ssh(monkeypatch, probe={"pi@b.local": 255})

        rc = checkpoint.main(["a", "b"])

        assert rc == 1
        assert [c for c in calls if c[0] != "ssh"] == [[sys.executable, "-m", "pytest", "-m", "installed", "--target=ssh", "--target-uri=pi@a.local"]]
        assert capsys.readouterr().out.splitlines() == ["a: passed", "b: unreachable (pi@b.local)"]

    def test_fails_when_a_boards_tests_fail(self, monkeypatch, capsys):
        fake_ssh(monkeypatch, tier={"pi@a.local": 1})

        rc = checkpoint.main(["a", "b"])

        assert rc == 1
        assert capsys.readouterr().out.splitlines() == ["a: failed", "b: passed"]


def fake_ssh(monkeypatch, probe: dict[str, int] | None = None, tier: dict[str, int] | None = None) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ssh":
            return subprocess.CompletedProcess(cmd, (probe or {}).get(cmd[-2], 0))
        return subprocess.CompletedProcess(cmd, (tier or {}).get(cmd[-1].removeprefix("--target-uri="), 0))

    monkeypatch.setattr(checkpoint.subprocess, "run", run)
    return calls
