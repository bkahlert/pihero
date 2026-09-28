import pytest

from pihero_testkit import disk

pytestmark = pytest.mark.tier0

CARD = {"DeviceIdentifier": "disk9", "WholeDisk": True, "Internal": False, "RemovableMedia": True, "MediaName": "USB3.0 CRW   -SD", "TotalSize": 31914983424}
BIG_CARD = {**CARD, "DeviceIdentifier": "disk10", "MediaName": "SD Card Reader", "TotalSize": 63864569856}


class TestIsCard:
    def test_accepts_an_external_removable_whole_disk(self):
        result = disk.is_card(CARD)

        assert result is True

    def test_rejects_a_partition(self):
        result = disk.is_card({**CARD, "DeviceIdentifier": "disk9s1", "WholeDisk": False})

        assert result is False

    def test_rejects_the_internal_disk(self):
        result = disk.is_card({**CARD, "DeviceIdentifier": "disk0", "Internal": True, "RemovableMedia": False})

        assert result is False

    def test_rejects_an_external_drive_with_fixed_media(self):
        result = disk.is_card({**CARD, "RemovableMedia": False, "MediaName": "Samsung T7"})

        assert result is False


class TestCheckRemovable:
    def test_accepts_an_external_removable_whole_disk(self):
        result = disk.check_removable(CARD)

        assert result is None

    def test_rejects_the_internal_disk(self):
        with pytest.raises(SystemExit, match="disk0 .* not a removable disk"):
            disk.check_removable({**CARD, "DeviceIdentifier": "disk0", "Internal": True, "RemovableMedia": False, "MediaName": "APPLE SSD"})

    def test_rejects_an_external_drive_with_fixed_media(self):
        with pytest.raises(SystemExit, match="not a removable disk"):
            disk.check_removable({**CARD, "RemovableMedia": False})

    def test_rejects_a_partition(self):
        with pytest.raises(SystemExit, match="disk9s1 is a partition"):
            disk.check_removable({**CARD, "DeviceIdentifier": "disk9s1", "WholeDisk": False})


class TestDescribe:
    def test_names_identifier_media_and_size(self):
        line = disk.describe(CARD)

        assert line == "disk9  USB3.0 CRW   -SD  31.9 GB"


class TestCard:
    def test_returns_the_named_disk_after_the_removable_check(self, monkeypatch):
        monkeypatch.setattr(disk, "disk_info", lambda ident: {**CARD, "DeviceIdentifier": ident})

        info = disk.card("disk9")

        assert info["DeviceIdentifier"] == "disk9"

    def test_rejects_a_named_disk_that_is_no_card(self, monkeypatch):
        monkeypatch.setattr(disk, "disk_info", lambda ident: {**CARD, "DeviceIdentifier": ident, "Internal": True, "RemovableMedia": False})

        with pytest.raises(SystemExit, match="not a removable disk"):
            disk.card("disk0")

    def test_asks_when_the_identifier_is_empty(self, monkeypatch):
        monkeypatch.setattr(disk, "cards", lambda: [CARD, BIG_CARD])
        monkeypatch.setattr(disk.prompt, "choose", lambda title, options: 1)

        info = disk.card("")

        assert info is BIG_CARD

    def test_exits_without_a_card_present(self, monkeypatch):
        monkeypatch.setattr(disk, "cards", lambda: [])

        with pytest.raises(SystemExit, match="no SD card found"):
            disk.card("")
