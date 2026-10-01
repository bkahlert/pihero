from pathlib import Path

import pytest

from pihero_testkit import model_icons
from pihero_testkit.model_icons import Table

pytestmark = pytest.mark.tier0


class TestDumpCommand:
    def test_names_every_model_identifier_after_the_dump_options(self):
        command = model_icons.dump_command(("AirPort4", "MacPro7,1@ECOLOR=226,226,224"))

        assert command == [
            *model_icons.DEVICE_ICONS, "dump", "--horizontal", "--no-open",
            "--model", "AirPort4", "--model", "MacPro7,1@ECOLOR=226,226,224",
        ]


class TestTable:
    def test_drops_the_lead_sentence(self):
        table = model_icons.table(DUMP_README, "")

        assert table.startswith("| Model identifier |")

    def test_prefixes_the_image_paths(self):
        table = model_icons.table(DUMP_README, "../docs/models/")

        assert 'src="../docs/models/icons/com.apple.airport-express.png"' in table
        assert 'src="../docs/models/sidebar/SidebarAirportExpress.png"' in table

    def test_keeps_the_widths_without_one(self):
        table = model_icons.table(DUMP_README, "")

        assert 'width="128"' in table
        assert 'width="32"' in table

    def test_sets_every_width_to_the_given_one(self):
        table = model_icons.table(DUMP_README, "", width=64)

        assert table.count('width="64"') == 2
        assert 'width="128"' not in table
        assert 'width="32"' not in table

    def test_ends_with_one_newline(self):
        table = model_icons.table(DUMP_README + "\n\n", "")

        assert table.endswith("|\n")
        assert not table.endswith("\n\n")


class TestComment:
    def test_is_an_html_comment(self):
        comment = model_icons.comment(DEVICES)

        assert comment.startswith("<!--\n")
        assert comment.endswith("\n-->\n")

    def test_names_the_call_with_every_model_identifier(self):
        comment = model_icons.comment(DEVICES)

        assert "device-icons dump --horizontal --no-open" in comment
        assert "--model AirPort7,120" in comment
        assert "--model MacPro7,1@ECOLOR=226,226,224" in comment

    def test_continues_every_wrapped_line_of_the_call(self):
        comment = model_icons.comment(DEVICES)

        call = [line for line in comment.splitlines() if line.startswith("    ")]
        assert len(call) > 1
        assert all(line.endswith(" \\") for line in call[:-1])
        assert not call[-1].endswith("\\")
        assert call[0].endswith("device-icons dump --horizontal --no-open \\")
        assert all(line.strip(" \\").startswith("--model ") for line in call[1:])
        assert all(len(line) <= 100 for line in call[1:])

    def test_names_the_prefix(self):
        comment = model_icons.comment(DEVICES)

        assert "prefixed with ../docs/models/" in comment

    def test_names_the_width_when_given(self):
        comment = model_icons.comment(README)

        assert "every width set to 64" in comment

    def test_leaves_the_width_out_without_one(self):
        comment = model_icons.comment(DEVICES)

        assert "width" not in comment


class TestSplice:
    def test_replaces_what_lies_between_the_markers(self):
        text = f"before\n{model_icons.START}\nold table\n{model_icons.END}\nafter\n"

        result = model_icons.splice(text, "new table\n")

        assert result == f"before\n{model_icons.START}\nnew table\n{model_icons.END}\nafter\n"

    def test_is_idempotent(self):
        text = f"{model_icons.START}\n{model_icons.END}\n"

        once = model_icons.splice(text, "table\n\n<!--\nhow\n-->\n")
        twice = model_icons.splice(once, "table\n\n<!--\nhow\n-->\n")

        assert twice == once

    def test_refuses_a_text_without_markers(self):
        with pytest.raises(ValueError, match="docs-models"):
            model_icons.splice("no markers\n", "table\n")

    def test_refuses_a_text_with_the_markers_reversed(self):
        with pytest.raises(ValueError, match="docs-models"):
            model_icons.splice(f"{model_icons.END}\n{model_icons.START}\n", "table\n")


class TestInstall:
    def test_replaces_docs_models_with_the_union_of_the_dumps_images(self, tmp_path):
        root = repo(tmp_path)
        (root / "docs" / "models" / "stale.png").write_bytes(b"old")
        first = dump(tmp_path / "first", icons=["com.apple.airport-express"], sidebars=["SidebarAirportExpress"])
        second = dump(tmp_path / "second", icons=["com.apple.macpro-cylinder"], sidebars=["SidebarMacProCylinder"])

        model_icons.install(root, [(DEVICES, first), (README, second)])

        assert not (root / "docs" / "models" / "stale.png").exists()
        assert sorted(p.name for p in (root / "docs" / "models" / "icons").iterdir()) == ["com.apple.airport-express.png", "com.apple.macpro-cylinder.png"]
        assert sorted(p.name for p in (root / "docs" / "models" / "sidebar").iterdir()) == ["SidebarAirportExpress.png", "SidebarMacProCylinder.png"]

    def test_splices_each_readme_with_its_table_and_comment(self, tmp_path):
        root = repo(tmp_path)
        first = dump(tmp_path / "first", icons=["com.apple.airport-express"], sidebars=["SidebarAirportExpress"])
        second = dump(tmp_path / "second", icons=["com.apple.airport-express"], sidebars=["SidebarAirportExpress"])

        model_icons.install(root, [(DEVICES, first), (README, second)])

        devices = (root / "devices" / "README.md").read_text()
        readme = (root / "README.md").read_text()
        assert devices.startswith(f"# Devices\n\n{model_icons.START}\n| Model identifier |")
        assert 'src="../docs/models/icons/com.apple.airport-express.png" alt="com.apple.airport-express" width="128"' in devices
        assert f"\n-->\n{model_icons.END}\n\nChanging it later.\n" in devices
        assert 'src="docs/models/icons/com.apple.airport-express.png" alt="com.apple.airport-express" width="64"' in readme
        assert "every width set to 64" in readme
        assert readme.endswith(f"{model_icons.END}\n\nAll eleven choices.\n")


DUMP_README = (
    "The icon Finder draws for each model identifier, dumped from `CoreTypes.bundle` by [device-icons](https://github.com/bkahlert/device-icons).\n"
    "\n"
    "| Model identifier | `AirPort4` |\n"
    "| --- | :-: |\n"
    "| Type identifier | `com.apple.airport-express` |\n"
    "| Kind | Mac |\n"
    '| Icon | <img src="icons/com.apple.airport-express.png" alt="com.apple.airport-express" width="128"> |\n'
    '| Sidebar icon | <img src="sidebar/SidebarAirportExpress.png" alt="SidebarAirportExpress" width="32"> |\n'
)
DEVICES = Table(
    "devices/README.md",
    ("AirPort4", "AirPort5", "AirPort6", "AirPort7,120", "Macmini8,1", "Macmini9,1", "MacPro6,1", "MacPro5,1", "MacPro7,1@ECOLOR=225,225,223", "MacPro7,1@ECOLOR=226,226,224", "Xserve3,1"),
    "../docs/models/",
)
README = Table("README.md", ("AirPort4",), "docs/models/", width=64)


def repo(root: Path) -> Path:
    (root / "docs" / "models").mkdir(parents=True)
    (root / "devices").mkdir()
    (root / "devices" / "README.md").write_text(f"# Devices\n\n{model_icons.START}\n| old |\n{model_icons.END}\n\nChanging it later.\n")
    (root / "README.md").write_text(f"# Pi Hero\n\n{model_icons.START}\n{model_icons.END}\n\nAll eleven choices.\n")
    return root


def dump(out: Path, *, icons: list[str], sidebars: list[str]) -> Path:
    (out / "icons").mkdir(parents=True)
    (out / "sidebar").mkdir()
    (out / "by-sidebar").mkdir()
    for icon in icons:
        (out / "icons" / f"{icon}.png").write_bytes(b"icon")
    for sidebar in sidebars:
        (out / "sidebar" / f"{sidebar}.png").write_bytes(b"sidebar")
    (out / "index.json").write_text("{}")
    (out / "README.md").write_text(DUMP_README)
    return out
