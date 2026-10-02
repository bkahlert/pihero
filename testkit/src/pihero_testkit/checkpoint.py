"""Runs the ssh tier against the checkpoints, the real boards a release is proven on, and says which one is unreachable."""

import os
import subprocess
import sys

USER = "pi"
PROBE_TIMEOUT = 5


def boards(argv: list[str]) -> list[str]:
    """Returns the device names given, else those in CHECKPOINTS; exits with the usage when there are none."""
    names = argv or os.environ.get("CHECKPOINTS", "").split()
    if not names:
        print("usage: python -m pihero_testkit.checkpoint [DEVICE ...]   (default: the names in CHECKPOINTS, set in .env)", file=sys.stderr)
        raise SystemExit(2)
    return names


def uri_for(name: str) -> str:
    """Returns pi@<name>.local: a checkpoint's device directory is named after its hostname."""
    return f"{USER}@{name}.local"


def probe(uri: str) -> str | None:
    """Returns None when a non-interactive ssh login at uri succeeds within PROBE_TIMEOUT seconds, else ssh's last line of stderr.

    A reflashed board has a new host key, which the login accepts as the operator would after `ssh-keygen -R`.
    """
    command = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={PROBE_TIMEOUT}", "-o", "StrictHostKeyChecking=accept-new", uri, "true"]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode == 0:
        return None
    lines = [line.strip() for line in result.stderr.decode(errors="replace").splitlines() if line.strip()]
    return lines[-1] if lines else f"ssh exited with {result.returncode}"


def run_tier(uri: str) -> int:
    """Runs the installed tests against uri and returns pytest's exit code."""
    tier = [sys.executable, "-m", "pytest", "-m", "installed", "--target=ssh", f"--target-uri={uri}"]
    return subprocess.run(tier, check=False).returncode


def main(argv: list[str]) -> int:
    verdicts: dict[str, str] = {}
    for name in boards(argv):
        uri = uri_for(name)
        if error := probe(uri):
            verdicts[name] = f"unreachable ({uri}): {error}"
            continue
        print(f"  {name}: the ssh tier against {uri}", file=sys.stderr, flush=True)
        verdicts[name] = "passed" if run_tier(uri) == 0 else "failed"
    for name, verdict in verdicts.items():
        print(f"{name}: {verdict}", flush=True)
    return 0 if all(verdict == "passed" for verdict in verdicts.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
