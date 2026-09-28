import pytest

pytestmark = pytest.mark.installed


class TestPackage:
    def test_is_installed_at_the_built_version(self, host, version):
        package = host.package("pihero")

        assert package.is_installed
        assert package.version == version

    @pytest.mark.parametrize("path", ["/usr/lib/pihero/bootconfig", "/usr/lib/pihero/motd", "/etc/update-motd.d/50-pihero"])
    def test_ships_executables_owned_by_root(self, host, path):
        file = host.file(path)

        assert file.exists
        assert file.mode == 0o755
        assert file.user == "root"


class TestMotd:
    def test_reports_the_installed_packages(self, host, version):
        output = host.check_output("/usr/lib/pihero/motd")

        assert f"pihero {version}" in output
        assert "failed units:" in output


class TestBootconfig:
    @pytest.mark.mutating
    def test_edits_cmdline_and_flags_a_reboot(self, host):
        host.check_output("sudo /usr/lib/pihero/bootconfig add cmdline pihero.probe=1 --package pihero-probe")

        assert "pihero.probe=1" in host.file("/boot/firmware/cmdline.txt").content_string
        assert host.file("/run/reboot-required").exists
        assert host.file("/run/reboot-required.pkgs").contains("pihero-probe")
        assert "reboot required: yes (pihero-probe)" in host.check_output("/usr/lib/pihero/motd")

        host.check_output("sudo /usr/lib/pihero/bootconfig remove cmdline pihero.probe --package pihero-probe")

        assert "pihero.probe" not in host.file("/boot/firmware/cmdline.txt").content_string

        host.check_output("sudo rm -f /run/reboot-required /run/reboot-required.pkgs")


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_leaves_nothing_behind(self, host, target):
        target.purge(["pihero"])

        assert not host.file("/usr/lib/pihero/bootconfig").exists
        assert not host.file("/etc/update-motd.d/50-pihero").exists

        target.reinstall()
