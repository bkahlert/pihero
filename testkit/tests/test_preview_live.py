import http.server
import struct
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from pihero_testkit import device_file
from pihero_testkit.preview import flavors, kiosk, layer, process, record, vm, window

pytestmark = [pytest.mark.preview, pytest.mark.skipif(sys.platform != "darwin", reason="the window is a macOS window")]
REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "devices" / "sample" / "user-data"


class TestVmSession:
    def test_keeps_the_guest_at_the_apps_display_whatever_the_window_does(self, session):
        resized = window.place(session.vm.process.pid, (1000, 668))
        session.restart_kiosk()

        assert (resized, picture_size(session)) == (True, (800, 480))

    def test_tunnels_the_inspector_of_a_page_served_from_the_macs_loopback(self, session):
        port = process.free_port()
        session.open_tunnel(port)

        listing = wait_for_listing(port)

        assert kiosk.inspector_url(listing, f"127.0.0.1:{port}") is not None

    def test_the_guest_fetched_the_page_from_the_macs_server(self, session, page):
        assert "/" in page.requests


class TestRecovery:
    def test_the_next_start_ends_the_qemu_a_killed_record_names(self, session, tmp_path):
        rec = record.Record(tmp_path)
        rec.update(owner=[999999, "gone"], qemu=process.entry(session.vm.process.pid))

        rec.claim(stop_backend=lambda: None, restore_board=lambda t: None)

        assert session.vm.process.poll() is not None


class Page:
    def __init__(self, port: int, requests: list[str]):
        self.port, self.requests = port, requests


class StaticApp:
    name = "pihero-preview-probe"
    display = (800, 480)

    def __init__(self, root: Path, port: int):
        self.root, self.port = root, port

    def user_data(self) -> str:
        text = device_file.with_user(SAMPLE.read_text(), device_file.PUBLIC_KEY.read_text().strip())
        return text.replace("  - pihero\n", f"  - pihero\n  - {kiosk.PACKAGE}\n", 1)

    def dev_server(self, settings):
        raise NotImplementedError

    def backend(self, settings):
        raise NotImplementedError

    def page_url(self, backend, served) -> str:
        return f"http://{served.address(self.port)}/"


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    directory = tmp_path_factory.mktemp("page")
    (directory / "index.html").write_text("<h1>preview</h1>")
    requests = []

    class Recording(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def do_GET(self):
            requests.append(self.path)
            super().do_GET()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Recording)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield Page(server.server_address[1], requests)
    server.shutdown()


@pytest.fixture(scope="module")
def session(request, tmp_path_factory, page):
    app = StaticApp(tmp_path_factory.mktemp("root"), page.port)
    started = vm.Session(layer.ensure(app), app.root / "dist" / "preview" / "session", app.display)
    request.addfinalizer(started.stop)
    started.start()
    started.place_window()
    started.configure_kiosk(app.page_url(None, flavors.VmServed()))
    return started


def picture_size(session) -> tuple[int, int]:
    png = session.directory / "picture.png"
    session.vm.screenshot(png)
    return struct.unpack(">II", png.read_bytes()[16:24])


def wait_for_listing(port: int) -> str:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            listing = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3).read().decode()
            if "socket/" in listing:
                return listing
        except OSError:
            pass
        time.sleep(1)
    raise AssertionError("the inspector's page list named no target within 60 seconds")
