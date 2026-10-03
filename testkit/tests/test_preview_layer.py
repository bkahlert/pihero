import fcntl
from pathlib import Path
from types import SimpleNamespace

import pytest

from pihero_testkit import prepare
from pihero_testkit.preview import layer

pytestmark = pytest.mark.tier0
BASE = prepare.BaseImage(Path("/cache/base/aa0c21373d89/rootfs.qcow2"), Path("/b/vmlinuz"), Path("/b/initrd.img"), Path("/b/boot"))
USER_DATA = "#cloud-config\npackages:\n  - pihero-kiosk\n"


class TestName:
    def test_is_twelve_hex_digits(self):
        name = layer.name("aa0c21373d89", USER_DATA)

        assert len(name) == 12 and int(name, 16) >= 0

    def test_is_stable(self):
        assert layer.name("a", "b") == layer.name("a", "b")

    @pytest.mark.parametrize("other", [("x", "b"), ("a", "x")])
    def test_changes_with_the_base_image_and_with_the_user_data(self, other):
        assert layer.name(*other) != layer.name("a", "b")

    def test_does_not_confuse_where_the_two_parts_meet(self):
        assert layer.name("ab", "c") != layer.name("a", "bc")


class TestLayerFor:
    def test_lives_under_the_cache_in_a_directory_of_its_name(self, tmp_path):
        found = layer.layer_for(BASE, USER_DATA, cache=tmp_path)

        name = layer.name("aa0c21373d89", USER_DATA)
        assert found == layer.Layer(tmp_path / name / "rootfs.qcow2", tmp_path / name / "bootfs.img")


class TestEnsure:
    def test_returns_an_existing_layer_without_building(self, tmp_path):
        existing = layer.layer_for(BASE, USER_DATA, tmp_path)
        existing.rootfs.parent.mkdir()
        existing.rootfs.touch()
        existing.bootfs.touch()

        found = layer.ensure(app(tmp_path), cache=tmp_path, build=lambda *a: pytest.fail("built"), prepare_base=lambda: BASE, report=lambda m: None)

        assert found == existing

    def test_builds_into_a_building_directory_then_renames_it_read_only(self, tmp_path):
        seen = {}

        def build(device, accel, display, into):
            seen.update(device=device, accel=accel, display=display, into=into)
            (into / "rootfs.qcow2").write_text("disk")
            (into / "bootfs.img").write_text("boot")

        found = layer.ensure(app(tmp_path), cache=tmp_path, build=build, prepare_base=lambda: BASE, report=lambda m: None)

        assert seen["into"] == tmp_path / f"{found.rootfs.parent.name}.building"
        assert (seen["device"], seen["accel"], seen["display"]) == (tmp_path / "dist" / "preview" / "preview-device", "hvf", (800, 480))
        assert (seen["device"] / "user-data").read_text() == USER_DATA
        assert found.rootfs.read_text() == "disk" and found.bootfs.read_text() == "boot"
        assert not seen["into"].exists()
        assert oct(found.rootfs.stat().st_mode)[-3:] == "444"

    def test_removes_a_building_directory_a_dead_build_left(self, tmp_path):
        name = layer.name("aa0c21373d89", USER_DATA)
        stale = tmp_path / f"{name}.building"
        stale.mkdir(parents=True)
        (stale / "rootfs.qcow2").write_text("half")

        def build(device, accel, display, into):
            assert not (into / "rootfs.qcow2").exists()
            (into / "rootfs.qcow2").touch()
            (into / "bootfs.img").touch()

        layer.ensure(app(tmp_path), cache=tmp_path, build=build, prepare_base=lambda: BASE, report=lambda m: None)

    def test_takes_the_lock_of_the_layer_while_building(self, tmp_path):
        name = layer.name("aa0c21373d89", USER_DATA)

        def build(device, accel, display, into):
            with (tmp_path / f"{name}.lock").open("w") as handle:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            (into / "rootfs.qcow2").touch()
            (into / "bootfs.img").touch()

        layer.ensure(app(tmp_path), cache=tmp_path, build=build, prepare_base=lambda: BASE, report=lambda m: None)

    def test_announces_the_build(self, tmp_path):
        reported = []

        def build(device, accel, display, into):
            (into / "rootfs.qcow2").touch()
            (into / "bootfs.img").touch()

        layer.ensure(app(tmp_path), cache=tmp_path, build=build, prepare_base=lambda: BASE, report=reported.append)

        assert reported == ["building the preview's base layer, once per base image and device file (about 2.5 minutes)"]

    def test_refuses_a_device_file_without_the_kiosk(self, tmp_path):
        with pytest.raises(ValueError, match="must install pihero-kiosk"):
            layer.ensure(app(tmp_path, user_data="#cloud-config\npackages:\n  - pihero\n"), cache=tmp_path, build=lambda *a: pytest.fail("built"), prepare_base=lambda: BASE, report=lambda m: None)


def app(root: Path, user_data: str = USER_DATA):
    return SimpleNamespace(name="probe", root=root, display=(800, 480), user_data=lambda: user_data)
