import pytest

from pihero_testkit import plugin, ssh

pytestmark = pytest.mark.tier0
pytest_plugins = ["pytester"]

OPTIONS = ("-p", "pihero_testkit.plugin", "-p", "no:pytest11.testinfra", "--import-mode=importlib", "-m", "installed", "-rs")
INSTALLED_TEST = "import pytest\n\npytestmark = pytest.mark.installed\n\n\ndef test_passes():\n    assert True\n"


class TestPackageOf:
    def test_is_the_package_directory_above_a_test(self, tmp_path):
        (tmp_path / "packages" / "pihero-kiosk" / "tests").mkdir(parents=True)
        (tmp_path / "packages" / "pihero-kiosk" / "nfpm.yaml").write_text("name: pihero-kiosk\n")

        name = plugin.package_of(tmp_path / "packages" / "pihero-kiosk" / "tests" / "test_installed.py")

        assert name == "pihero-kiosk"

    def test_is_none_outside_a_package(self, tmp_path):
        (tmp_path / "testkit" / "tests").mkdir(parents=True)

        name = plugin.package_of(tmp_path / "testkit" / "tests" / "test_boot.py")

        assert name is None


class TestSshTarget:
    def test_skips_the_installed_tests_of_packages_the_device_lacks(self, pytester, monkeypatch):
        monkeypatch.setattr(ssh, "installed_packages", lambda uri: {"probe-core"})
        tree(pytester)

        result = pytester.runpytest_inprocess(*OPTIONS, "--target=ssh", "--target-uri=pi@host")

        result.assert_outcomes(passed=2, skipped=1)
        result.stdout.fnmatch_lines(["*probe-panel is not installed on pi@host*"])

    def test_asks_nothing_on_podman(self, pytester, monkeypatch):
        monkeypatch.setattr(ssh, "installed_packages", lambda uri: pytest.fail("asked the device"))
        tree(pytester)

        result = pytester.runpytest_inprocess(*OPTIONS, "--target=podman")

        result.assert_outcomes(passed=3)


def tree(pytester) -> None:
    pytester.makefile(".yaml", **{"probes/probe-core/nfpm": "name: probe-core", "probes/probe-panel/nfpm": "name: probe-panel"})
    pytester.makepyfile(
        **{
            "probes/probe-core/tests/test_probe_core": INSTALLED_TEST,
            "probes/probe-panel/tests/test_probe_panel": INSTALLED_TEST,
            "harness/tests/test_harness": INSTALLED_TEST,
        }
    )
