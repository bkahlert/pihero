import time

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

    def test_apt_knows_the_pihero_source(self, host):
        assert host.file("/etc/apt/sources.list.d/pihero.sources").exists
        assert "10.0.2.2:8000" in host.check_output("apt-cache policy")

    def test_cloud_init_performed_the_requested_reboot(self, host):
        log = host.file("/var/log/cloud-init.log").content_string

        assert "check_condition command (test -f /run/reboot-required): exited 0. condition met." in log


class TestWatchdog:
    def test_is_armed(self, host):
        assert host.check_output("systemctl show --property=RuntimeWatchdogUSec").strip() == "RuntimeWatchdogUSec=15s"


class TestAvahi:
    def test_advertises_the_pretty_hostname(self, host):
        browse = browse_until(host, "_device-info._tcp", "All\\032Features")

        assert "All\\032Features" in browse


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


def browse_until(host, service_type: str, needle: str, attempts: int = 10) -> str:
    output = ""
    for _ in range(attempts):
        output = host.run(f"avahi-browse -rpt {service_type}").stdout
        if needle in output:
            return output
        time.sleep(1)
    return output
