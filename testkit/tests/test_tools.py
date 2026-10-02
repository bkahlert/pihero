import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from pihero_testkit import tools

pytestmark = pytest.mark.tier0


class TestImage:
    def test_names_the_tools_image_as_before(self):
        tag = tools.image()

        assert tag == f"localhost/pihero-tools:{hashlib.sha256(tools.CONTAINERFILE.read_bytes()).hexdigest()[:12]}"

    def test_names_another_image_after_its_directory(self, tmp_path):
        containerfile = containerfile_in(tmp_path / "cog", "FROM scratch\n")

        tag = tools.image(containerfile)

        assert tag.startswith("localhost/pihero-cog:")

    def test_changes_with_the_content(self, tmp_path):
        containerfile = containerfile_in(tmp_path / "cog", "FROM scratch\n")
        before = tools.image(containerfile)
        containerfile.write_text("FROM scratch\n# probe\n")

        after = tools.image(containerfile)

        assert after != before


class TestCommand:
    def test_mounts_the_repository_and_ends_with_the_image_and_the_arguments(self):
        command = tools.command(["sh", "-c", "true"], image="localhost/probe:1")

        assert command[: len(tools.PODMAN)] == tools.PODMAN
        assert f"{Path.cwd()}:/work" in command
        assert command[-4:] == ["localhost/probe:1", "sh", "-c", "true"]

    def test_passes_workdir_environment_and_mounts(self):
        command = tools.command(["true"], workdir="/work/packages/cog", env={"A": "1"}, mounts=["/x:/y:ro"], image="localhost/probe:1")

        assert command[command.index("-w") + 1] == "/work/packages/cog"
        assert "A=1" in command
        assert "/x:/y:ro" in command


def containerfile_in(directory: Path, content: str) -> Path:
    directory.mkdir()
    containerfile = directory / "Containerfile"
    containerfile.write_text(content)
    return containerfile


class TestMain:
    def test_without_arguments_prints_the_tools_image(self, capsys):
        status = tools.main([])

        assert status == 0
        assert capsys.readouterr().out.strip() == tools.image()

    def test_runs_a_command_in_the_tools_image_and_returns_its_status(self):
        result = subprocess.run([sys.executable, "-m", "pihero_testkit.tools", "--", "sh", "-c", "go version; exit 3"], capture_output=True, text=True)

        assert result.returncode == 3
        assert result.stdout.startswith("go version go1.")

    def test_keeps_gos_build_cache_in_a_volume(self):
        result = subprocess.run([sys.executable, "-m", "pihero_testkit.tools", "--", "sh", "-c", "go env GOCACHE; mount | grep -c /root/.cache/go-build"], capture_output=True, text=True)

        assert result.stdout.splitlines() == ["/root/.cache/go-build", "1"]
