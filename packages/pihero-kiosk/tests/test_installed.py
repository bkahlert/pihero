import pytest

from pihero_testkit.ssh import SshTarget

pytestmark = pytest.mark.installed


class TestPackage:
    def test_is_installed_at_the_built_version(self, host, version):
        package = host.package("pihero-kiosk")

        assert package.is_installed
        assert package.version == version

    def test_pulls_in_cog_and_the_gles_library_its_renderer_loads_at_runtime(self, host):
        assert host.package("cog").is_installed
        assert host.package("libgles2").is_installed

    def test_ships_the_launcher_and_the_default_page(self, host):
        assert host.file("/usr/lib/pihero/kiosk").mode == 0o755
        assert host.file("/usr/share/pihero/kiosk/index.html").contains("/etc/pihero/kiosk.conf")


class TestUser:
    def test_kiosk_is_a_system_user_without_a_login(self, host):
        user = host.user("kiosk")

        assert user.exists
        assert user.uid < 1000
        assert user.shell in ("/usr/sbin/nologin", "/bin/false")


class TestUnit:
    def test_is_enabled(self, host):
        assert host.service("pihero-kiosk").is_enabled

    def test_runs_as_kiosk_with_the_hardware_groups_and_a_memory_cap(self, host):
        show = host.check_output("systemctl show -p User -p SupplementaryGroups -p MemoryMax pihero-kiosk.service")

        assert "User=kiosk" in show
        assert "SupplementaryGroups=video render input" in show
        assert "MemoryMax=314572800" in show

    def test_is_skipped_by_its_condition_without_a_display_adapter(self, host):
        if host.file("/dev/dri").exists:
            pytest.skip("has a display adapter")

        states = host.check_output("systemctl show --property=ActiveState --property=ConditionResult --value pihero-kiosk.service").split()

        assert states == ["inactive", "no"]

    def test_is_running_with_a_connected_display(self, host):
        # A container shares the host's /sys, which may list a connected connector, while the unit's condition looks at /dev.
        if not host.file("/dev/dri").exists:
            pytest.skip("no display adapter")
        statuses = host.run("cat /sys/class/drm/card*-*/status").stdout.split()
        if "connected" not in statuses:
            pytest.skip("no connected display")

        assert host.service("pihero-kiosk").is_running

    def test_has_not_restarted_since_the_vm_booted(self, host, target):
        if isinstance(target, SshTarget):
            pytest.skip("a board's restart count spans its uptime")
        if not host.file("/dev/dri").exists:
            pytest.skip("no display adapter")
        if "connected" not in host.run("cat /sys/class/drm/card*-*/status").stdout.split():
            pytest.skip("no connected display")

        restarts = host.check_output("systemctl show -p NRestarts --value pihero-kiosk.service").strip()

        assert restarts == "0"


class TestStop:
    def test_a_stop_leaves_the_unit_inactive_not_failed(self, host):
        if not host.service("pihero-kiosk").is_running:
            pytest.skip("the kiosk runs only with a connected display")

        host.check_output("sudo systemctl stop pihero-kiosk.service")
        state = host.check_output("systemctl show -p ActiveState --value pihero-kiosk.service").strip()
        result = host.check_output("systemctl show -p Result --value pihero-kiosk.service").strip()
        host.check_output("sudo systemctl start pihero-kiosk.service")

        assert (state, result) == ("inactive", "success")


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_leaves_nothing_behind(self, host, target):
        target.purge(["pihero-kiosk"])

        assert not host.file("/usr/lib/pihero/kiosk").exists
        assert not host.file("/usr/lib/systemd/system/pihero-kiosk.service").exists
        assert not host.file("/var/lib/pihero-kiosk").exists
        assert not host.user("kiosk").exists

        target.reinstall()
