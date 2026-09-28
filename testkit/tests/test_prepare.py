import pytest

from pihero_testkit import prepare

pytestmark = pytest.mark.tier0


class TestImages:
    def test_lists_the_pinned_raspberry_pi_os_images_and_nothing_else(self):
        images = prepare.images()

        assert sorted(images) == ["raspios_lite_arm64", "raspios_lite_armhf"]
        assert all({"url", "sha256"} <= set(table) for table in images.values())

    def test_includes_the_tier_2_image(self):
        images = prepare.images()

        assert prepare.TIER2_IMAGE in images
