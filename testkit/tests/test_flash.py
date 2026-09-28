import hashlib
import lzma
import os

import pytest

from pihero_testkit import flash, prepare

pytestmark = pytest.mark.tier0


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


class TestImageName:
    def test_reads_the_name_from_a_leading_comment(self):
        name = flash.image_name("#cloud-config\n# board: Raspberry Pi Zero W\n# image: raspios_lite_armhf\nhostname: pi\n")

        assert name == "raspios_lite_armhf"

    def test_defaults_to_the_tier_2_image_without_the_line(self):
        name = flash.image_name("#cloud-config\n# board: Raspberry Pi Zero 2 W\nhostname: pi\n")

        assert name == prepare.TIER2_IMAGE

    def test_ignores_the_line_once_the_config_has_started(self):
        name = flash.image_name("#cloud-config\nhostname: pi\n# image: raspios_lite_armhf\n")

        assert name == prepare.TIER2_IMAGE


class TestImageFor:
    def test_resolves_the_named_image_from_the_lock(self, tmp_path):
        (tmp_path / "user-data").write_text("#cloud-config\n# image: raspios_lite_armhf\n")

        name, config = flash.image_for(tmp_path)

        assert name == "raspios_lite_armhf"
        assert config["url"].endswith("-armhf-lite.img.xz")

    def test_rejects_an_image_the_lock_does_not_pin(self, tmp_path):
        (tmp_path / "user-data").write_text("#cloud-config\n# image: raspios_full_arm64\n")

        with pytest.raises(SystemExit, match="raspios_full_arm64.*pins raspios_lite_arm64, raspios_lite_armhf"):
            flash.image_for(tmp_path)


class TestRegulatoryDomain:
    def test_reads_the_quoted_code_from_network_config(self):
        code = flash.regulatory_domain('network:\n  wifis:\n    wlan0:\n      regulatory-domain: "DE"\n      dhcp4: true\n')

        assert code == "DE"

    def test_reads_an_unquoted_code(self):
        code = flash.regulatory_domain("      regulatory-domain: GB\n")

        assert code == "GB"

    def test_is_none_without_a_domain(self):
        code = flash.regulatory_domain("network:\n  version: 2\n  wifis:\n    wlan0:\n      dhcp4: true\n")

        assert code is None


class TestWithRegulatoryDomain:
    def test_appends_the_parameter_to_the_single_line(self):
        cmdline = flash.with_regulatory_domain("console=serial0,115200 console=tty1 root=PARTUUID=4d8fd085-02 rootwait resize\n", "DE")

        assert cmdline == "console=serial0,115200 console=tty1 root=PARTUUID=4d8fd085-02 rootwait resize cfg80211.ieee80211_regdom=DE\n"

    def test_replaces_an_existing_parameter(self):
        cmdline = flash.with_regulatory_domain("console=tty1 cfg80211.ieee80211_regdom=GB root=PARTUUID=4d8fd085-02 rootwait\n", "DE")

        assert cmdline == "console=tty1 root=PARTUUID=4d8fd085-02 rootwait cfg80211.ieee80211_regdom=DE\n"
        assert cmdline.count("\n") == 1


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
