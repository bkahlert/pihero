import hashlib
import lzma
import os
from pathlib import Path

import pytest

from pihero_testkit import flash, prepare

pytestmark = pytest.mark.tier0

CARD = {"DeviceIdentifier": "disk9", "WholeDisk": True, "Internal": False, "RemovableMedia": True, "MediaName": "USB3.0 CRW   -SD", "TotalSize": 31914983424}
SAMPLE = Path("devices/sample/user-data")


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


class TestHostname:
    def test_reads_an_unquoted_hostname(self):
        host = flash.hostname("#cloud-config\nhostname: mypi\nmanage_etc_hosts: true\n")

        assert host == "mypi"

    def test_reads_a_quoted_hostname(self):
        host = flash.hostname('hostname: "my-pi"\n')

        assert host == "my-pi"

    def test_ignores_an_indented_key(self):
        host = flash.hostname("users:\n  - name: pi\n    hostname: nope\n")

        assert host is None

    def test_ignores_a_commented_key(self):
        host = flash.hostname("# hostname: nope\ntimezone: Europe/Berlin\n")

        assert host is None

    def test_is_none_without_a_hostname(self):
        host = flash.hostname("#cloud-config\ntimezone: Europe/Berlin\n")

        assert host is None

    def test_reads_the_sample_device_file(self):
        host = flash.hostname(SAMPLE.read_text())

        assert host == "sample"


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


class TestFlash:
    def test_forgets_the_devices_host_in_ghosttys_ssh_cache_once_the_card_is_done(self, tmp_path, monkeypatch):
        device = tmp_path / "device"
        device.mkdir()
        (device / "user-data").write_text("#cloud-config\nhostname: mypi\n")
        payload = os.urandom(2 * flash.SECTOR)
        card = fake_flash(tmp_path, payload, monkeypatch)
        forgotten = []
        monkeypatch.setattr(flash.ghostty, "forget", lambda host, report: forgotten.append((host, card.read_bytes() == payload)) or [])

        flash.flash(device, "disk9")

        assert forgotten == [("mypi", True)]

    def test_leaves_the_cache_alone_for_a_device_without_a_hostname(self, tmp_path, monkeypatch):
        device = tmp_path / "device"
        device.mkdir()
        (device / "user-data").write_text("#cloud-config\ntimezone: Europe/Berlin\n")
        fake_flash(tmp_path, os.urandom(2 * flash.SECTOR), monkeypatch)
        forgotten = []
        monkeypatch.setattr(flash.ghostty, "forget", lambda host, report: forgotten.append(host) or [])

        flash.flash(device, "disk9")

        assert forgotten == []


def xz_image(tmp_path, payload: bytes):
    image = tmp_path / "os.img.xz"
    with lzma.open(image, "wb") as out:
        out.write(payload)
    return image


def fake_flash(tmp_path, payload: bytes, monkeypatch) -> Path:
    """Points flash at a file standing in for the card and a downloaded image holding payload; returns the card."""
    image = xz_image(tmp_path, payload)
    card = tmp_path / "card"
    card.write_bytes(bytes(len(payload)))
    (tmp_path / "bootfs").mkdir()
    monkeypatch.setattr(flash, "disk_info", lambda disk: CARD)
    monkeypatch.setattr(flash.prepare, "download", lambda url, sha256: image)
    monkeypatch.setattr(flash, "unmount", lambda disk: None)
    monkeypatch.setattr(flash, "open_raw", lambda disk, flags: os.open(card, flags))
    monkeypatch.setattr(flash, "mount_bootfs", lambda disk: tmp_path / "bootfs")
    monkeypatch.setattr(flash, "eject", lambda disk: None)
    return card
