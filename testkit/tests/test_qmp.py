import json
import socket
import threading

import pytest

from pihero_testkit import qmp

pytestmark = pytest.mark.tier0


class TestExecute:
    def test_negotiates_capabilities_and_returns_the_commands_result(self):
        server = FakeQmp([{"return": {}}, {"return": {"qemu": {"major": 11}}}])
        with server:
            result = qmp.execute(server.port, "query-version")

        assert result == {"qemu": {"major": 11}}
        assert [m["execute"] for m in server.received] == ["qmp_capabilities", "query-version"]

    def test_passes_the_arguments(self):
        server = FakeQmp([{"return": {}}, {"return": {}}])
        with server:
            qmp.execute(server.port, "screendump", {"filename": "/tmp/x.png", "format": "png"})

        assert server.received[1]["arguments"] == {"filename": "/tmp/x.png", "format": "png"}

    def test_skips_events_while_waiting_for_the_reply(self):
        server = FakeQmp([{"return": {}}, {"event": "RESUME", "timestamp": {}}, {"return": {"ok": 1}}])
        with server:
            result = qmp.execute(server.port, "cont")

        assert result == {"ok": 1}

    def test_raises_with_qmps_error(self):
        server = FakeQmp([{"return": {}}, {"error": {"class": "GenericError", "desc": "no console"}}])
        with server, pytest.raises(RuntimeError, match="screendump: .*no console"):
            qmp.execute(server.port, "screendump", {"filename": "/tmp/x.png"})


class FakeQmp:
    def __init__(self, replies: list[dict]):
        self.replies = replies
        self.received: list[dict] = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.thread.join(timeout=5)
        self.sock.close()

    def serve(self):
        conn, _ = self.sock.accept()
        with conn, conn.makefile("rwb", buffering=0) as stream:
            stream.write(b'{"QMP": {"version": {}, "capabilities": []}}\r\n')
            for reply in self.replies:
                if "event" not in reply:
                    self.received.append(json.loads(stream.readline()))
                stream.write((json.dumps(reply) + "\r\n").encode())
