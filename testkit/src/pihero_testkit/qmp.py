"""A QEMU Machine Protocol client for the one thing the harness asks QEMU: a screendump."""

import json
import socket


def execute(port: int, command: str, arguments: dict | None = None, timeout: float = 30) -> dict:
    """Runs one QMP command on the monitor at 127.0.0.1:port and returns its result; raises RuntimeError with QMP's error."""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
        stream = sock.makefile("rwb", buffering=0)
        greeting = json.loads(stream.readline())
        if "QMP" not in greeting:
            raise RuntimeError(f"not a QMP monitor on port {port}: {greeting}")
        _exchange(stream, {"execute": "qmp_capabilities"})
        message = {"execute": command, **({"arguments": arguments} if arguments else {})}
        return _exchange(stream, message)


def _exchange(stream, message: dict) -> dict:
    stream.write((json.dumps(message) + "\n").encode())
    while True:
        reply = json.loads(stream.readline())
        if "event" in reply:
            continue
        if "error" in reply:
            raise RuntimeError(f"{message['execute']}: {reply['error'].get('desc', reply['error'])}")
        return reply["return"]
