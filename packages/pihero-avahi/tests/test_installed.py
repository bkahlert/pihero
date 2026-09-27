import time

import pytest

pytestmark = pytest.mark.installed


class TestUnit:
    def test_is_enabled_and_active(self, host):
        unit = host.service("pihero-avahi-render")

        assert unit.is_enabled
        assert unit.is_running


class TestRecords:
    def test_files_are_rendered(self, host):
        assert host.file("/etc/avahi/services/pihero-device-info.service").contains("_device-info._tcp")
        assert host.file("/etc/avahi/services/pihero-ssh.service").contains("_sftp-ssh._tcp")

    def test_device_info_is_advertised(self, host, avahi_utils):
        browse = browse_until(host, "_device-info._tcp", "model=")

        expected = configured_model(host) or "AirPort4"
        assert f"model={expected}" in browse

    def test_ssh_is_advertised(self, host, avahi_utils):
        browse = browse_until(host, "_ssh._tcp", ";22;")

        assert ";22;" in browse

    def test_machine_record_follows_the_device_tree(self, host, avahi_utils):
        browse = browse_until(host, "_device-info._tcp", "model=")

        device_tree = host.file("/proc/device-tree/model")
        if device_tree.exists:
            assert f"machine={device_tree.content.rstrip(b'\x00').decode()}" in browse
        else:
            assert "machine=" not in browse


class TestOverride:
    @pytest.mark.mutating
    def test_model_from_the_conffile_is_applied_on_restart(self, host, avahi_utils):
        previous = host.file("/etc/pihero/device-info.conf").content_string if host.file("/etc/pihero/device-info.conf").exists else None
        host.check_output("sudo mkdir -p /etc/pihero && printf 'MODEL=Xserve\\n' | sudo tee /etc/pihero/device-info.conf >/dev/null")

        host.check_output("sudo systemctl restart pihero-avahi-render.service")

        assert "model=Xserve" in browse_until(host, "_device-info._tcp", "model=Xserve")
        restore = f"printf '%s' '{previous}' | sudo tee /etc/pihero/device-info.conf >/dev/null" if previous else "sudo rm -f /etc/pihero/device-info.conf"
        host.check_output(restore + " && sudo systemctl restart pihero-avahi-render.service")


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_removes_the_rendered_records(self, host, target):
        target.purge(["pihero-avahi"])

        assert not host.file("/etc/avahi/services/pihero-device-info.service").exists
        assert not host.file("/etc/avahi/services/pihero-ssh.service").exists

        target.reinstall()


@pytest.fixture(scope="module")
def avahi_utils(request, target):
    if target.host.exists("avahi-browse"):
        return
    if request.config.getoption("--target") == "ssh":
        pytest.skip("avahi-utils is not installed on the device")
    target.install_extra(["avahi-utils"])


def configured_model(host) -> str | None:
    conf = host.file("/etc/pihero/device-info.conf")
    if not conf.exists:
        return None
    for line in conf.content_string.splitlines():
        if line.startswith("MODEL="):
            return line.removeprefix("MODEL=").strip()
    return None


def browse_until(host, service_type: str, needle: str, attempts: int = 10) -> str:
    output = ""
    for _ in range(attempts):
        output = host.run(f"avahi-browse -rpt {service_type}").stdout
        if needle in output:
            return output
        time.sleep(1)
    return output
