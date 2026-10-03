import json
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from types import SimpleNamespace

import pytest

from pihero_testkit.preview import flavors, session
from pihero_testkit.preview.api import DevServer, Settings

pytestmark = pytest.mark.tier0


class TestRun:
    def test_starts_the_backend_and_the_dev_server_shows_the_flavor_and_cleans_up_in_reverse(self, tmp_path):
        log = []
        app = App(tmp_path, log, managed=True)
        harness = Harness(log)

        status = session.run(app, Settings("vm", None, "Safari", {}), **harness.injected)

        assert status == 0
        assert log == [
            "backend", "dev_server", "backend.start", "ensure 8081", "show vm",
            "wait_for_inspector 127.0.0.1:54321", "open Safari http://127.0.0.1:54321/Main.html", "until_interrupted",
            "stop dev server", "backend.stop",
        ]
        assert not (tmp_path / "dist" / "preview" / "session.json").exists()

    def test_leaves_an_unmanaged_backend_alone(self, tmp_path):
        log = []

        session.run(App(tmp_path, log, managed=False), Settings("browser", None, None, {}), **Harness(log).injected)

        assert "backend.start" not in log and "backend.stop" not in log

    def test_records_the_backend_and_the_dev_server_while_running(self, tmp_path):
        log = []
        app = App(tmp_path, log, managed=True)
        seen = {}
        harness = Harness(log, on_wait=lambda: seen.update(json.loads((tmp_path / "dist" / "preview" / "session.json").read_text())))

        session.run(app, Settings("vm", None, None, {}), **harness.injected)

        assert seen["backend"] is True
        assert seen["dev_server"] == [77, "T"]
        assert "owner" in seen

    def test_records_the_dev_server_while_waiting_for_it_to_serve(self, tmp_path):
        log = []
        seen = {}
        harness = Harness(log, on_serving_wait=lambda: seen.update(json.loads((tmp_path / "dist" / "preview" / "session.json").read_text())))

        session.run(App(tmp_path, log), Settings("vm", None, None, {}), **harness.injected)

        assert seen["dev_server"] == [77, "T"]

    def test_opens_the_page_itself_in_the_browser_flavor(self, tmp_path):
        log = []

        session.run(App(tmp_path, log), Settings("browser", None, "Safari", {}), **Harness(log, flavor="browser").injected)

        assert "open Safari http://localhost:8081/?x=1" in log

    def test_goes_on_when_the_application_to_open_is_missing(self, tmp_path):
        log = []
        harness = Harness(log)
        harness.open_status = 1

        status = session.run(App(tmp_path, log), Settings("vm", None, "Nope", {}), **harness.injected)

        assert status == 0 and "until_interrupted" in log

    def test_prints_the_ready_message(self, tmp_path, capsys):
        log = []

        session.run(App(tmp_path, log, managed=True), Settings("vm", None, None, {}), **Harness(log).injected)

        err = capsys.readouterr().err
        assert "preview ready (vm)\n  page       http://localhost:8081/\n  backend    fake on localhost:8080\n  inspector  http://127.0.0.1:54321/\nCtrl-C ends it." in err

    def test_fails_before_claiming_when_the_apps_variables_are_bad(self, tmp_path):
        log = []
        app = App(tmp_path, log)
        app.bad_backend = True

        with pytest.raises(ValueError, match="BROKER must be"):
            session.run(app, Settings("vm", None, None, {}), **Harness(log).injected)

        assert not (tmp_path / "dist" / "preview").exists()

    def test_stops_the_dev_server_and_backend_when_the_flavor_fails(self, tmp_path):
        log = []
        harness = Harness(log)
        harness.show_error = RuntimeError("no kiosk")

        with pytest.raises(RuntimeError, match="no kiosk"):
            session.run(App(tmp_path, log, managed=True), Settings("vm", None, None, {}), **harness.injected)

        assert log[-2:] == ["stop dev server", "backend.stop"]

    def test_stops_the_backend_and_forgets_the_record_when_it_fails_to_start(self, tmp_path):
        log = []
        app = App(tmp_path, log, managed=True)
        app.start_error = RuntimeError("no fake")

        with pytest.raises(RuntimeError, match="no fake"):
            session.run(app, Settings("vm", None, None, {}), **Harness(log).injected)

        assert "backend.stop" in log
        assert not (tmp_path / "dist" / "preview" / "session.json").exists()

    def test_restores_the_board_and_stops_the_backend_a_killed_preview_left_behind_before_starting(self, tmp_path):
        log = []
        state = tmp_path / "dist" / "preview"
        state.mkdir(parents=True)
        (state / "session.json").write_text(json.dumps({"owner": [999999, "gone"], "backend": True, "device": "pi@old"}))
        made = []

        def make_board(*args):
            made.append(args)
            return SimpleNamespace(restore=lambda: log.append("restore") or True)

        session.run(App(tmp_path, log, managed=True), Settings("vm", None, None, {}), make_board=make_board, **Harness(log).injected)

        assert made == [("pi@old", "probe", state / "tunnel.log")]
        assert log.index("restore") < log.index("backend.start")
        assert log.index("backend.stop") < log.index("backend.start")

    def test_the_wait_reports_the_flavors_problem(self, tmp_path):
        log = []
        harness = Harness(log)
        harness.watch = lambda: "problem"

        session.run(App(tmp_path, log), Settings("vm", None, None, {}), **harness.injected)

        assert harness.waited_with() == "problem"

    def test_the_wait_reports_that_the_dev_server_exited(self, tmp_path):
        log = []
        harness = Harness(log, flavor="browser")
        harness.server_status = 1

        session.run(App(tmp_path, log), Settings("browser", None, None, {}), **harness.injected)

        assert harness.waited_with() == f"the dev server exited with status 1; see {tmp_path / 'dist' / 'preview' / 'dev-server.log'}"

    def test_the_wait_defers_to_the_flavors_problem_over_the_dev_servers_exit(self, tmp_path):
        log = []
        harness = Harness(log)
        harness.watch = lambda: "problem"
        harness.server_status = 1

        session.run(App(tmp_path, log), Settings("vm", None, None, {}), **harness.injected)

        assert harness.waited_with() == "problem"

    def test_the_wait_is_quiet_while_the_flavor_and_the_dev_server_run(self, tmp_path):
        log = []
        harness = Harness(log)

        session.run(App(tmp_path, log), Settings("vm", None, None, {}), **harness.injected)

        assert harness.waited_with() is None


class TestMain:
    def test_returns_2_with_the_message_for_a_variable_that_does_not_fit(self, tmp_path, capsys):
        status = session.main(App(tmp_path, []), ["--on", "device"], {})

        assert status == 2
        assert "preview-device needs TARGET=user@host" in capsys.readouterr().err

    def test_refuses_an_unknown_flavor(self, tmp_path):
        with pytest.raises(SystemExit) as exit_:
            session.main(App(tmp_path, []), ["--on", "tv"], {})

        assert exit_.value.code == 2

    def test_returns_2_with_the_apps_own_message(self, tmp_path, capsys):
        app = App(tmp_path, [])
        app.bad_backend = True

        status = session.main(app, ["--on", "vm"], {})

        assert status == 2
        assert "BROKER must be" in capsys.readouterr().err

    @pytest.mark.parametrize("error", [RuntimeError("no kiosk"), TimeoutError("board did not answer")])
    def test_returns_2_with_the_message_of_a_failed_run(self, tmp_path, capsys, monkeypatch, error):
        monkeypatch.setattr(session, "run", raising(error))

        status = session.main(App(tmp_path, []), ["--on", "vm"], {})

        assert status == 2
        assert str(error) in capsys.readouterr().err

    def test_returns_130_on_ctrl_c(self, tmp_path, monkeypatch):
        monkeypatch.setattr(session, "run", raising(KeyboardInterrupt()))

        status = session.main(App(tmp_path, []), ["--on", "vm"], {})

        assert status == 130

    def test_is_exported_by_the_package(self):
        from pihero_testkit import preview

        assert preview.main is session.main


class TestStateDir:
    def test_is_dist_preview_under_the_apps_root(self):
        assert session.state_dir(SimpleNamespace(root=Path("/repo"))) == Path("/repo/dist/preview")


def raising(error: BaseException):
    def run(app, settings):
        raise error

    return run


class App:
    name = "probe"
    display = (800, 480)

    def __init__(self, root: Path, log: list, managed: bool = False):
        self.root, self.log, self.managed, self.bad_backend, self.start_error = root, log, managed, False, None

    def user_data(self):
        return "#cloud-config\npackages:\n  - pihero-kiosk\n"

    def dev_server(self, settings):
        self.log.append("dev_server")
        return DevServer(["serve"], 8081)

    def backend(self, settings):
        self.log.append("backend")
        if self.bad_backend:
            raise ValueError("BROKER must be fake, device or HOST:PORT")
        log = self.log

        def start():
            log.append("backend.start")
            if self.start_error:
                raise self.start_error

        return SimpleNamespace(managed=self.managed, mac_port=8080, start=start, stop=lambda: log.append("backend.stop"), describe=lambda: "fake on localhost:8080")

    def page_url(self, backend, served):
        return f"http://{served.address(8081)}/?x=1"


class Harness:
    def __init__(self, log: list, flavor: str = "vm", on_wait=lambda: None, on_serving_wait=lambda: None):
        self.log, self.flavor_name, self.on_wait, self.on_serving_wait = log, flavor, on_wait, on_serving_wait
        self.open_status, self.show_error, self.watch, self.waited_with, self.server_status = 0, None, None, None, None

    @property
    def injected(self) -> dict:
        return dict(
            ensure_dev_server=self.ensure, stop_dev_server=lambda proc: self.log.append("stop dev server"), flavor_for=lambda name: self,
            wait_for_inspector=self.wait_for_inspector, open_=self.open_, until_interrupted=self.until_interrupted, arm_sigterm=lambda: None,
            entry=lambda pid: [pid, "T"],
        )

    def ensure(self, dev, root, log, *, on_start):
        self.log.append(f"ensure {dev.port}")
        proc = SimpleNamespace(pid=77, poll=lambda: self.server_status)
        on_start(proc)
        self.on_serving_wait()
        return proc

    def show(self, app, settings, backend, dev, cleanup, rec):
        self.log.append(f"show {settings.flavor}")
        if self.show_error:
            raise self.show_error
        if self.flavor_name == "browser":
            return flavors.Shown(app.page_url(backend, flavors.BrowserServed()))
        return flavors.Shown("http://localhost:8081/", "127.0.0.1:54321", self.watch)

    def wait_for_inspector(self, address):
        self.log.append(f"wait_for_inspector {address}")
        return f"http://{address}/Main.html"

    def open_(self, argv, check):
        self.log.append(f"open {argv[2]} {argv[3]}")
        if check and self.open_status:
            raise CalledProcessError(self.open_status, argv)
        return CompletedProcess(argv, self.open_status, "", "")

    def until_interrupted(self, watch):
        self.waited_with = watch
        self.on_wait()
        self.log.append("until_interrupted")
