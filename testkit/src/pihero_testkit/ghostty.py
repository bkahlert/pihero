"""Forgets a host in Ghostty's ssh-terminfo cache, so the next `ssh` from Ghostty installs its terminfo on a reflashed card.

Ghostty's `ssh-terminfo` shell integration installs xterm-ghostty on a host once and remembers `user@host` for good; a card
flashed or restored under a known name never gets the terminfo but is sent TERM=xterm-ghostty regardless. The `ghostty`
CLI is on PATH only inside a Ghostty shell, so the app bundle is searched as well.
"""

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

APP_BUNDLES = (Path("/Applications/Ghostty.app"), Path.home() / "Applications" / "Ghostty.app")
CACHED_HOST = re.compile(r"^\s+(?P<entry>\S+) \(")


def binary() -> Path | None:
    """Return the ghostty CLI from GHOSTTY_BIN_DIR, PATH, or the app bundle, in that order; None when Ghostty is not installed."""
    candidates = [Path(exported) / "ghostty" for exported in [os.environ.get("GHOSTTY_BIN_DIR")] if exported]
    if on_path := shutil.which("ghostty"):
        candidates.append(Path(on_path))
    candidates.extend(bundle / "Contents" / "MacOS" / "ghostty" for bundle in APP_BUNDLES)
    return next((candidate for candidate in candidates if os.access(candidate, os.X_OK)), None)


def cached_hosts(ghostty: Path) -> list[str]:
    """Return the cache's entries, each `user@host` or `host`, as `ghostty +ssh-cache` lists them."""
    out = subprocess.run([ghostty, "+ssh-cache"], capture_output=True, text=True, check=True).stdout
    return [match["entry"] for line in out.splitlines() if (match := CACHED_HOST.match(line))]


def entries_for(hostname: str, cached: list[str]) -> list[str]:
    """Return the entries for hostname or hostname.local, under any user, ignoring case as mDNS does."""
    names = {hostname.lower(), f"{hostname}.local".lower()}
    return [entry for entry in cached if entry.rpartition("@")[2].lower() in names]


def forget(hostname: str, report: Callable[[str], None] = lambda message: None) -> list[str]:
    """Remove hostname's entries from the cache and return them; report what was removed. Empty without Ghostty."""
    ghostty = binary()
    if not ghostty:
        return []
    entries = entries_for(hostname, cached_hosts(ghostty))
    for entry in entries:
        subprocess.run([ghostty, "+ssh-cache", f"--remove={entry}"], capture_output=True, check=True)
    if entries:
        report(f"forgot {', '.join(entries)} in Ghostty's ssh-terminfo cache; the next ssh from Ghostty installs its terminfo again")
    return entries
