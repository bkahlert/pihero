import shutil

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
