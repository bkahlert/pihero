import os
from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0

SCRIPT = Path(__file__).resolve().parents[1] / "root" / "usr" / "lib" / "pihero" / "motd"
motd = load_script(SCRIPT)


class TestParseDpkg:
    def test_keeps_installed_packages_with_version(self):
        rows = motd.parse_dpkg("pihero 2.0.0 ii \npihero-avahi 2.0.0 ii \npihero-smb 1.0 rc \n")

        assert rows == [("pihero", "2.0.0"), ("pihero-avahi", "2.0.0")]

    def test_is_empty_on_no_output(self):
        assert motd.parse_dpkg("") == []


class TestParseFailed:
    def test_lists_unit_names(self):
        assert motd.parse_failed("pihero-avahi-render.service loaded failed failed Pi Hero\nfoo.service loaded failed failed Foo\n") == ["pihero-avahi-render.service", "foo.service"]

    def test_is_empty_on_no_output(self):
        assert motd.parse_failed("\n") == []


class TestParseUsb0:
    def test_returns_the_cidr(self):
        assert motd.parse_usb0("3: usb0    inet 10.10.10.60/29 brd 10.10.10.63 scope global usb0\\       valid_lft forever\n") == "10.10.10.60/29"

    def test_is_none_without_an_address(self):
        assert motd.parse_usb0("") is None


class TestRebootState:
    def test_reports_flag_and_packages(self, tmp_path):
        (tmp_path / "reboot-required").write_text("*** System restart required ***\n")
        (tmp_path / "reboot-required.pkgs").write_text("pihero-splash\n")

        assert motd.reboot_state(tmp_path) == (True, ["pihero-splash"])

    def test_reports_no_reboot_without_the_flag(self, tmp_path):
        assert motd.reboot_state(tmp_path) == (False, [])


class TestMood:
    def test_is_sad_on_a_failed_unit(self):
        assert motd.mood(["x.service"], False) == "sad"

    def test_is_unknown_on_a_pending_reboot(self):
        assert motd.mood([], True) == "unknown"

    def test_is_happy_otherwise(self):
        assert motd.mood([], False) == "happy"

    def test_a_failed_unit_wins_over_a_pending_reboot(self):
        assert motd.mood(["x.service"], True) == "sad"


class TestRender:
    def test_shows_every_line_with_defaults(self):
        text = motd.render("HERO\n", [("pihero", "2.0.0")], [], (False, []), None)

        assert text == "\nHERO\n\n  packages:        pihero 2.0.0\n  failed units:    none\n  reboot required: no\n  usb0:            not present\n"

    def test_sets_the_banner_apart_from_the_line_above(self):
        text = motd.render("HERO\n", [], [], (False, []), None)

        assert text.startswith("\nHERO\n")

    def test_lists_failed_units_and_reboot_packages(self):
        text = motd.render("", [], ["x.service"], (True, ["pihero-splash", "pihero-display-hdmi"]), "10.10.10.60/29")

        assert "  failed units:    x.service\n" in text
        assert "  reboot required: yes (pihero-splash, pihero-display-hdmi)\n" in text
        assert "  usb0:            10.10.10.60/29\n" in text

    def test_shows_yes_without_package_list(self):
        text = motd.render("", [], [], (True, []), None)

        assert "  reboot required: yes\n" in text


class TestMain:
    def test_renders_the_banner_through_kaomoji_hero_in_the_mood_of_the_state(self, tmp_path, monkeypatch, capsys):
        stub(tmp_path, "systemctl", 'printf "x.service loaded failed failed X\\n"')
        stub(tmp_path, "kaomoji", 'printf "%s\\n" "$*" >> "$0.log"; printf "HERO %s\\n" "$3"')
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        monkeypatch.setattr(motd, "RUN", tmp_path)

        motd.main()

        out = capsys.readouterr().out
        assert out.startswith("\nHERO sad\n\n")
        assert (tmp_path / "kaomoji.log").read_text() == "hero --mood sad --no-color\n"

    def test_asks_for_the_puzzled_hero_on_a_pending_reboot(self, tmp_path, monkeypatch, capsys):
        stub(tmp_path, "systemctl", "")
        stub(tmp_path, "kaomoji", 'printf "HERO %s\\n" "$3"')
        (tmp_path / "reboot-required").write_text("*** System restart required ***\n")
        monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        monkeypatch.setattr(motd, "RUN", tmp_path)

        motd.main()

        out = capsys.readouterr().out
        assert out.startswith("\nHERO unknown\n\n")

    def test_prints_the_lines_without_a_hero(self, tmp_path, monkeypatch, capsys):
        stub(tmp_path, "systemctl", "")
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.setattr(motd, "RUN", tmp_path)

        motd.main()

        out = capsys.readouterr().out
        assert out.startswith("\n\n\n  packages:")
        assert "  failed units:    none\n" in out
        assert "  reboot required: no\n" in out


def stub(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path
