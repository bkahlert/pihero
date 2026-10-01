import pytest

pytestmark = pytest.mark.installed
VERSION = "0.18.4-1+pihero1"


class TestPackage:
    def test_is_installed(self, host):
        assert host.package("cog").is_installed

    def test_is_pi_heros_build_on_arm64(self, host):
        if host.check_output("dpkg --print-architecture") != "arm64":
            pytest.skip("the 32-bit boards keep Debian's cog")

        version = host.package("cog").version

        assert version == VERSION
