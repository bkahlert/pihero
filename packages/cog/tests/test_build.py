import subprocess
from pathlib import Path

import pytest

from pihero_testkit import build, tools

pytestmark = pytest.mark.tier0
PACKAGE = Path(__file__).resolve().parents[1]
VERSION = "0.18.4-1+pihero1"


class TestBuildScript:
    def test_reuses_a_deb_that_exists(self):
        dist = Path.cwd() / "dist" / "probe-cog"
        dist.mkdir(parents=True, exist_ok=True)
        deb = dist / f"cog_{VERSION}_arm64.deb"
        deb.write_bytes(b"")
        image = tools.ensure_image(PACKAGE / "Containerfile", build.TARGET_PLATFORM)
        try:
            result = tools.run(["/work/packages/cog/build", "--dist", "/work/dist/probe-cog"], image=image, capture=True)

            assert result.stdout.strip() == f"/work/dist/probe-cog/cog_{VERSION}_arm64.deb"
            assert deb.stat().st_size == 0
        finally:
            subprocess.run(["rm", "-rf", str(dist)], check=True)
