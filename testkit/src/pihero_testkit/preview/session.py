"""One preview session from claim to cleanup: the backend, the dev server, the flavor, the inspector, and Ctrl-C."""

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path

from . import board, dev_server, flavors, kiosk, process
from .api import FLAVORS, Backend, KioskApp, Settings
from .record import AlreadyRunning, Record


def state_dir(app: KioskApp) -> Path:
    """Return where the app's preview keeps its record, logs and session: root/dist/preview."""
    return app.root / "dist" / "preview"


def ready_message(settings: Settings, shown: flavors.Shown, backend: Backend) -> str:
    """Return the lines printed once the preview is up."""
    inspector = f"\n  inspector  http://{shown.inspector}/" if shown.inspector else ""
    return f"preview ready ({settings.flavor})\n  page       {shown.page}\n  backend    {backend.describe()}{inspector}\nCtrl-C ends it."


def run(app: KioskApp, settings: Settings, *, ensure_dev_server=dev_server.ensure, stop_dev_server=dev_server.stop, flavor_for=flavors.flavor_for, wait_for_inspector=kiosk.wait_for_inspector, open_=subprocess.run, until_interrupted=process.until_interrupted, arm_sigterm=process.raise_on_sigterm, entry=process.entry, make_board=board.Session, out=None) -> int:
    """Run the preview until Ctrl-C and return 0, printing progress to `out` (stderr by default); raise RuntimeError when the flavor reports a problem or the dev server exits meanwhile; everything started is ended on the way out."""
    out = sys.stderr if out is None else out
    backend = app.backend(settings)
    dev = app.dev_server(settings)
    arm_sigterm()
    state = state_dir(app)
    rec = Record(state)
    rec.claim(backend.stop, lambda target: make_board(target, app.name, state / board.LOG_NAME).restore())
    with ExitStack() as cleanup:
        cleanup.callback(rec.forget)
        if backend.managed:
            rec.update(backend=True)
            cleanup.callback(backend.stop)
            backend.start()
        log = state / dev_server.LOG_NAME
        print(f"dev server: {shlex.join(dev.argv)} on port {dev.port}, log in {log}", file=out, flush=True)
        server = ensure_dev_server(dev, app.root, log, on_start=lambda proc: rec.update(dev_server=entry(proc.pid)))
        cleanup.callback(stop_dev_server, server)
        shown = flavor_for(settings.flavor).show(app, settings, backend, dev, cleanup, rec)
        opened = wait_for_inspector(shown.inspector) if shown.inspector else shown.page
        if settings.inspect:
            open_(kiosk.open_command(settings.inspect, opened), check=False)
        print(ready_message(settings, shown, backend), file=out, flush=True)

        def watch() -> str | None:
            problem = shown.watch() if shown.watch else None
            if problem:
                return problem
            status = server.poll()
            return f"the dev server exited with status {status}; see {log}" if status is not None else None

        until_interrupted(watch)
    return 0


def main(app: KioskApp, argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """Run the app's preview for `--on browser|vm|board`; return 0 when Ctrl-C ends a ready preview, 130 when Ctrl-C lands before it is ready, and 2 with the message on a bad variable or a failure."""
    parser = argparse.ArgumentParser(prog="preview.py", description=f"Show {app.name}'s page from the dev server in a browser, a VM's kiosk or a board's kiosk until Ctrl-C.")
    parser.add_argument("--on", required=True, choices=FLAVORS, help="where to show the page")
    flavor = parser.parse_args(argv).on
    try:
        return run(app, Settings.from_environ(flavor, os.environ if environ is None else environ))
    except (ValueError, AlreadyRunning, RuntimeError, TimeoutError) as error:
        print(error, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
