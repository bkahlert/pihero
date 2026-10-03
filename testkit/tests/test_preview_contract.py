from pathlib import Path

import pytest

from pihero_testkit.preview import kiosk
from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0
PACKAGE = Path(__file__).resolve().parents[2] / "packages" / "pihero-kiosk"
UNIT_FILE = PACKAGE / "root" / "usr" / "lib" / "systemd" / "system" / f"{kiosk.UNIT}.service"
SCRIPT = PACKAGE / "root" / "usr" / "lib" / "pihero" / "kiosk"


class TestKioskContract:
    def test_the_unit_the_preview_restarts_exists(self):
        assert UNIT_FILE.exists()

    def test_the_unit_reads_the_file_the_preview_rewrites(self):
        assert f"EnvironmentFile=-{kiosk.CONF}\n" in UNIT_FILE.read_text()

    def test_the_package_the_preview_installs_is_this_one(self):
        assert f"name: {kiosk.PACKAGE}\n" in (PACKAGE / "nfpm.yaml").read_text()

    def test_the_script_hands_cog_the_variables_the_session_writes(self):
        script = load_script(SCRIPT)
        script.reachable = lambda url, timeout=5.0: True
        environ = kiosk.parse_conf(kiosk.session_conf('COG_ARGS="--doc-viewer"\n', "http://10.0.2.2:8081/"))
        argv = []

        script.main([], environ=environ, execvp=lambda file, args: argv.extend(args))

        assert argv == ["cog", "--platform=drm", "--enable-developer-extras=true", "--doc-viewer", "http://10.0.2.2:8081/"]
