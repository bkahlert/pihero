import json
import os
import signal

import pytest

from pihero_testkit.preview import record

pytestmark = pytest.mark.tier0
STARTED = "Fri Oct  3 10:11:12 2026"


class TestStaleActions:
    def test_refuses_to_start_next_to_a_running_preview(self):
        with pytest.raises(record.AlreadyRunning, match=r"a preview is already running \(process 100\)"):
            record.stale_actions({"owner": [100, STARTED]}, alive=lambda entry: entry[0] == 100)

    def test_ends_what_a_killed_preview_left_behind(self):
        stale = {"owner": [100, STARTED], "qemu": [200, STARTED], "dev_server": [300, STARTED], "tunnel": [400, STARTED], "device": "pi@host", "backend": True}

        actions = record.stale_actions(stale, alive=lambda entry: entry[0] != 100)

        assert actions == [("terminate", 200), ("terminate-group", 300), ("terminate", 400), ("restore-device", "pi@host"), ("stop-backend", None)]

    def test_leaves_alone_a_process_that_reuses_the_recorded_id(self):
        actions = record.stale_actions({"owner": [100, STARTED], "qemu": [200, STARTED]}, alive=lambda entry: False)

        assert actions == []

    def test_does_nothing_for_an_empty_record(self):
        assert record.stale_actions({}, alive=lambda entry: True) == []

    def test_reads_a_record_of_the_older_format_without_crashing(self):
        older = {"owner": 1234, "gradle": 5678, "broker": True}

        actions = record.stale_actions(older, alive=lambda entry: isinstance(entry, list))

        assert actions == []


class TestCarryOut:
    def test_terminates_processes_and_groups_and_waits_for_them(self):
        calls = []
        gone = {200: 1, 300: 1}

        def info(pid):
            gone[pid] -= 1
            return (STARTED, "S") if gone[pid] >= 0 else None

        record.carry_out(
            [("terminate", 200), ("terminate-group", 300)], stop_backend=lambda: calls.append("stop"), restore_board=lambda t: calls.append(t),
            kill=lambda pid, sig: calls.append(("kill", pid, sig)), killpg=lambda pgid, sig: calls.append(("killpg", pgid, sig)), getpgid=lambda pid: pid + 1,
            info=info, sleep=lambda s: None, clock=counter(),
        )

        assert calls == [("kill", 200, signal.SIGTERM), ("killpg", 301, signal.SIGTERM)]
        assert gone == {200: -1, 300: -1}

    def test_restores_the_board_and_stops_the_backend(self):
        calls = []

        record.carry_out([("restore-device", "pi@host"), ("stop-backend", None)], stop_backend=lambda: calls.append("stop"), restore_board=calls.append, info=lambda pid: None)

        assert calls == ["pi@host", "stop"]

    def test_skips_a_process_that_ended_meanwhile(self):
        waited = []

        def kill(pid, sig):
            raise ProcessLookupError

        record.carry_out([("terminate", 200)], stop_backend=lambda: None, restore_board=lambda t: None, kill=kill, info=lambda pid: waited.append(pid))

        assert waited == []

    def test_returns_the_board_whose_restore_failed(self):
        failed = record.carry_out([("restore-device", "pi@host")], stop_backend=lambda: None, restore_board=lambda t: False, info=lambda pid: None)

        assert failed == "pi@host"

    def test_returns_none_when_the_board_was_restored(self):
        failed = record.carry_out([("restore-device", "pi@host")], stop_backend=lambda: None, restore_board=lambda t: True, info=lambda pid: None)

        assert failed is None


class TestRecord:
    def test_claim_records_this_process_as_the_owner(self, tmp_path):
        rec = record.Record(tmp_path)

        rec.claim(stop_backend=lambda: None, restore_board=lambda t: None, alive=lambda entry: False, info=lambda pid: (STARTED, "S"))

        assert rec.read()["owner"] == [os.getpid(), STARTED]

    def test_claim_ends_the_stale_session_and_removes_its_directory(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED], "backend": True}))
        rec.session_dir.mkdir()
        stopped = []

        rec.claim(stop_backend=lambda: stopped.append(True), restore_board=lambda t: None, alive=lambda entry: False, info=lambda pid: (STARTED, "S"))

        assert stopped == [True]
        assert not rec.session_dir.exists()

    def test_claim_keeps_a_board_whose_restore_failed_next_to_the_new_owner(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"device": "pi@host"}))

        rec.claim(stop_backend=lambda: None, restore_board=lambda t: False, alive=lambda entry: False, info=lambda pid: (STARTED, "S"))

        assert rec.read() == {"owner": [os.getpid(), STARTED], "device": "pi@host"}

    def test_claim_drops_a_board_whose_restore_succeeded(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"device": "pi@host"}))

        rec.claim(stop_backend=lambda: None, restore_board=lambda t: True, alive=lambda entry: False, info=lambda pid: (STARTED, "S"))

        assert rec.read() == {"owner": [os.getpid(), STARTED]}

    def test_claim_treats_a_corrupt_record_as_empty(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text('{"owner": [1, "Fri')

        rec.claim(stop_backend=lambda: None, restore_board=lambda t: None, alive=lambda entry: pytest.fail("asked"), info=lambda pid: (STARTED, "S"))

        assert "owner" in rec.read()

    @pytest.mark.parametrize("content", ["[]", "null", '"x"'])
    def test_claim_treats_a_record_that_is_not_an_object_as_empty(self, tmp_path, content):
        rec = record.Record(tmp_path)
        rec.path.write_text(content)

        rec.claim(stop_backend=lambda: None, restore_board=lambda t: None, alive=lambda entry: pytest.fail("asked"), info=lambda pid: (STARTED, "S"))

        assert rec.read()["owner"] == [os.getpid(), STARTED]

    def test_claim_raises_next_to_a_live_owner_and_changes_nothing(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED]}))

        with pytest.raises(record.AlreadyRunning):
            rec.claim(stop_backend=lambda: None, restore_board=lambda t: None, alive=lambda entry: True, info=lambda pid: (STARTED, "S"))

        assert rec.read() == {"owner": [1, STARTED]}

    def test_update_adds_fields(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED]}))

        rec.update(qemu=[2, STARTED], inspector=54321)

        assert rec.read() == {"owner": [1, STARTED], "qemu": [2, STARTED], "inspector": 54321}

    def test_forget_deletes_the_record(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED], "dev_server": [2, STARTED]}))

        rec.forget()

        assert not rec.path.exists()

    def test_forget_keeps_only_a_board_that_still_runs_the_session(self, tmp_path):
        rec = record.Record(tmp_path)
        rec.path.write_text(json.dumps({"owner": [1, STARTED], "device": "pi@host"}))

        rec.forget()

        assert rec.read() == {"device": "pi@host"}

    def test_forget_is_done_on_a_missing_record(self, tmp_path):
        rec = record.Record(tmp_path)

        rec.forget()

        assert not rec.path.exists()

    def test_read_is_empty_without_a_record(self, tmp_path):
        assert record.Record(tmp_path).read() == {}


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
