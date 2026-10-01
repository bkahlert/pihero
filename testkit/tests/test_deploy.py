import subprocess
from pathlib import Path

import pytest

from pihero_testkit import deploy

pytestmark = pytest.mark.tier0

STATUS = "bash ii \nkaomoji ii \npihero ii \npihero-avahi ii \npihero-usb-gadget rc \npihero-kiosk iF \n"
DEBS = [Path(f"dist/{name}_2.3.0_all.deb") for name in ["kaomoji", "pihero", "pihero-avahi", "pihero-kiosk", "pihero-usb-gadget"]]


class TestInstalled:
    def test_lists_the_packages_dpkg_reports_installed(self):
        names = deploy.installed(STATUS)

        assert names == {"bash", "kaomoji", "pihero", "pihero-avahi"}

    def test_is_empty_on_no_output(self):
        names = deploy.installed("")

        assert names == set()


class TestSelect:
    def test_keeps_the_debs_of_installed_packages_in_build_order(self):
        debs = deploy.select(DEBS, {"pihero-avahi", "pihero", "kaomoji"})

        assert debs == DEBS[:3]

    def test_tells_a_package_from_the_siblings_sharing_its_prefix(self):
        debs = deploy.select(DEBS, {"pihero"})

        assert debs == [DEBS[1]]


class TestMain:
    def test_copies_and_reinstalls_only_the_packages_the_target_has(self, monkeypatch):
        calls = fake_target(monkeypatch, STATUS)

        rc = deploy.main(["pi@host"])

        assert rc == 0
        assert calls[0][0] == "ssh" and "dpkg-query" in calls[0][2]
        assert calls[2] == ["scp", "-q", *map(str, DEBS[:3]), "pi@host:/tmp/pihero-deploy/"]
        assert calls[3][0] == "ssh" and "apt-get install" in calls[3][2]

    def test_exits_2_on_a_target_with_none_of_the_packages(self, monkeypatch, capsys):
        calls = fake_target(monkeypatch, "bash ii \n")

        rc = deploy.main(["pi@host"])

        assert rc == 2
        assert len(calls) == 1
        assert "flash" in capsys.readouterr().err


def fake_target(monkeypatch, status: str) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=status, stderr="")

    monkeypatch.setattr(deploy.subprocess, "run", run)
    monkeypatch.setattr(deploy.build, "version_from_git", lambda: "2.3.0")
    monkeypatch.setattr(deploy.build, "build_all", lambda version: DEBS)
    return calls
