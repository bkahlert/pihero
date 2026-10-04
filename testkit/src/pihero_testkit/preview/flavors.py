"""The places a preview shows the page: a browser tab, the kiosk in a VM window, and the kiosk of a real board."""

from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field

from . import board, layer, process, vm
from .api import Backend, DevServer, KioskApp, Settings
from .record import Record


@dataclass(frozen=True)
class Shown:
    """What a flavor put up: the page as the Mac's browser loads it, the kiosk's inspector address (None where the page's own tools inspect it), and a check asked while the session runs."""

    page: str
    inspector: str | None = None
    watch: Callable[[], str | None] | None = field(default=None, compare=False)


class BrowserServed:
    """Serve the Mac's own browser, which reaches the Mac on localhost."""

    flavor = "browser"

    def address(self, mac_port: int) -> str:
        """Return the address of `mac_port` as the browser reaches it."""
        return f"localhost:{mac_port}"


class VmServed:
    """Serve the kiosk in the VM, which reaches the Mac at QEMU's host address."""

    flavor = "vm"

    def address(self, mac_port: int) -> str:
        """Return the address of `mac_port` as the VM reaches it."""
        return f"10.0.2.2:{mac_port}"


class BoardServed:
    """Serve the kiosk of a real board, which reaches the Mac through an SSH reverse forward."""

    flavor = "board"

    def address(self, mac_port: int) -> str:
        """Return the address of `mac_port` as the board reaches it, on its reverse port."""
        return f"127.0.0.1:{board.remote_port(mac_port)}"


def mac_ports(dev: DevServer, backend: Backend) -> list[int]:
    """Return the Mac ports the kiosk must reach: the dev server's, and the backend's when it runs on the Mac."""
    return [dev.port] + ([backend.mac_port] if backend.mac_port is not None else [])


class Browser:
    """Show the page in a tab of the Mac's own browser."""

    def show(self, app: KioskApp, settings: Settings, backend: Backend, dev: DevServer, cleanup: ExitStack, rec: Record) -> Shown:
        """Return the app's page URL as the browser loads it, with nothing to inspect."""
        return Shown(app.page_url(backend, BrowserServed()))


class Vm:
    """Show the page in the kiosk of a QEMU VM window."""

    def __init__(self, ensure_layer=layer.ensure, make_session=vm.Session, free_port=process.free_port, entry=process.entry):
        self._ensure_layer, self._make_session, self._free_port, self._entry = ensure_layer, make_session, free_port, entry

    def show(self, app: KioskApp, settings: Settings, backend: Backend, dev: DevServer, cleanup: ExitStack, rec: Record) -> Shown:
        """Boot the app's VM, point its kiosk at the page and open the inspector tunnel, watching for QEMU to end; stop the VM on `cleanup`, and when any step raises."""
        session = self._make_session(self._ensure_layer(app), rec.session_dir, app.display)
        cleanup.callback(session.stop)
        session.start(on_qemu=lambda pid: rec.update(qemu=self._entry(pid)))
        session.place_window()
        session.configure_kiosk(app.page_url(backend, VmServed()))
        local = self._free_port()
        session.open_tunnel(local)
        rec.update(inspector=local)
        return Shown(f"http://localhost:{dev.port}/", f"127.0.0.1:{local}", lambda: f"the VM's QEMU ended; see {session.keep_serial_log()}" if session.vm.process.poll() is not None else None)


class Board:
    """Show the page in the kiosk of a real board reached over SSH."""

    def __init__(self, make_board=board.Session, free_port=process.free_port, entry=process.entry):
        self._make_board, self._free_port, self._entry = make_board, free_port, entry

    def show(self, app: KioskApp, settings: Settings, backend: Backend, dev: DevServer, cleanup: ExitStack, rec: Record) -> Shown:
        """Point the board's kiosk at the page through a tunnel to the Mac; restore the board and close the tunnel on `cleanup`, keeping the board in the record when the restore fails."""
        target = self._make_board(settings.target, app.name, rec.directory / board.LOG_NAME)
        target.check_kiosk()
        conf = target.session_conf(app.page_url(backend, BoardServed()))
        ports = mac_ports(dev, backend)
        local = self._free_port()
        tunnel = target.open_tunnel(board.forwards(ports, local), local, [board.remote_port(port) for port in ports])
        cleanup.callback(target.close_tunnel, tunnel)
        rec.update(tunnel=self._entry(tunnel.pid), board=settings.target, inspector=local)

        def restore() -> None:
            if target.restore():
                rec.update(board=None)

        cleanup.callback(restore)
        target.install(conf, tunnel)
        return Shown(f"http://localhost:{dev.port}/", f"127.0.0.1:{local}", lambda: target.tunnel_problem(tunnel))


def flavor_for(flavor: str) -> Browser | Vm | Board:
    """Return the flavor object for `flavor`; raise KeyError for an unknown flavor."""
    return {"browser": Browser, "vm": Vm, "board": Board}[flavor]()
