"""A kiosk app's page from the Mac's dev server in a browser, a VM's kiosk or a board's kiosk; see docs/app-conventions.md."""

from .api import Backend, DevServer, KioskApp, Served, Settings
from .session import main

__all__ = ["Backend", "DevServer", "KioskApp", "Served", "Settings", "main"]
