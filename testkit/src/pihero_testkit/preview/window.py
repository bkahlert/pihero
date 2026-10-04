"""Places a session's QEMU window: found by its process id, sized to the display, cascaded behind the other VM windows."""

import subprocess
import sys
import time
from collections.abc import Callable

TITLE_BAR = 32
ORIGIN = (120, 80)
STEP = 40
PROCESS = "qemu-system-aarch64"
HINT = "could not place the VM's window; allow your terminal under Privacy & Security > Accessibility"


def points(display: tuple[int, int]) -> tuple[int, int]:
    """Return the window's size in points for `display`: one point per pixel plus the title bar."""
    return display[0], display[1] + TITLE_BAR


def origin(others: int) -> tuple[int, int]:
    """Return the window's origin with `others` VM windows already open, one step down and right per window."""
    return ORIGIN[0] + STEP * others, ORIGIN[1] + STEP * others


def listing(run=subprocess.run) -> str:
    """Return every process as `pid command`, one per line."""
    return run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=False).stdout


def other_windows(pid: int, listing: str) -> int:
    """Return how many QEMU processes other than `pid` show a cocoa window in `listing`."""
    count = 0
    for line in listing.splitlines():
        words = line.split(None, 1)
        if len(words) == 2 and PROCESS in words[1] and "-display cocoa" in words[1] and int(words[0]) != pid:
            count += 1
    return count


def script(pid: int, size: tuple[int, int], origin: tuple[int, int]) -> list[str]:
    """Return the osascript command that moves and sizes the first window of the process `pid`."""
    target = f'tell application "System Events" to tell (first process whose unix id is {pid})'
    return [
        "osascript",
        "-e", f"{target} to set position of window 1 to {{{origin[0]}, {origin[1]}}}",
        "-e", f"{target} to set size of window 1 to {{{size[0]}, {size[1]}}}",
    ]


def place(pid: int, display: tuple[int, int], attempts: int = 20, run=subprocess.run, sleep=time.sleep, report: Callable[[str], None] = lambda message: print(message, file=sys.stderr)) -> bool:
    """Place the window of the QEMU process `pid` for `display`, trying once a second; return whether macOS allowed it, reporting the hint when not."""
    at = origin(other_windows(pid, listing(run)))
    for _ in range(attempts):
        if run(script(pid, points(display), at), capture_output=True, text=True, check=False).returncode == 0:
            return True
        sleep(1)
    report(HINT)
    return False
