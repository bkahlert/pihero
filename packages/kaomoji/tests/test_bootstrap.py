import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier0

PACKAGE = Path(__file__).resolve().parents[1]
TEMPLATE = PACKAGE / "bootstrap.sh"
FAKE_CURL = '#!/bin/sh\nout=""; url=""\nwhile [ $# -gt 0 ]; do case $1 in -o) out=$2; shift 2 ;; -*) shift ;; *) url=$1; shift ;; esac; done\nprintf "%s\\n" "$url" >> "$FAKE/curl.log"\ncp "$FAKE/release/${url##*/}" "$out"\n'
FAKE_UNAME = '#!/bin/sh\ncase $1 in -s) echo "$FAKE_OS" ;; -m) echo "$FAKE_ARCH" ;; esac\n'
FAKE_BINARY = '#!/bin/sh\nprintf "%s\\n" "$*" > "$FAKE/run.log"\n'


class Release:
    """A directory standing in for the GitHub release, a curl that copies from it, a uname that says what we want, and a binary that records its arguments."""

    def __init__(self, directory: Path):
        self.dir = directory
        self.bin, self.assets, self.cache = directory / "bin", directory / "release", directory / "cache"
        self.bin.mkdir()
        self.assets.mkdir()
        self.binary = self.assets / "kaomoji-linux-arm64"
        for path, text in [(self.binary, FAKE_BINARY), (self.bin / "curl", FAKE_CURL), (self.bin / "uname", FAKE_UNAME)]:
            path.write_text(text)
            path.chmod(0o755)

    def script(self, version: str = "2.1.0~rc.1", character: str = "hero", sha: str | None = None) -> Path:
        """The template rendered as the build renders it, with the hash of the fake binary unless given."""
        sha = sha or hashlib.sha256(self.binary.read_bytes()).hexdigest()
        name = character or "kaomoji"
        text = TEMPLATE.read_text().replace("@VERSION@", version).replace("@NAME@", name).replace("@CHARACTER@", character).replace("@SHA256_LINUX_ARM64@", sha)
        path = self.dir / name
        path.write_text(text)
        return path

    def run(self, script: Path, *args: str, os_: str = "Linux", arch: str = "aarch64") -> subprocess.CompletedProcess:
        """Runs the script the way the curl line does: piped into sh, the arguments after -s --."""
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "XDG_CACHE_HOME": str(self.cache), "FAKE": str(self.dir), "FAKE_OS": os_, "FAKE_ARCH": arch}
        return subprocess.run(["sh", "-s", "--", *args], input=script.read_text(), capture_output=True, text=True, env=env)

    def fetched(self) -> list[str]:
        log = self.dir / "curl.log"
        return log.read_text().splitlines() if log.exists() else []

    def ran(self) -> str:
        return (self.dir / "run.log").read_text().strip()


@pytest.fixture
def release(tmp_path):
    return Release(tmp_path)


class TestBootstrap:
    def test_fetches_the_binary_of_its_release_for_this_machine_and_runs_its_character_with_the_arguments(self, release):
        result = release.run(release.script(), "--animate", "--exit")

        assert result.returncode == 0, result.stderr
        assert release.fetched() == ["https://github.com/bkahlert/pihero/releases/download/v2.1.0-rc.1/kaomoji-linux-arm64"]
        assert release.ran() == "hero --animate --exit"
        cached = release.cache / "kaomoji" / "2.1.0~rc.1" / "kaomoji"
        assert cached.exists() and cached.stat().st_mode & stat.S_IXUSR

    def test_runs_from_the_cache_the_second_time(self, release):
        script = release.script()

        release.run(script)
        release.run(script, "--loops", "1")

        assert len(release.fetched()) == 1
        assert release.ran() == "hero --loops 1"

    def test_without_a_character_passes_the_arguments_through(self, release):
        result = release.run(release.script(character=""), "wizard", "--mood", "happy")

        assert result.returncode == 0, result.stderr
        assert release.ran() == "wizard --mood happy"

    def test_maps_a_full_release_version_to_its_tag(self, release):
        release.run(release.script(version="2.1.0"))

        assert release.fetched() == ["https://github.com/bkahlert/pihero/releases/download/v2.1.0/kaomoji-linux-arm64"]

    @pytest.mark.parametrize(
        ("os_", "arch", "asset"),
        [("Darwin", "arm64", "kaomoji-darwin-arm64"), ("Darwin", "x86_64", "kaomoji-darwin-amd64"), ("Linux", "x86_64", "kaomoji-linux-amd64"), ("Linux", "armv7l", "kaomoji-linux-armv6"), ("Linux", "armv6l", "kaomoji-linux-armv6"), ("Linux", "armv8l", "kaomoji-linux-armv6")],
    )
    def test_picks_the_asset_by_os_and_architecture(self, release, os_, arch, asset):
        (release.assets / asset).write_bytes(release.binary.read_bytes())

        release.run(release.script(), os_=os_, arch=arch)

        assert release.fetched()[0].endswith("/" + asset)

    def test_refuses_a_machine_without_a_binary(self, release):
        result = release.run(release.script(), arch="mips")

        assert result.returncode == 1
        assert result.stderr == "kaomoji: no binary for Linux mips\n"
        assert release.fetched() == []

    def test_refuses_a_download_whose_hash_does_not_match_and_leaves_no_file(self, release):
        result = release.run(release.script(sha="0" * 64))

        assert result.returncode == 1
        assert result.stderr == "kaomoji: checksum mismatch for kaomoji-linux-arm64\n"
        assert list((release.cache / "kaomoji" / "2.1.0~rc.1").iterdir()) == []

    def test_runs_nothing_when_cut_short(self, release):
        script = release.script()
        lines = script.read_text().splitlines(keepends=True)
        script.write_text("".join(lines[: len(lines) // 2]))  # a download that ended halfway through

        result = release.run(script)

        assert release.fetched() == [] and not (release.dir / "run.log").exists()
        assert result.returncode in (0, 2)  # sh reads the truncated text, finds no call, or chokes on a cut construct
