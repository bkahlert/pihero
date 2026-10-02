import time
from pathlib import Path

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
    def test_keeps_raspberry_pi_os_minute(self, host):
        # 2.1.0 tightened it to 15 s and reset the Zero W, whose systemd needs 13.5 s for a daemon-reload at idle.
        assert host.check_output("systemctl show --property=RuntimeWatchdogUSec").strip() == "RuntimeWatchdogUSec=1min"


class TestAvahi:
    def test_advertises_the_pretty_hostname(self, host):
        browse = browse_until(host, "_device-info._tcp", "All\\032Features")

        assert "All\\032Features" in browse


class TestDisplay:
    def test_is_connected_at_the_configured_size(self, host, target):
        if target.display is None:
            pytest.skip("no display")

        status = host.file("/sys/class/drm/card0-Virtual-1/status").content_string.strip()
        modes = host.file("/sys/class/drm/card0-Virtual-1/modes").content_string.split()

        assert status == "connected"
        assert f"{target.display[0]}x{target.display[1]}" in modes

    def test_is_pictured_as_a_png_of_its_size(self, target):
        if target.display is None:
            pytest.skip("no display")

        picture = target.screenshot(target.workdir / "display.png")

        assert png_size(picture) == target.display


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


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
