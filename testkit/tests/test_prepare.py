import fcntl
from pathlib import Path

import pytest

from pihero_testkit import prepare, tools

pytestmark = pytest.mark.tier0


class TestImages:
    def test_lists_the_pinned_raspberry_pi_os_images_and_nothing_else(self):
        images = prepare.images()

        assert sorted(images) == ["raspios_lite_arm64", "raspios_lite_armhf"]
        assert all({"url", "sha256"} <= set(table) for table in images.values())

    def test_includes_the_tier_2_image(self):
        images = prepare.images()

        assert prepare.TIER2_IMAGE in images


class TestPrepare:
    def test_builds_under_the_lock_of_its_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prepare, "CACHE", tmp_path)
        monkeypatch.setattr(prepare, "download", lambda url, sha256: Path("/downloads/image.img.xz"))
        seen = []

        def fake_run(args, **kwargs):
            lock = next(tmp_path.joinpath("base").glob("*.lock"))
            with lock.open("w") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    seen.append("free")
                except BlockingIOError:
                    seen.append("held")

        monkeypatch.setattr(tools, "run", fake_run)

        base = prepare.prepare()

        assert seen == ["held"]
        assert (base.rootfs.parent / "done").exists()

    def test_skips_the_build_of_a_prepared_image(self, tmp_path, monkeypatch):
        monkeypatch.setattr(prepare, "CACHE", tmp_path)
        monkeypatch.setattr(tools, "run", lambda *args, **kwargs: pytest.fail("built again"))
        out = tmp_path / "base" / prepare.key()
        out.mkdir(parents=True)
        (out / "done").touch()

        base = prepare.prepare()

        assert base.rootfs == out / "rootfs.qcow2"
