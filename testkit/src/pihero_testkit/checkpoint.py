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
        raise SystemExit("usage: python -m pihero_testkit.checkpoint [DEVICE ...]   (default: the names in CHECKPOINTS, set in .env)")
    return names


def uri_for(name: str) -> str:
    """Returns pi@<name>.local: a checkpoint's device directory is named after its hostname."""
    return f"{USER}@{name}.local"


def reachable(uri: str) -> bool:
    """Returns whether a non-interactive ssh login at uri succeeds within PROBE_TIMEOUT seconds."""
    probe = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={PROBE_TIMEOUT}", uri, "true"]
    return subprocess.run(probe, capture_output=True, check=False).returncode == 0


def run_tier(uri: str) -> int:
    """Runs the installed tests against uri and returns pytest's exit code."""
    tier = [sys.executable, "-m", "pytest", "-m", "installed", "--target=ssh", f"--target-uri={uri}"]
    return subprocess.run(tier, check=False).returncode


def main(argv: list[str]) -> int:
    verdicts: dict[str, str] = {}
    for name in boards(argv):
        uri = uri_for(name)
        if not reachable(uri):
            verdicts[name] = f"unreachable ({uri})"
            continue
        print(f"  {name}: the ssh tier against {uri}", file=sys.stderr, flush=True)
        verdicts[name] = "passed" if run_tier(uri) == 0 else "failed"
    for name, verdict in verdicts.items():
        print(f"{name}: {verdict}", flush=True)
    return 0 if all(verdict == "passed" for verdict in verdicts.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
