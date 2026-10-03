from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest

from pihero_testkit.preview import flavors, layer, record
from pihero_testkit.preview.api import DevServer, Settings

pytestmark = pytest.mark.tier0
DEV = DevServer(["serve"], 8081)


class TestServed:
    def test_the_browser_reaches_the_mac_on_localhost(self):
        assert flavors.served_for("browser").address(8081) == "localhost:8081"

    def test_the_vm_reaches_the_mac_at_qemus_host_address(self):
        assert flavors.served_for("vm").address(8081) == "10.0.2.2:8081"

    def test_the_board_reaches_the_mac_through_the_reverse_port(self):
        assert flavors.served_for("device").address(8081) == "127.0.0.1:18081"

    def test_each_names_its_flavor(self):
        assert [flavors.served_for(f).flavor for f in ("browser", "vm", "device")] == ["browser", "vm", "device"]


class TestMacPorts:
    def test_are_the_dev_servers_and_a_backend_on_the_mac(self):
        assert flavors.mac_ports(DEV, backend(mac_port=8080)) == [8081, 8080]

    def test_leave_out_a_backend_elsewhere(self):
        assert flavors.mac_ports(DEV, backend(mac_port=None)) == [8081]


class TestBrowser:
    def test_shows_the_apps_page_url_with_nothing_to_inspect(self, tmp_path):
        shown = flavors.Browser().show(app(), Settings("browser", None, "Safari", {}), backend(), DEV, ExitStack(), record.Record(tmp_path))

        assert shown == flavors.Shown("http://localhost:8081/?x=1")
        assert shown.inspector is None and shown.watch is None


class TestVm:
    def test_builds_the_layer_boots_places_configures_and_tunnels(self, tmp_path):
        session = FakeSession()
        rec = record.Record(tmp_path)
        rec.update()
        made = {}

        def make_session(found_layer, directory, display):
            made.update(layer=found_layer, directory=directory, display=display)
            return session

        with ExitStack() as cleanup:
            shown = flavors.Vm(ensure_layer=lambda a: LAYER, make_session=make_session, free_port=lambda: 54321, entry=lambda pid: [pid, "T"]).show(app(), Settings("vm", None, "Safari", {}), backend(), DEV, cleanup, rec)

            assert made == {"layer": LAYER, "directory": tmp_path / "session", "display": (800, 480)}
            assert session.calls == ["start", "place_window", "configure_kiosk http://10.0.2.2:8081/?x=1", "open_tunnel 54321"]
            assert shown == flavors.Shown("http://localhost:8081/", "127.0.0.1:54321")
            assert rec.read() == {"qemu": [4242, "T"], "inspector": 54321}
        assert session.calls[-1] == "stop"

    def test_watch_is_quiet_while_qemu_runs(self, tmp_path):
        with ExitStack() as cleanup:
            shown = flavors.Vm(ensure_layer=lambda a: LAYER, make_session=lambda *a: FakeSession(), free_port=lambda: 1, entry=lambda pid: None).show(app(), Settings("vm", None, None, {}), backend(), DEV, cleanup, record.Record(tmp_path))

            problem = shown.watch()

        assert problem is None

    def test_watch_reports_that_qemu_ended_naming_the_kept_serial_log(self, tmp_path):
        session = FakeSession()

        with ExitStack() as cleanup:
            shown = flavors.Vm(ensure_layer=lambda a: LAYER, make_session=lambda *a: session, free_port=lambda: 1, entry=lambda pid: None).show(app(), Settings("vm", None, None, {}), backend(), DEV, cleanup, record.Record(tmp_path))
            session.vm.process.poll = lambda: 1

            problem = shown.watch()

        assert problem == "the VM's QEMU ended; see /state/serial.log"

    def test_stops_the_session_when_the_kiosk_fails_to_load(self, tmp_path):
        session = FakeSession(fail_kiosk=True)

        with pytest.raises(TimeoutError), ExitStack() as cleanup:
            flavors.Vm(ensure_layer=lambda a: LAYER, make_session=lambda *a: session, free_port=lambda: 1, entry=lambda pid: None).show(app(), Settings("vm", None, None, {}), backend(), DEV, cleanup, record.Record(tmp_path))

        assert session.calls[-1] == "stop"


class TestDevice:
    def test_checks_tunnels_installs_and_restores_at_the_end(self, tmp_path):
        b = FakeBoard()
        rec = record.Record(tmp_path)
        rec.update()
        made = {}

        def make_board(target, name, log):
            made.update(target=target, name=name, log=log)
            return b

        with ExitStack() as cleanup:
            shown = flavors.Device(make_board=make_board, free_port=lambda: 54321, entry=lambda pid: [pid, "T"]).show(app(), Settings("device", "pi@host", None, {}), backend(mac_port=8080), DEV, cleanup, rec)

            assert made == {"target": "pi@host", "name": "probe", "log": tmp_path / "tunnel.log"}
            assert b.calls[:3] == ["check_kiosk", "session_conf http://127.0.0.1:18081/?x=1", "open_tunnel ['-R', '127.0.0.1:18081:127.0.0.1:8081', '-R', '127.0.0.1:18080:127.0.0.1:8080', '-L', '127.0.0.1:54321:127.0.0.1:2999'] 54321 [18081, 18080]"]
            assert b.calls[3] == "install CONF"
            assert rec.read() == {"tunnel": [9, "T"], "device": "pi@host", "inspector": 54321}
            assert shown.page == "http://localhost:8081/" and shown.inspector == "127.0.0.1:54321"
            assert shown.watch() == "problem"
        assert b.calls[4:] == ["restore", "close_tunnel"]
        assert rec.read()["device"] is None

    def test_keeps_the_board_in_the_record_when_restore_fails(self, tmp_path):
        b = FakeBoard(restores=False)
        rec = record.Record(tmp_path)
        rec.update()

        with ExitStack() as cleanup:
            flavors.Device(make_board=lambda *a: b, free_port=lambda: 1, entry=lambda pid: [pid, "T"]).show(app(), Settings("device", "pi@host", None, {}), backend(), DEV, cleanup, rec)

        assert rec.read()["device"] == "pi@host"


    def test_restores_the_board_and_closes_the_tunnel_when_install_fails(self, tmp_path):
        b = FakeBoard(fail_install=True)
        rec = record.Record(tmp_path)
        rec.update()

        with pytest.raises(TimeoutError), ExitStack() as cleanup:
            flavors.Device(make_board=lambda *a: b, free_port=lambda: 1, entry=lambda pid: [pid, "T"]).show(app(), Settings("device", "pi@host", None, {}), backend(), DEV, cleanup, rec)

        assert b.calls[-2:] == ["restore", "close_tunnel"]
        assert rec.read()["device"] is None


class TestFlavorFor:
    @pytest.mark.parametrize("name, cls", [("browser", flavors.Browser), ("vm", flavors.Vm), ("device", flavors.Device)])
    def test_names_the_flavor(self, name, cls):
        assert isinstance(flavors.flavor_for(name), cls)


LAYER = layer.Layer(Path("/l/rootfs.qcow2"), Path("/l/bootfs.img"))


def app():
    return SimpleNamespace(name="probe", root=Path("/repo"), display=(800, 480), page_url=lambda backend, served: f"http://{served.address(8081)}/?x=1")


def backend(mac_port=None):
    return SimpleNamespace(managed=False, mac_port=mac_port, start=lambda: None, stop=lambda: None, describe=lambda: "none")


class FakeSession:
    def __init__(self, fail_kiosk: bool = False):
        self.calls, self.fail_kiosk = [], fail_kiosk
        self.vm = SimpleNamespace(process=SimpleNamespace(pid=4242, poll=lambda: None))

    def start(self, on_qemu=None):
        self.calls.append("start")
        if on_qemu:
            on_qemu(4242)

    def place_window(self):
        self.calls.append("place_window")
        return True

    def configure_kiosk(self, url):
        self.calls.append(f"configure_kiosk {url}")
        if self.fail_kiosk:
            raise TimeoutError("did not load")

    def open_tunnel(self, local_port):
        self.calls.append(f"open_tunnel {local_port}")

    def keep_serial_log(self):
        return Path("/state/serial.log")

    def stop(self):
        self.calls.append("stop")


class FakeBoard:
    def __init__(self, restores: bool = True, fail_install: bool = False):
        self.calls, self.restores, self.fail_install = [], restores, fail_install

    def check_kiosk(self):
        self.calls.append("check_kiosk")

    def session_conf(self, url):
        self.calls.append(f"session_conf {url}")
        return "CONF"

    def open_tunnel(self, forward_args, inspector_local, remote_ports):
        self.calls.append(f"open_tunnel {forward_args} {inspector_local} {remote_ports}")
        return SimpleNamespace(pid=9, poll=lambda: None)

    def install(self, conf, tunnel):
        self.calls.append(f"install {conf}")
        if self.fail_install:
            raise TimeoutError("did not load")

    def restore(self):
        self.calls.append("restore")
        return self.restores

    def tunnel_problem(self, tunnel):
        return "problem"

    def close_tunnel(self, tunnel):
        self.calls.append("close_tunnel")
