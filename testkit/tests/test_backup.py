import hashlib
import lzma
import os
import tomllib
from datetime import date
from pathlib import Path

import pytest

from pihero_testkit import backup, flash

pytestmark = pytest.mark.tier0

CARD = {"DeviceIdentifier": "disk9", "WholeDisk": True, "Internal": False, "RemovableMedia": True, "MediaName": "USB3.0 CRW   -SD", "TotalSize": 31914983424}
DAY = date(2026, 9, 28)
SAMPLE = Path("devices/sample/user-data")


class TestHostname:
    def test_reads_an_unquoted_hostname(self):
        host = backup.hostname("#cloud-config\nhostname: mypi\nmanage_etc_hosts: true\n")

        assert host == "mypi"

    def test_reads_a_quoted_hostname(self):
        host = backup.hostname('hostname: "my-pi"\n')

        assert host == "my-pi"

    def test_ignores_an_indented_key(self):
        host = backup.hostname("users:\n  - name: pi\n    hostname: nope\n")

        assert host is None

    def test_ignores_a_commented_key(self):
        host = backup.hostname("# hostname: nope\ntimezone: Europe/Berlin\n")

        assert host is None

    def test_is_none_without_a_hostname(self):
        host = backup.hostname("#cloud-config\ntimezone: Europe/Berlin\n")

        assert host is None

    def test_reads_the_sample_device_file(self):
        host = backup.hostname(SAMPLE.read_text())

        assert host == "sample"


class TestImageName:
    def test_joins_host_and_iso_date(self):
        name = backup.image_name("mypi", DAY)

        assert name == "mypi-2026-09-28.img.xz"

    def test_refuses_a_name_that_is_not_a_file_name(self):
        with pytest.raises(SystemExit, match="not a valid name"):
            backup.image_name("../mypi", DAY)

    def test_refuses_a_name_with_spaces(self):
        with pytest.raises(SystemExit, match="not a valid name"):
            backup.image_name("my pi", DAY)


class TestSidecarFor:
    def test_replaces_the_image_suffixes_with_toml(self):
        sidecar = backup.sidecar_for(Path("backups/mypi-2026-09-28.img.xz"))

        assert sidecar == Path("backups/mypi-2026-09-28.toml")


class TestDump:
    def test_round_trips_through_write_image(self, tmp_path):
        payload = os.urandom(flash.CHUNK + 4096) + bytes(flash.CHUNK) + b"tail"
        card = tmp_path / "card"
        card.write_bytes(payload)
        image = tmp_path / "pi.img.xz"

        fd = os.open(card, os.O_RDONLY)
        try:
            size, digest = backup.dump(fd, image, len(payload))
        finally:
            os.close(fd)

        assert size == len(payload)
        assert digest == hashlib.sha256(payload).hexdigest()
        restored = tmp_path / "restored"
        fd = os.open(restored, os.O_RDWR | os.O_CREAT)
        try:
            written = flash.write_image(fd, image)
        finally:
            os.close(fd)
        assert written == (size, digest)
        assert restored.read_bytes()[: len(payload)] == payload

    def test_compresses_zeros_to_almost_nothing(self, tmp_path):
        card = tmp_path / "card"
        card.write_bytes(bytes(8 * flash.CHUNK))
        image = tmp_path / "pi.img.xz"

        fd = os.open(card, os.O_RDONLY)
        try:
            backup.dump(fd, image, 8 * flash.CHUNK)
        finally:
            os.close(fd)

        assert image.stat().st_size < 64 << 10


class TestWriteSidecar:
    def test_writes_size_and_sha256_as_toml(self, tmp_path):
        image = tmp_path / "mypi-2026-09-28.img.xz"

        sidecar = backup.write_sidecar(image, 31914983424, "ab" * 32)

        assert sidecar == tmp_path / "mypi-2026-09-28.toml"
        assert tomllib.loads(sidecar.read_text()) == {"size": 31914983424, "sha256": "ab" * 32}


class TestBackup:
    def test_writes_image_and_sidecar_then_ejects(self, tmp_path, monkeypatch):
        payload = os.urandom(3 * flash.SECTOR)
        card = fake_card(tmp_path, payload, monkeypatch)
        ejected = []
        monkeypatch.setattr(backup.disk, "eject", ejected.append)

        image = backup.backup({**CARD, "TotalSize": len(payload)}, "mypi", DAY, tmp_path / "backups")

        assert image == tmp_path / "backups" / "mypi-2026-09-28.img.xz"
        with lzma.open(image) as stream:
            assert stream.read() == payload
        assert tomllib.loads(backup.sidecar_for(image).read_text()) == {"size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        assert ejected == ["disk9"]
        assert card.read_bytes() == payload

    def test_opens_the_card_read_only(self, tmp_path, monkeypatch):
        fake_card(tmp_path, bytes(flash.SECTOR), monkeypatch)
        opened = []
        monkeypatch.setattr(backup.disk, "open_raw", lambda ident, flags: opened.append(flags) or os.open(tmp_path / "card", flags))

        backup.backup({**CARD, "TotalSize": flash.SECTOR}, "mypi", DAY, tmp_path / "backups")

        assert opened == [os.O_RDONLY]

    def test_refuses_an_existing_image_untouched(self, tmp_path):
        backups = tmp_path / "backups"
        backups.mkdir()
        existing = backups / "mypi-2026-09-28.img.xz"
        existing.write_bytes(b"old")

        with pytest.raises(SystemExit, match="exists"):
            backup.backup(CARD, "mypi", DAY, backups)

        assert existing.read_bytes() == b"old"

    def test_removes_the_partial_image_on_interrupt(self, tmp_path, monkeypatch):
        fake_card(tmp_path, bytes(flash.SECTOR), monkeypatch)
        monkeypatch.setattr(backup, "dump", interrupting_dump)

        with pytest.raises(KeyboardInterrupt):
            backup.backup({**CARD, "TotalSize": flash.SECTOR}, "mypi", DAY, tmp_path / "backups")

        assert list((tmp_path / "backups").iterdir()) == []


def fake_card(tmp_path, payload: bytes, monkeypatch) -> Path:
    card = tmp_path / "card"
    card.write_bytes(payload)
    monkeypatch.setattr(backup.disk, "unmount", lambda ident: None)
    monkeypatch.setattr(backup.disk, "open_raw", lambda ident, flags: os.open(card, flags))
    monkeypatch.setattr(backup.disk, "eject", lambda ident: None)
    return card


def interrupting_dump(fd, image, total, report=None):
    image.write_bytes(b"partial")
    raise KeyboardInterrupt
