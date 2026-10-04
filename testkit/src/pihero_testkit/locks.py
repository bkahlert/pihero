"""A file lock for the builds two runs must not do at once: the base image and a preview layer."""

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def held(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on `path`, creating it and its directory, until the block ends; a second holder waits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
