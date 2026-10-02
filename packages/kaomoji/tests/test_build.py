import hashlib
import platform
import subprocess
from pathlib import Path

import pytest

from pihero_testkit import build, tools

pytestmark = pytest.mark.tier0

PACKAGE = Path(__file__).resolve().parents[1]
BINARIES = ["kaomoji-darwin-amd64", "kaomoji-darwin-arm64", "kaomoji-linux-amd64", "kaomoji-linux-arm64", "kaomoji-linux-armv6"]


@pytest.fixture(scope="module")
def built():
    """The build script run once for this module into dist/probe-kaomoji: the debs it printed and the directory."""
    dist = Path.cwd() / "dist" / "probe-kaomoji"
    try:
        yield build.build_in_tools(PACKAGE, "9.9.9", dist=dist), dist
    finally:
        subprocess.run(["rm", "-rf", str(dist)], check=True)


class TestDebs:
    def test_builds_one_deb_per_linux_architecture(self, built):
        debs, _ = built

        assert sorted(deb.name for deb in debs) == ["kaomoji_9.9.9_amd64.deb", "kaomoji_9.9.9_arm64.deb", "kaomoji_9.9.9_armhf.deb"]

    @pytest.mark.parametrize("arch", ["armhf", "arm64", "amd64"])
    def test_ships_the_binary_for_its_architecture_and_nothing_else(self, built, arch):
        _, dist = built
        deb = f"/work/{(dist / f'kaomoji_9.9.9_{arch}.deb').relative_to(Path.cwd())}"

        info = tools.run(["dpkg-deb", "--info", deb], capture=True).stdout
        contents = tools.run(["dpkg-deb", "--contents", deb], capture=True).stdout

        assert f" Architecture: {arch}" in info and " Version: 9.9.9" in info and " Section: admin" in info
        assert " Depends:" not in info
        files = [line.split()[-1] for line in contents.splitlines() if not line.split()[-1].endswith("/")]
        assert files == ["./usr/bin/kaomoji"]
        assert contents.splitlines()[-1].startswith("-rwxr-xr-x")


class TestBinaries:
    def test_builds_five_static_binaries(self, built):
        _, dist = built

        assert sorted(path.name for path in dist.glob("kaomoji-*")) == BINARIES
        assert (dist / "kaomoji-linux-armv6").read_bytes()[:5] == b"\x7fELF\x01"  # 32-bit ELF
        assert (dist / "kaomoji-linux-arm64").read_bytes()[:5] == b"\x7fELF\x02"

    def test_links_the_version_in(self, built):
        _, dist = built
        mine = dist / f"kaomoji-{platform.system().lower()}-{ {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'amd64'}[platform.machine()] }"

        result = subprocess.run([str(mine), "--version"], capture_output=True, text=True)

        assert result.stdout == "9.9.9\n"


class TestScripts:
    @pytest.mark.parametrize(("name", "character"), [("kaomoji", ""), ("hero", "hero"), ("wizard", "wizard"), ("visitor", "visitor")])
    def test_renders_the_bootstrap_with_the_version_the_character_and_the_hashes(self, built, name, character):
        _, dist = built
        script = (dist / name).read_text()

        assert "@VERSION@" not in script and "@NAME@" not in script and "@CHARACTER@" not in script and "@SHA256_" not in script
        assert f"version='9.9.9'" in script and f"character='{character}'" in script
        assert f"releases/latest/download/{name} |" in script
        for binary in BINARIES:
            assert f"{binary} {hashlib.sha256((dist / binary).read_bytes()).hexdigest()}" in script
        assert (dist / name).stat().st_mode & 0o111
