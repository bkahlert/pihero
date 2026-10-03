from subprocess import CompletedProcess

import pytest

from pihero_testkit.preview import window

pytestmark = pytest.mark.tier0
PS = """\
  501 /opt/homebrew/bin/qemu-system-aarch64 -M virt -display cocoa,zoom-to-fit=on -m 1024
  502 /opt/homebrew/bin/qemu-system-aarch64 -M virt -display none -m 1024
  503 /opt/homebrew/bin/qemu-system-aarch64 -M virt -display cocoa,zoom-to-fit=on -m 1024
  504 vim notes.txt
"""


class TestPoints:
    def test_is_the_display_plus_the_title_bar(self):
        assert window.points((800, 480)) == (800, 512)
        assert window.points((480, 320)) == (480, 352)


class TestOrigin:
    def test_starts_at_the_default_and_steps_per_other_window(self):
        assert window.origin(0) == (120, 80)
        assert window.origin(2) == (200, 160)


class TestOtherWindows:
    def test_counts_qemu_processes_with_a_cocoa_display_other_than_the_pid(self):
        assert window.other_windows(501, PS) == 1

    def test_is_zero_when_this_vm_is_the_only_one(self):
        only_this_vm = "".join(line for line in PS.splitlines(keepends=True) if not line.startswith("  503"))

        assert window.other_windows(501, only_this_vm) == 0


class TestScript:
    def test_targets_the_process_by_its_unix_id_and_sets_position_then_size(self):
        argv = window.script(501, (800, 512), (120, 80))

        target = 'tell application "System Events" to tell (first process whose unix id is 501)'
        assert argv == ["osascript", "-e", f"{target} to set position of window 1 to {{120, 80}}", "-e", f"{target} to set size of window 1 to {{800, 512}}"]


class TestPlace:
    def test_places_the_window_once_system_events_accepts(self):
        results = iter([0, 1, 1, 0])
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return CompletedProcess(argv, next(results), "", "")

        placed = window.place(501, (800, 480), run=run, sleep=lambda s: None, report=lambda m: pytest.fail(m))

        assert placed is True
        assert len(calls) == 4
        assert calls[0] == ["ps", "-axo", "pid=,command="]
        assert "set size of window 1 to {800, 512}" in calls[-1][-1]

    def test_reports_the_accessibility_hint_and_gives_up_after_the_attempts(self):
        reported = []
        calls = []
        sleeps = []

        def run(argv, **kwargs):
            calls.append(argv)
            return CompletedProcess(argv, 1, "", "")

        placed = window.place(501, (800, 480), attempts=2, run=run, sleep=sleeps.append, report=reported.append)

        assert placed is False
        assert [argv[0] for argv in calls] == ["ps", "osascript", "osascript"]
        assert sleeps == [1, 1]
        assert reported == ["could not place the VM's window; allow your terminal under Privacy & Security > Accessibility"]

    def test_cascades_behind_the_other_vm_windows(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            return CompletedProcess(argv, 0, PS if argv[0] == "ps" else "", "")

        window.place(501, (800, 480), run=run, sleep=lambda s: None, report=lambda m: None)

        assert "set position of window 1 to {160, 120}" in calls[-1][2]
