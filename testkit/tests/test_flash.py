import hashlib
import lzma
import os

import pytest

from pihero_testkit import flash

pytestmark = pytest.mark.tier0

CARD = {"DeviceIdentifier": "disk9", "WholeDisk": True, "Internal": False, "RemovableMedia": True, "MediaName": "USB3.0 CRW   -SD"}


class TestWriteImage:
    def test_writes_the_decompressed_image_padded_to_whole_sectors(self, tmp_path):
        payload = os.urandom(flash.CHUNK + 100)
        image = xz_image(tmp_path, payload)
        target = tmp_path / "card"
        fd = os.open(target, os.O_RDWR | os.O_CREAT)

        try:
            size, digest = flash.write_image(fd, image)
        finally:
            os.close(fd)

        assert size == len(payload)
        assert digest == hashlib.sha256(payload).hexdigest()
        written = target.read_bytes()
        assert len(written) == len(payload) + 412
        assert written[: len(payload)] == payload
        assert written[len(payload) :] == bytes(412)

    def test_leaves_a_sector_aligned_image_unpadded(self, tmp_path):
        payload = os.urandom(flash.SECTOR * 3)
        image = xz_image(tmp_path, payload)
        target = tmp_path / "card"
        fd = os.open(target, os.O_RDWR | os.O_CREAT)

        try:
            size, _ = flash.write_image(fd, image)
        finally:
            os.close(fd)

        assert size == len(payload)
        assert target.read_bytes() == payload


class TestReadBack:
    def test_hashes_only_the_image_bytes_of_a_padded_target(self, tmp_path):
        payload = b"pihero" * 1000
        target = tmp_path / "card"
        target.write_bytes(payload + bytes(-len(payload) % flash.SECTOR) + b"old card contents" * 100)
        fd = os.open(target, os.O_RDONLY)

        try:
            digest = flash.read_back(fd, len(payload))
        finally:
            os.close(fd)

        assert digest == hashlib.sha256(payload).hexdigest()

    def test_matches_what_write_image_wrote(self, tmp_path):
        image = xz_image(tmp_path, os.urandom(flash.CHUNK + 1))
        fd = os.open(tmp_path / "card", os.O_RDWR | os.O_CREAT)

        try:
            size, written = flash.write_image(fd, image)
            read = flash.read_back(fd, size)
        finally:
            os.close(fd)

        assert read == written

    def test_fails_on_a_target_shorter_than_the_image(self, tmp_path):
        target = tmp_path / "card"
        target.write_bytes(bytes(flash.SECTOR))
        fd = os.open(target, os.O_RDONLY)

        try:
            with pytest.raises(SystemExit, match="short read"):
                flash.read_back(fd, flash.SECTOR * 2)
        finally:
            os.close(fd)


class TestDeviceDir:
    def test_accepts_a_directory_with_user_data(self, tmp_path):
        (tmp_path / "user-data").write_text("#cloud-config\n")

        path = flash.device_dir(str(tmp_path))

        assert path == tmp_path

    def test_resolves_a_name_under_devices(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "devices" / "pi").mkdir(parents=True)
        (tmp_path / "devices" / "pi" / "user-data").write_text("#cloud-config\n")

        path = flash.device_dir("pi")

        assert path == tmp_path / "devices" / "pi"

    def test_rejects_a_directory_without_user_data(self, tmp_path):
        with pytest.raises(SystemExit, match="no user-data"):
            flash.device_dir(str(tmp_path))


class TestCheckRemovable:
    def test_accepts_an_external_removable_whole_disk(self):
        result = flash.check_removable(CARD)

        assert result is None

    def test_rejects_the_internal_disk(self):
        with pytest.raises(SystemExit, match="disk0 .* not a removable disk"):
            flash.check_removable({**CARD, "DeviceIdentifier": "disk0", "Internal": True, "RemovableMedia": False, "MediaName": "APPLE SSD"})

    def test_rejects_an_external_drive_with_fixed_media(self):
        with pytest.raises(SystemExit, match="not a removable disk"):
            flash.check_removable({**CARD, "RemovableMedia": False})

    def test_rejects_a_partition(self):
        with pytest.raises(SystemExit, match="disk9s1 is a partition"):
            flash.check_removable({**CARD, "DeviceIdentifier": "disk9s1", "WholeDisk": False})


class TestCopyDeviceFiles:
    def test_copies_the_cloud_init_files_that_exist(self, tmp_path):
        device = tmp_path / "device"
        device.mkdir()
        (device / "user-data").write_text("#cloud-config\n")
        (device / "network-config").write_text("network:\n  version: 2\n")
        (device / "notes.md").write_text("stays home\n")
        bootfs = tmp_path / "bootfs"
        bootfs.mkdir()

        copied = flash.copy_device_files(device, bootfs)

        assert copied == ["user-data", "network-config"]
        assert (bootfs / "user-data").read_text() == "#cloud-config\n"
        assert (bootfs / "network-config").read_text() == "network:\n  version: 2\n"
        assert sorted(p.name for p in bootfs.iterdir()) == ["network-config", "user-data"]


def xz_image(tmp_path, payload: bytes):
    image = tmp_path / "os.img.xz"
    with lzma.open(image, "wb") as out:
        out.write(payload)
    return image
