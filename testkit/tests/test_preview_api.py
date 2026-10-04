import pytest

from pihero_testkit.preview import api

pytestmark = pytest.mark.tier0


class TestSettingsFromEnviron:
    def test_takes_the_flavor_and_defaults_to_safari(self):
        settings = api.Settings.from_environ("vm", {})

        assert (settings.flavor, settings.target, settings.inspect) == ("vm", None, "Safari")

    def test_keeps_the_environment_for_the_apps_own_variables(self):
        settings = api.Settings.from_environ("browser", {"BROKER": "fake"})

        assert settings.environ["BROKER"] == "fake"

    def test_on_the_board_takes_target(self):
        settings = api.Settings.from_environ("board", {"TARGET": "pi@host"})

        assert settings.target == "pi@host"

    def test_on_the_board_without_target_raises(self):
        with pytest.raises(ValueError, match="preview-board needs TARGET=user@host"):
            api.Settings.from_environ("board", {})

    @pytest.mark.parametrize("flavor", ["browser", "vm"])
    def test_refuses_target_elsewhere(self, flavor):
        with pytest.raises(ValueError, match="TARGET is only for preview-board"):
            api.Settings.from_environ(flavor, {"TARGET": "pi@host"})

    def test_refuses_an_unknown_flavor(self):
        with pytest.raises(ValueError, match="browser, vm or board"):
            api.Settings.from_environ("tv", {})

    @pytest.mark.parametrize("value", ["", "0"])
    def test_opens_nothing_for_inspect_zero_or_empty(self, value):
        settings = api.Settings.from_environ("vm", {"INSPECT": value})

        assert settings.inspect is None

    def test_takes_any_application_name(self):
        settings = api.Settings.from_environ("vm", {"INSPECT": "Google Chrome"})

        assert settings.inspect == "Google Chrome"


class TestDevServer:
    def test_has_no_environment_additions_by_default(self):
        server = api.DevServer(["./gradlew", "run"], 8081)

        assert server.env == {}


class TestFlavors:
    def test_are_browser_vm_and_board(self):
        assert api.FLAVORS == ("browser", "vm", "board")
