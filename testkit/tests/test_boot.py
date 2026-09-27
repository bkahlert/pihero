import pytest

pytestmark = pytest.mark.boot


class TestProvisioning:
    def test_cloud_init_finished_without_errors(self, host):
        status = host.check_output("cloud-init status --long")

        assert "status: done" in status
        assert "errors: []" in status

    def test_boot_partition_is_the_bootfs_image(self, host):
        assert host.mount_point("/boot/firmware").exists
        assert host.file("/boot/firmware/user-data").exists

    def test_no_unit_failed(self, host):
        assert host.check_output("systemctl --failed --no-legend --plain").strip() == ""

    def test_no_reboot_is_pending(self, host):
        assert not host.file("/run/reboot-required").exists

    def test_pretty_hostname_was_applied(self, host):
        assert host.check_output("hostnamectl --pretty").strip() == "All Features"


class TestWatchdog:
    def test_is_armed(self, host):
        assert host.check_output("systemctl show --property=RuntimeWatchdogUSec").strip() == "RuntimeWatchdogUSec=15s"


class TestBootConfigRoundTrip:
    @pytest.mark.mutating
    def test_cmdline_edit_survives_a_reboot(self, target):
        target.host.check_output("sudo /usr/lib/pihero/bootconfig add cmdline pihero.marker=1 --package pihero-probe")
        assert target.host.file("/run/reboot-required").exists

        target.reboot()

        assert "pihero.marker=1" in target.host.file("/proc/cmdline").content_string
        assert not target.host.file("/run/reboot-required").exists
        target.host.check_output("sudo /usr/lib/pihero/bootconfig remove cmdline pihero.marker")
        # The remove is itself a change and re-touches the flag.
        target.host.check_output("sudo rm -f /run/reboot-required /run/reboot-required.pkgs")
