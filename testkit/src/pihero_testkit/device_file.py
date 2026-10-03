"""Renders a device file for the tier-2 VM: the testkit's user and key, and the harness repository in place of a published source."""

import re
from importlib.resources import files
from pathlib import Path

from . import repo

USER = "pihero"
PUBLIC_KEY = Path(str(files("pihero_testkit") / "keys" / "pihero-testkit.pub"))
SOURCE = """\
  - path: {path}
    content: |
      Types: deb
      URIs: {url}
      Suites: ./
      Trusted: yes
"""


def block(text: str, start: str) -> str:
    """Return the line equal to `start` and every following line indented deeper than it, with the blank and comment lines
    between them; blank and comment lines after the last such line belong to what follows. Raise ValueError without the line."""
    lines = text.splitlines(keepends=True)
    try:
        begin = next(i for i, line in enumerate(lines) if line.rstrip("\n") == start)
    except StopIteration:
        raise ValueError(f"the device file has no line {start!r}") from None
    indent = len(start) - len(start.lstrip(" "))
    end = begin + 1
    for i in range(begin + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(lines[i]) - len(lines[i].lstrip(" ")) <= indent:
            break
        end = i + 1
    return "".join(lines[begin:end])


def drop(text: str, start: str) -> str:
    """Return `text` without the block that starts at `start`."""
    return text.replace(block(text, start), "", 1)


def with_user(text: str, key: str, user: str = USER) -> str:
    """Return `text` with its one user renamed to `user` and that user's first authorized key replaced by `key`.

    Raise ValueError without a users block, with more or fewer than one user, or without an ssh_authorized_keys entry.
    """
    users = block(text, "users:")
    if users.count("  - name: ") != 1:
        raise ValueError("expected one user in the device file")
    renamed = re.sub(r"^(?P<prefix>  - name: ).*$", lambda m: m["prefix"] + user, users, count=1, flags=re.M)
    rekeyed, keys = re.subn(r"^(?P<prefix>    ssh_authorized_keys:\n      - ).*$", lambda m: m["prefix"] + key, renamed, count=1, flags=re.M)
    if keys == 0:
        raise ValueError("expected an ssh_authorized_keys entry in the device file")
    return text.replace(users, rekeyed, 1)


def with_source(text: str, path: str, url: str = repo.URL) -> str:
    """Return `text` with the write_files entry at `path` replaced by a trusted deb822 source for `url`."""
    return text.replace(block(text, f"  - path: {path}"), SOURCE.format(path=path, url=url), 1)


def write(directory: Path, user_data: str) -> Path:
    """Write `user_data` as `directory/user-data`, creating the directory, and return the directory."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "user-data").write_text(user_data)
    return directory
