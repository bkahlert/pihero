import pytest

pytestmark = pytest.mark.installed


class TestPackage:
    def test_is_installed_at_the_built_version(self, host, version):
        package = host.package("pihero-usb-gadget")

        assert package.is_installed
        assert package.version == version

    def test_pulls_in_rpi_usb_gadget(self, host):
        assert host.package("rpi-usb-gadget").is_installed

    def test_ships_the_loader_owned_by_root(self, host):
        file = host.file("/usr/lib/pihero/usb-gadget")

        assert file.exists
        assert file.mode == 0o755
        assert file.user == "root"

    def test_blacklists_g_ether(self, host):
        assert host.file("/usr/lib/modprobe.d/pihero-usb-gadget.conf").contains("^blacklist g_ether$")


class TestUnit:
    def test_is_enabled(self, host):
        assert host.service("pihero-usb-gadget").is_enabled

    def test_is_active_on_a_raspberry_pi(self, host, raspberry_pi_only):
        assert host.service("pihero-usb-gadget").is_running

    def test_is_skipped_by_its_condition_without_a_device_controller(self, host):
        if raspberry_pi(host):
            pytest.skip("runs on a Raspberry Pi")

        load_state = host.check_output("systemctl show --property=LoadState --value pihero-usb-gadget.service").strip()
        active_state = host.check_output("systemctl show --property=ActiveState --value pihero-usb-gadget.service").strip()
        condition_result = host.check_output("systemctl show --property=ConditionResult --value pihero-usb-gadget.service").strip()

        assert (load_state, active_state, condition_result) == ("loaded", "inactive", "no")


class TestGadget:
    def test_is_named_after_the_board_or_the_conffile(self, host, raspberry_pi_only):
        expected = configured(host, "PRODUCT") or model(host)

        product = host.file("/sys/module/g_cdc/parameters/iProduct").content_string.strip()

        assert product == expected

    def test_derives_the_host_mac_from_the_serial(self, host, raspberry_pi_only):
        serial = host.file("/proc/device-tree/serial-number").content.rstrip(b"\x00").decode()
        tail = serial[-10:]
        expected = "02:" + ":".join(tail[i:i + 2] for i in range(0, 10, 2))

        host_addr = host.file("/sys/module/g_cdc/parameters/host_addr").content_string.strip()

        assert host_addr == expected

    def test_brings_up_usb0(self, host, raspberry_pi_only):
        assert host.interface("usb0").exists


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_leaves_nothing_behind(self, host, target):
        target.purge(["pihero-usb-gadget"])

        assert not host.file("/usr/lib/pihero/usb-gadget").exists
        assert not host.file("/usr/lib/systemd/system/pihero-usb-gadget.service").exists
        assert not host.file("/usr/lib/modprobe.d/pihero-usb-gadget.conf").exists

        target.reinstall()


@pytest.fixture
def raspberry_pi_only(host):
    if not raspberry_pi(host):
        pytest.skip("needs a Raspberry Pi")


def raspberry_pi(host) -> bool:
    return "Raspberry Pi" in model(host)


def model(host) -> str:
    file = host.file("/proc/device-tree/model")
    return file.content.rstrip(b"\x00").decode() if file.exists else ""


def configured(host, key: str) -> str | None:
    conf = host.file("/etc/pihero/usb-gadget.conf")
    if not conf.exists:
        return None
    for line in conf.content_string.splitlines():
        if line.startswith(f"{key}="):
            return line.removeprefix(f"{key}=").strip().strip('"')
    return None
