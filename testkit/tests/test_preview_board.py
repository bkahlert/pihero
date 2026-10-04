import re
import subprocess
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from pihero_testkit import ssh
from pihero_testkit.preview import board, kiosk

pytestmark = pytest.mark.tier0
TARGET = "pi@netmon.local"
SAMPLE_CONF = 'URL=http://localhost/?broker.host=localhost&broker.port=8080\nCOG_ARGS="--doc-viewer --web-mem-limit=200"\nJSC_useJIT=false\n'


class TestRemotePort:
    @pytest.mark.parametrize("mac_port, expected", [(8081, 18081), (8080, 18080), (1880, 11880), (55535, 65535)])
    def test_is_ten_thousand_above_the_mac_port(self, mac_port, expected):
        assert board.remote_port(mac_port) == expected

    def test_refuses_a_port_that_would_leave_the_range(self):
        with pytest.raises(ValueError, match="55536 .* 55535"):
            board.remote_port(55536)


class TestForwards:
    def test_reverses_every_mac_port_and_forwards_the_inspector(self):
        args = board.forwards([8081, 8080], 54321)

        assert args == ["-R", "127.0.0.1:18081:127.0.0.1:8081", "-R", "127.0.0.1:18080:127.0.0.1:8080", "-L", "127.0.0.1:54321:127.0.0.1:2999"]


class TestTunnelCommand:
    def test_is_a_batch_ipv4_ssh_that_exits_when_a_forward_fails(self):
        argv = board.tunnel_command(TARGET, ["-L", "a"])

        assert argv == ["ssh", "-N", "-4", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=10", *ssh.KEEPALIVE, "-L", "a", TARGET]

    def test_passes_the_targets_port(self):
        argv = board.tunnel_command("pi@netmon.local:2222", [])

        assert argv[-3:] == ["-p", "2222", TARGET]


class TestSessionPaths:
    def test_are_scoped_by_the_apps_name(self, tmp_path):
        b = board.Session(TARGET, "netmon", tmp_path / "tunnel.log")

        assert (b.run_dir, b.conf, b.dropin) == ("/run/netmon-preview", "/run/netmon-preview/kiosk.conf", "/run/systemd/system/pihero-kiosk.service.d/netmon-preview.conf")


class TestSessionName:
    @pytest.mark.parametrize("name", ["", "my app", "a;b", "a/b", "ä"])
    def test_refuses_a_name_that_is_not_letters_digits_dash_underscore_or_dot(self, name, tmp_path):
        with pytest.raises(ValueError, match=re.escape(f"the app's name must be letters, digits, '-', '_' or '.', not {name!r}")):
            board.Session(TARGET, name, tmp_path / "t")

    @pytest.mark.parametrize("name", ["busy-screen", "Net_mon.2"])
    def test_accepts_letters_digits_dash_underscore_and_dot(self, name, tmp_path):
        assert board.Session(TARGET, name, tmp_path / "t").run_dir == f"/run/{name}-preview"


class TestCommands:
    def test_install_writes_the_conf_and_the_drop_in_then_restarts(self, tmp_path):
        command = board.Session(TARGET, "netmon", tmp_path / "t").install_command()

        assert command == (
            "sudo install -d /run/netmon-preview /run/systemd/system/pihero-kiosk.service.d && sudo tee /run/netmon-preview/kiosk.conf >/dev/null && "
            "printf '[Service]\\nEnvironmentFile=/run/netmon-preview/kiosk.conf\\n' | sudo tee /run/systemd/system/pihero-kiosk.service.d/netmon-preview.conf >/dev/null && "
            "sudo systemctl daemon-reload && sudo systemctl restart pihero-kiosk"
        )

    def test_restore_removes_both_and_restarts(self, tmp_path):
        command = board.Session(TARGET, "netmon", tmp_path / "t").restore_command()

        assert command == (
            "sudo rm -rf /run/netmon-preview /run/systemd/system/pihero-kiosk.service.d/netmon-preview.conf; "
            "sudo rmdir --ignore-fail-on-non-empty /run/systemd/system/pihero-kiosk.service.d 2>/dev/null; "
            "sudo systemctl daemon-reload && sudo systemctl restart pihero-kiosk"
        )

    def test_end_forwards_kills_the_sshd_listening_on_the_sessions_remote_ports(self, tmp_path):
        command = board.Session(TARGET, "netmon", tmp_path / "t").end_forwards_command([18081, 18080])

        assert command == "sudo ss -ltnpH | grep -E '127\\.0\\.0\\.1:(18081|18080) ' | grep sshd | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u | xargs -r sudo kill"


class TestSsh:
    def test_runs_the_remote_through_the_testkits_ssh_command(self, tmp_path):
        calls = []
        b = board.Session("pi@netmon.local:2222", "netmon", tmp_path / "t", run=lambda argv, **kw: calls.append(argv) or CompletedProcess(argv, 0, "", ""))

        b.ssh("true")

        assert calls == [ssh.command("pi@netmon.local:2222", "true")]
        assert "-p" in calls[0] and "2222" in calls[0]

    def test_turns_a_hanging_connection_into_a_timeout_error(self, tmp_path):
        def run(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

        with pytest.raises(TimeoutError, match="pi@netmon.local did not answer within 60 s"):
            board.Session(TARGET, "netmon", tmp_path / "t", run=run).ssh("true")


class TestCheckKiosk:
    def test_passes_when_the_package_is_installed(self, tmp_path):
        board.Session(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 0, "pihero-kiosk 2.7.0\n", "")).check_kiosk()

    def test_names_the_ssh_error_when_the_board_is_unreachable(self, tmp_path):
        with pytest.raises(RuntimeError, match="cannot reach pi@netmon.local over ssh: Connection refused"):
            board.Session(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 255, "", "Connection refused\n")).check_kiosk()

    def test_asks_for_a_pi_hero_device_file_without_the_kiosk(self, tmp_path):
        with pytest.raises(RuntimeError, match="has no pihero-kiosk; flash a Pi Hero device file first"):
            board.Session(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 1, "", "no packages found\n")).check_kiosk()


class TestSessionConf:
    def test_rewrites_the_boards_own_conf_for_the_session(self, tmp_path):
        b = board.Session(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 0, SAMPLE_CONF, ""))

        conf = b.session_conf("http://127.0.0.1:18081/")

        assert conf == kiosk.session_conf(SAMPLE_CONF, "http://127.0.0.1:18081/")

    def test_fails_when_the_conf_cannot_be_read(self, tmp_path):
        with pytest.raises(RuntimeError, match="cannot read /etc/pihero/kiosk.conf on pi@netmon.local: denied"):
            board.Session(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 1, "", "denied\n")).session_conf("http://x/")


class TestInstall:
    def test_sends_the_conf_and_waits_for_the_page_to_load(self, tmp_path):
        calls = []
        answers = {kiosk.since_command(): "2026-10-03 10:00:00\n"}
        loaded = iter(["0\n", "1\n"])

        def run(argv, **kwargs):
            calls.append((argv[-1], kwargs.get("input")))
            remote = argv[-1]
            out = answers.get(remote, next(loaded) if remote.startswith("sudo journalctl") else "")
            return CompletedProcess(argv, 0, out, "")

        b = board.Session(TARGET, "netmon", tmp_path / "t", run=run, sleep=lambda s: None, clock=counter())

        b.install("CONF", SimpleNamespace(poll=lambda: None))

        assert calls[1] == (b.install_command(), "CONF")
        assert [c[0] for c in calls[2:]] == [kiosk.loaded_command("2026-10-03 10:00:00")] * 2

    def test_fails_early_with_the_tunnels_message_when_it_ends(self, tmp_path):
        log = tmp_path / "tunnel.log"
        log.write_text("channel 3: open failed: connect failed\nremote port forwarding failed for listen port 18081\n")
        b = board.Session(TARGET, "netmon", log, run=lambda argv, **kw: CompletedProcess(argv, 0, "x\n", ""), sleep=lambda s: None, clock=counter())

        with pytest.raises(RuntimeError, match="the ssh tunnel to pi@netmon.local ended: remote port forwarding failed for listen port 18081"):
            b.install("CONF", SimpleNamespace(poll=lambda: 255))

    def test_times_out_asking_about_the_dev_server_and_the_tunnel(self, tmp_path):
        b = board.Session(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 0, "0\n", ""), sleep=lambda s: None, clock=counter(step=50))

        with pytest.raises(TimeoutError, match="did not load its page within 90 s; is the dev server up and the tunnel open"):
            b.install("CONF", SimpleNamespace(poll=lambda: None))


class TestRestore:
    def test_returns_true_when_the_board_answered(self, tmp_path):
        assert board.Session(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 0, "", "")).restore() is True

    def test_warns_and_returns_false_when_it_did_not(self, tmp_path):
        warned = []
        b = board.Session(TARGET, "netmon", tmp_path / "t", run=lambda argv, **kw: CompletedProcess(argv, 255, "", "no route\n"), report=warned.append)

        assert b.restore() is False
        assert warned == ["could not restore the kiosk on pi@netmon.local: no route; a reboot of the board removes the session's files"]

    def test_waits_as_long_as_the_kiosk_unit_may_take_to_stop(self, tmp_path):
        """A loaded Zero took 43 s to daemon-reload and restart, so 30 s warned of a restore that had worked."""
        timeouts = []

        def run(argv, **kwargs):
            timeouts.append(kwargs["timeout"])
            return CompletedProcess(argv, 0, "", "")

        board.Session(TARGET, "netmon", tmp_path / "t", run=run).restore()

        assert len(timeouts) == 1 and timeouts[0] >= 90

    def test_warns_and_returns_false_when_it_hangs(self, tmp_path):
        warned = []

        def run(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

        b = board.Session(TARGET, "netmon", tmp_path / "t", run=run, report=warned.append)

        assert b.restore() is False
        assert warned == ["could not restore the kiosk on pi@netmon.local: pi@netmon.local did not answer within 120 s; a reboot of the board removes the session's files"]


class TestOpenTunnel:
    def test_ends_stale_forwards_then_opens_the_tunnel_and_waits_for_the_inspector_port(self, tmp_path):
        remotes, popened = [], []
        tunnel = SimpleNamespace(poll=lambda: None, pid=9)
        answers = iter([False, True])
        b = board.Session(TARGET, "netmon", tmp_path / "dist" / "tunnel.log", run=lambda argv, **kw: remotes.append(argv[-1]) or CompletedProcess(argv, 0, "", ""), popen=lambda argv, **kw: popened.append((argv, kw)) or tunnel, answers=lambda h, p: next(answers), sleep=lambda s: None, clock=counter())

        opened = b.open_tunnel(["-L", "a"], 54321, [18081])

        assert opened is tunnel
        assert remotes == [b.end_forwards_command([18081])]
        assert popened[0][0] == board.tunnel_command(TARGET, ["-L", "a"])
        assert (tmp_path / "dist").is_dir()

    def test_raises_with_the_exit_status_when_the_tunnel_ends_early(self, tmp_path):
        tunnel = SimpleNamespace(poll=lambda: 255, pid=9)
        b = board.Session(TARGET, "netmon", tmp_path / "tunnel.log", run=lambda argv, **kw: CompletedProcess(argv, 0, "", ""), popen=lambda argv, **kw: tunnel, answers=lambda h, p: False, sleep=lambda s: None, clock=counter())

        with pytest.raises(RuntimeError, match="ended with status 255 and no message"):
            b.open_tunnel([], 54321, [])

    def test_closes_the_tunnel_and_times_out_naming_the_log(self, tmp_path):
        closed = []
        tunnel = SimpleNamespace(poll=lambda: None, pid=9, terminate=lambda: closed.append(True), wait=lambda t: None)
        b = board.Session(TARGET, "netmon", tmp_path / "tunnel.log", run=lambda argv, **kw: CompletedProcess(argv, 0, "", ""), popen=lambda argv, **kw: tunnel, answers=lambda h, p: False, sleep=lambda s: None, clock=counter(step=10))

        with pytest.raises(TimeoutError, match=f"did not come up within 15 s; see {tmp_path / 'tunnel.log'}"):
            b.open_tunnel([], 54321, [])

        assert closed == [True]


class TestCloseTunnel:
    def test_terminates_a_running_tunnel_and_waits_five_seconds(self, tmp_path):
        events = []
        tunnel = SimpleNamespace(poll=lambda: None, terminate=lambda: events.append("terminate"), wait=lambda t: events.append(("wait", t)), kill=lambda: events.append("kill"))

        board.Session(TARGET, "netmon", tmp_path / "t").close_tunnel(tunnel)

        assert events == ["terminate", ("wait", 5)]

    def test_kills_a_tunnel_that_does_not_end_in_time(self, tmp_path):
        events = []

        def wait(timeout):
            raise subprocess.TimeoutExpired("ssh", timeout)

        tunnel = SimpleNamespace(poll=lambda: None, terminate=lambda: events.append("terminate"), wait=wait, kill=lambda: events.append("kill"))

        board.Session(TARGET, "netmon", tmp_path / "t").close_tunnel(tunnel)

        assert events == ["terminate", "kill"]

    def test_leaves_an_ended_tunnel_alone(self, tmp_path):
        events = []
        tunnel = SimpleNamespace(poll=lambda: 255, terminate=lambda: events.append("terminate"), wait=lambda t: events.append("wait"), kill=lambda: events.append("kill"))

        board.Session(TARGET, "netmon", tmp_path / "t").close_tunnel(tunnel)

        assert events == []


class TestTunnelProblem:
    def test_is_none_while_the_tunnel_runs(self, tmp_path):
        assert board.Session(TARGET, "netmon", tmp_path / "t").tunnel_problem(SimpleNamespace(poll=lambda: None)) is None

    def test_is_the_last_line_of_the_log_that_is_not_channel_noise(self, tmp_path):
        log = tmp_path / "tunnel.log"
        log.write_text("Connection to netmon.local closed by remote host.\nchannel 2: open failed: connect failed: Connection refused\n")

        problem = board.Session(TARGET, "netmon", log).tunnel_problem(SimpleNamespace(poll=lambda: 255))

        assert problem == "the ssh tunnel to pi@netmon.local ended: Connection to netmon.local closed by remote host."


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
