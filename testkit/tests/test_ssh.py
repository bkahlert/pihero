import subprocess

import pytest

from pihero_testkit import deploy, ssh

pytestmark = pytest.mark.tier0

STATUS = "arm64\nbash ii \nkaomoji ii \npihero ii \npihero-avahi ii \npihero-usb-gadget rc \n"


class TestInstalledPackages:
    def test_asks_dpkg_over_ssh_in_batch_mode(self, monkeypatch):
        calls = fake_ssh(monkeypatch, STATUS)

        ssh.installed_packages("pi@host")

        assert calls == [["ssh", "-o", "BatchMode=yes", "pi@host", deploy.STATUS_QUERY]]

    def test_passes_the_port_of_the_uri(self, monkeypatch):
        calls = fake_ssh(monkeypatch, STATUS)

        ssh.installed_packages("pi@host:2222")

        assert calls == [["ssh", "-o", "BatchMode=yes", "-p", "2222", "pi@host", deploy.STATUS_QUERY]]

    def test_returns_the_names_dpkg_reports_installed(self, monkeypatch):
        fake_ssh(monkeypatch, STATUS)

        names = ssh.installed_packages("pi@host")

        assert names == {"bash", "kaomoji", "pihero", "pihero-avahi"}

    def test_exits_when_the_device_cannot_be_asked(self, monkeypatch):
        fake_ssh(monkeypatch, "", returncode=255, stderr="ssh: connect to host host port 22: Connection refused")

        with pytest.raises(SystemExit, match="pi@host.*Connection refused"):
            ssh.installed_packages("pi@host")

    def test_exits_without_a_uri(self):
        with pytest.raises(SystemExit, match="--target-uri"):
            ssh.installed_packages("")


def fake_ssh(monkeypatch, stdout: str, returncode: int = 0, stderr: str = "") -> list[list[str]]:
    calls: list[list[str]] = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(ssh.subprocess, "run", run)
    return calls
