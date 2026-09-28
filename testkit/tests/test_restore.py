import hashlib
import lzma
import os
import sys
from pathlib import Path

import pytest

from pihero_testkit import backup, flash, restore

pytestmark = pytest.mark.tier0

CARD = {"DeviceIdentifier": "disk9", "WholeDisk": True, "Internal": False, "RemovableMedia": True, "MediaName": "USB3.0 CRW   -SD", "TotalSize": 31914983424}


class TestCheckFits:
    def test_refuses_a_smaller_card_naming_both_sizes(self):
        with pytest.raises(SystemExit, match=r"disk9 holds 31\.9 GB, the image needs 32\.0 GB"):
            restore.check_fits(CARD, 32_000_000_000)

    def test_names_the_shortfall_when_both_sizes_round_alike(self):
        with pytest.raises(SystemExit, match=r"disk9 holds 31\.9 GB, the image needs 31\.9 GB \(21 MiB short\)"):
            restore.check_fits({**CARD, "TotalSize": 31893291008}, 31914983424)

    def test_accepts_an_equal_card(self):
        result = restore.check_fits(CARD, CARD["TotalSize"])

        assert result is None

    def test_accepts_a_larger_card(self):
        result = restore.check_fits(CARD, 16_000_000_000)

        assert result is None


class TestSidecar:
    def test_reads_size_and_sha256(self, tmp_path):
        image = tmp_path / "mypi-2026-09-28.img.xz"
        backup.write_sidecar(image, 1234, "cd" * 32)

        meta = restore.sidecar(image)

        assert meta == {"size": 1234, "sha256": "cd" * 32}

    def test_is_none_without_a_sidecar(self, tmp_path):
        meta = restore.sidecar(tmp_path / "mypi-2026-09-28.img.xz")

        assert meta is None

    def test_refuses_a_malformed_sidecar_naming_it(self, tmp_path):
        image = tmp_path / "mypi-2026-09-28.img.xz"
        backup.sidecar_for(image).write_text("size = \n")

        with pytest.raises(SystemExit, match=r"mypi-2026-09-28\.toml is not a valid sidecar"):
            restore.sidecar(image)

    def test_refuses_a_sidecar_without_a_size(self, tmp_path):
        image = tmp_path / "mypi-2026-09-28.img.xz"
        backup.sidecar_for(image).write_text('sha256 = "ab"\n')

        with pytest.raises(SystemExit, match="not a valid sidecar"):
            restore.sidecar(image)


class TestImages:
    def test_lists_images_newest_first(self, tmp_path):
        older = tmp_path / "mypi-2026-09-01.img.xz"
        newer = tmp_path / "other-2026-09-28.img.xz"
        older.write_bytes(b"")
        newer.write_bytes(b"")
        os.utime(older, (1_700_000_000, 1_700_000_000))
        os.utime(newer, (1_800_000_000, 1_800_000_000))

        found = restore.images(tmp_path)

        assert found == [newer, older]

    def test_ignores_files_that_are_no_images(self, tmp_path):
        (tmp_path / "mypi-2026-09-28.toml").write_text("size = 1\n")
        (tmp_path / "notes.txt").write_text("")

        found = restore.images(tmp_path)

        assert found == []


class TestDescribe:
    def test_names_the_card_size_the_image_needs(self, tmp_path):
        image = tmp_path / "mypi-2026-09-28.img.xz"
        backup.write_sidecar(image, 31914983424, "ab" * 32)

        line = restore.describe(image)

        assert line == "mypi-2026-09-28.img.xz  needs a 31.9 GB card"

    def test_says_so_without_a_sidecar(self, tmp_path):
        line = restore.describe(tmp_path / "mypi-2026-09-28.img.xz")

        assert line == "mypi-2026-09-28.img.xz  (no sidecar)"


class TestImageFor:
    def test_returns_the_given_path(self, tmp_path):
        given = tmp_path / "mypi-2026-09-28.img.xz"
        given.write_bytes(b"")

        image = restore.image_for(str(given))

        assert image == given

    def test_refuses_a_missing_path(self, tmp_path):
        with pytest.raises(SystemExit, match="not found"):
            restore.image_for(str(tmp_path / "gone.img.xz"))

    def test_refuses_a_file_that_is_no_image(self, tmp_path):
        sidecar = tmp_path / "mypi-2026-09-28.toml"
        sidecar.write_text("size = 1\n")

        with pytest.raises(SystemExit, match=r"is not an \.img\.xz image"):
            restore.image_for(str(sidecar))

    def test_asks_when_the_path_is_empty(self, tmp_path, monkeypatch):
        first = tmp_path / "a-2026-09-28.img.xz"
        second = tmp_path / "b-2026-09-01.img.xz"
        first.write_bytes(b"")
        second.write_bytes(b"")
        os.utime(first, (1_800_000_000, 1_800_000_000))
        os.utime(second, (1_700_000_000, 1_700_000_000))
        monkeypatch.setattr(restore.prompt, "choose", lambda title, options: 1)

        image = restore.image_for("", tmp_path)

        assert image == second

    def test_exits_without_images(self, tmp_path):
        with pytest.raises(SystemExit, match="no images"):
            restore.image_for("", tmp_path)


class TestCheck:
    def test_returns_the_sidecar_of_an_image_that_fits(self, tmp_path):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)

        meta = restore.check(image, {**CARD, "TotalSize": len(payload)})

        assert meta == {"size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}

    def test_refuses_a_smaller_card(self, tmp_path):
        payload = os.urandom(4 * flash.SECTOR)
        image = backup_image(tmp_path, payload)

        with pytest.raises(SystemExit, match="use a larger card"):
            restore.check(image, {**CARD, "TotalSize": len(payload) - flash.SECTOR})

    def test_is_none_and_says_so_without_a_sidecar(self, tmp_path, capsys):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        backup.sidecar_for(image).unlink()

        meta = restore.check(image, {**CARD, "TotalSize": len(payload)})

        assert meta is None
        assert "skipping the size and integrity checks" in capsys.readouterr().err


class TestRestore:
    def test_writes_verifies_and_ejects(self, tmp_path, monkeypatch, capsys):
        payload = os.urandom(3 * flash.SECTOR + 100)
        image = backup_image(tmp_path, payload)
        card = fake_card(tmp_path, bytes(len(payload) + 4096), monkeypatch)
        ejected = []
        monkeypatch.setattr(restore.disk, "eject", ejected.append)

        restore.restore(image, {**CARD, "TotalSize": len(payload) + 4096}, restore.sidecar(image))

        assert card.read_bytes()[: len(payload)] == payload
        assert ejected == ["disk9"]
        assert "raspi-config --expand-rootfs" in capsys.readouterr().err

    def test_does_not_mention_expanding_on_an_equal_card(self, tmp_path, monkeypatch, capsys):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        fake_card(tmp_path, bytes(len(payload)), monkeypatch)

        restore.restore(image, {**CARD, "TotalSize": len(payload)}, restore.sidecar(image))

        assert "expand-rootfs" not in capsys.readouterr().err

    def test_reports_a_damaged_image(self, tmp_path, monkeypatch):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        fake_card(tmp_path, bytes(len(payload)), monkeypatch)

        with pytest.raises(SystemExit, match="damaged"):
            restore.restore(image, {**CARD, "TotalSize": len(payload)}, {"size": len(payload), "sha256": "00" * 32})

    def test_reports_a_file_that_is_no_xz_as_damaged_without_writing(self, tmp_path, monkeypatch):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        image.write_bytes(b"not an xz stream at all")
        card = fake_card(tmp_path, bytes(len(payload)), monkeypatch)

        with pytest.raises(SystemExit, match="damaged"):
            restore.restore(image, {**CARD, "TotalSize": len(payload)}, restore.sidecar(image))

        assert card.read_bytes() == bytes(len(payload))

    def test_reports_a_truncated_image_as_damaged(self, tmp_path, monkeypatch):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        image.write_bytes(image.read_bytes()[: image.stat().st_size // 2])
        fake_card(tmp_path, bytes(len(payload)), monkeypatch)

        with pytest.raises(SystemExit, match="damaged"):
            restore.restore(image, {**CARD, "TotalSize": len(payload)}, restore.sidecar(image))

    def test_writes_without_a_sidecar(self, tmp_path, monkeypatch):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        backup.sidecar_for(image).unlink()
        card = fake_card(tmp_path, bytes(len(payload)), monkeypatch)

        restore.restore(image, {**CARD, "TotalSize": len(payload)}, None)

        assert card.read_bytes() == payload


class TestMain:
    def test_refuses_a_smaller_card_before_asking_and_before_opening_it(self, tmp_path, monkeypatch):
        payload = os.urandom(4 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        fake_card(tmp_path, bytes(len(payload)), monkeypatch)
        asked, opened = [], []
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(restore.disk, "card", lambda ident: {**CARD, "TotalSize": len(payload) - flash.SECTOR})
        monkeypatch.setattr(restore.prompt, "confirm", lambda question: asked.append(question) or True)
        monkeypatch.setattr(restore.disk, "open_raw", lambda ident, flags: opened.append(flags))

        with pytest.raises(SystemExit, match="use a larger card"):
            restore.main(["--image", str(image), "--disk", ""])

        assert asked == []
        assert opened == []

    def test_writes_without_confirmation_when_image_and_disk_are_given(self, tmp_path, monkeypatch):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        card = fake_card(tmp_path, bytes(len(payload)), monkeypatch)
        asked = []
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(restore.disk, "card", lambda ident: {**CARD, "TotalSize": len(payload)})
        monkeypatch.setattr(restore.prompt, "confirm", lambda question: asked.append(question) or False)

        code = restore.main(["--image", str(image), "--disk", "disk9"])

        assert code == 0
        assert asked == []
        assert card.read_bytes() == payload

    def test_asks_for_confirmation_when_the_card_was_chosen_and_stops_on_no(self, tmp_path, monkeypatch):
        payload = os.urandom(2 * flash.SECTOR)
        image = backup_image(tmp_path, payload)
        card = fake_card(tmp_path, bytes(len(payload)), monkeypatch)
        asked = []
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(restore.disk, "card", lambda ident: {**CARD, "TotalSize": len(payload)})
        monkeypatch.setattr(restore.prompt, "confirm", lambda question: asked.append(question) or False)

        code = restore.main(["--image", str(image), "--disk", ""])

        assert code == 1
        assert asked == [f"Restore {image.name} onto disk9  USB3.0 CRW   -SD  0.0 GB?"]
        assert card.read_bytes() == bytes(len(payload))


def backup_image(tmp_path, payload: bytes) -> Path:
    image = tmp_path / "mypi-2026-09-28.img.xz"
    with lzma.open(image, "wb") as out:
        out.write(payload)
    backup.write_sidecar(image, len(payload), hashlib.sha256(payload).hexdigest())
    return image


def fake_card(tmp_path, contents: bytes, monkeypatch) -> Path:
    card = tmp_path / "card"
    card.write_bytes(contents)
    monkeypatch.setattr(restore.disk, "unmount", lambda ident: None)
    monkeypatch.setattr(restore.disk, "open_raw", lambda ident, flags: os.open(card, flags))
    monkeypatch.setattr(restore.disk, "eject", lambda ident: None)
    return card
