import shutil
from pathlib import Path

import pytest

from pihero_testkit import podman

pytestmark = pytest.mark.tier0


class TestImageTag:
    def test_ends_with_the_platform(self):
        tag = podman.image_tag("linux/arm/v7")

        assert tag.startswith("localhost/pihero-tier1:")
        assert tag.endswith("-arm-v7")

    def test_changes_with_the_build_context(self, tmp_path):
        context = tmp_path / "tier1"
        shutil.copytree(podman.TIER1_DIR, context)
        before = podman.image_tag("linux/arm64", context)
        (context / "Containerfile").write_text((context / "Containerfile").read_text() + "# probe\n")

        after = podman.image_tag("linux/arm64", context)

        assert after != before


class TestInstallable:
    def test_keeps_architecture_independent_debs_and_the_platforms_own(self):
        debs = [Path("dist/pihero_2.4.0_all.deb"), Path("dist/cog_0.18.4-1+pihero1_arm64.deb"), Path("dist/cog_0.18.4-1+pihero1_armhf.deb")]

        kept = podman.installable(debs, "linux/arm/v7")

        assert kept == [debs[0], debs[2]]

    def test_keeps_the_arm64_deb_on_arm64(self):
        debs = [Path("dist/cog_0.18.4-1+pihero1_arm64.deb")]

        kept = podman.installable(debs, "linux/arm64")

        assert kept == debs


class TestReinstall:
    def test_reinstalls_the_local_debs_even_where_an_archive_carries_the_same_version(self):
        debs = [Path("/x/a_1_all.deb"), Path("/x/b_1_arm64.deb"), Path("/x/c_1_armhf.deb")]
        container = podman.SystemdContainer("linux/arm64", Path("/x"), debs)
        calls = []
        container.exec = lambda *args, **kwargs: calls.append(args)

        container.reinstall()

        # apt reports a same-version deb from another source as a downgrade and refuses it under -y without the flag
        assert calls == [("env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-y", "-q", "install", "--reinstall", "--allow-downgrades", "/dist/a_1_all.deb", "/dist/b_1_arm64.deb")]
