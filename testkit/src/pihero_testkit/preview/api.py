"""The preview's API: what an app that shows a page in pihero-kiosk implements, and what one session hands it."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

FLAVORS = ("browser", "vm", "board")


def inspect_app(value: str) -> str | None:
    """Return the application INSPECT names, or None for "0" or an empty value."""
    return None if value in ("", "0") else value


@dataclass(frozen=True)
class Settings:
    """What every flavor takes: the flavor, TARGET for the board, INSPECT, and the environment the app's own variables come from."""

    flavor: str
    target: str | None
    inspect: str | None
    environ: Mapping[str, str]

    @staticmethod
    def from_environ(flavor: str, environ: Mapping[str, str]) -> "Settings":
        """Return the settings for `flavor` from `environ`; raise ValueError for an unknown flavor or a TARGET that does not fit it."""
        if flavor not in FLAVORS:
            raise ValueError(f"flavor must be browser, vm or board, not {flavor!r}")
        target = environ.get("TARGET") or None
        if flavor == "board" and not target:
            raise ValueError("preview-board needs TARGET=user@host")
        if flavor != "board" and target:
            raise ValueError("TARGET is only for preview-board")
        return Settings(flavor, target, inspect_app(environ.get("INSPECT", "Safari")), environ)


@dataclass(frozen=True)
class DevServer:
    """The app's dev server: `argv` run in the app's root with `env` added to the environment, ready once `port` answers on 127.0.0.1."""

    argv: list[str]
    port: int
    env: dict[str, str] = field(default_factory=dict)


class Backend(Protocol):
    """The app's backend as one session sees it: a fake the session starts, the board's own, or an address given."""

    managed: bool
    """Whether start() starts something the session must stop."""
    mac_port: int | None
    """The Mac port the kiosk must reach, None when the backend is not on the Mac."""

    def start(self) -> None:
        """Start the fake; raise RuntimeError with the reason when it cannot."""

    def stop(self) -> None:
        """End the app's fake wherever a session left it; idempotent, and works from a fresh process."""

    def describe(self) -> str:
        """Return one line for the ready message, such as "fake on localhost:8080"."""


class Served(Protocol):
    """How the kiosk of one flavor reaches the Mac."""

    flavor: str

    def address(self, mac_port: int) -> str:
        """Return "host:port" as the kiosk reaches the Mac's `mac_port`."""


class KioskApp(Protocol):
    """What the preview needs from an app that shows a page in pihero-kiosk."""

    name: str
    """Scopes the record, the board's /run directory and its drop-in; "netmon"."""
    root: Path
    """The repository: the record lives under root/dist/preview and the dev server runs there."""
    display: tuple[int, int]
    """The VM's display and the window's size in points; (800, 480)."""

    def user_data(self) -> str:
        """Return the VM's device file: the sample minus what the Mac serves, with pihero-kiosk."""

    def dev_server(self, settings: Settings) -> DevServer:
        """Return the dev server for `settings`."""

    def backend(self, settings: Settings) -> Backend:
        """Return the backend `settings` ask for; raise ValueError naming the grammar for a bad variable."""

    def page_url(self, backend: Backend, served: Served) -> str:
        """Return the URL the kiosk or browser loads, every Mac port through `served.address`."""
