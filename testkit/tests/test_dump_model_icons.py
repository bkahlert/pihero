import json
import sys
from pathlib import Path

import pytest

from pihero_testkit import dump_model_icons as dump

pytestmark = pytest.mark.tier0

macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="needs iconutil and osascript")


class TestParse:
    def test_reads_codes_icon_template_and_symbol(self, declaration):
        types = dump.parse([declaration("com.example.foo", ["Foo1,1", "Foo1,2"], icon="foo.icns", template="SidebarFoo.icns", symbol="foo")])

        assert types["com.example.foo"] == dump.UTType(
            identifier="com.example.foo",
            description="Foo",
            model_codes=("Foo1,1", "Foo1,2"),
            conforms_to=("com.example.device",),
            icon_file="foo.icns",
            template_file="SidebarFoo.icns",
            symbol="foo",
        )

    def test_wraps_a_single_code_and_parent_in_tuples(self):
        types = dump.parse(
            [{"UTTypeIdentifier": "com.example.foo", "UTTypeConformsTo": "public.item", "UTTypeTagSpecification": {"com.apple.device-model-code": "Foo1,1"}}]
        )

        assert types["com.example.foo"].model_codes == ("Foo1,1",)
        assert types["com.example.foo"].conforms_to == ("public.item",)

    def test_reads_a_legacy_top_level_icon_file(self):
        types = dump.parse([{"UTTypeIdentifier": "com.example.foo", "UTTypeIconFile": "foo.icns"}])

        assert types["com.example.foo"].icon_file == "foo.icns"

    def test_keeps_a_type_without_codes(self):
        types = dump.parse([{"UTTypeIdentifier": "com.example.parent", "UTTypeIcons": {"UTTypeIconFile": "parent.icns"}}])

        assert types["com.example.parent"].model_codes == ()

    def test_keeps_the_first_of_duplicate_identifiers(self, declaration):
        types = dump.parse([declaration("com.example.foo", ["Foo1,1"], icon="first.icns"), declaration("com.example.foo", ["Foo1,1"], icon="second.icns")])

        assert types["com.example.foo"].icon_file == "first.icns"


class TestDevices:
    def test_lists_only_types_with_codes(self, declaration):
        types = dump.parse([declaration("com.example.foo", ["Foo1,1"]), {"UTTypeIdentifier": "com.example.parent"}])

        devices = dump.devices(types)

        assert [device.identifier for device in devices] == ["com.example.foo"]

    def test_inherits_icon_template_and_symbol_from_the_nearest_ancestor(self, declaration):
        types = dump.parse(
            [
                declaration("com.example.foo", ["Foo1,1"], conforms=["com.example.parent"]),
                {"UTTypeIdentifier": "com.example.parent", "UTTypeConformsTo": "com.example.grandparent", "UTTypeIcons": {"UTTypeIconFile": "parent.icns"}},
                {
                    "UTTypeIdentifier": "com.example.grandparent",
                    "UTTypeIcons": {
                        "UTTypeIconFile": "grandparent.icns",
                        "_UTTypeTemplateIconFile": "SidebarGrandparent.icns",
                        "UTTypeSymbolName": "grandparent",
                    },
                },
            ]
        )

        (device,) = dump.devices(types)

        assert device.icon_file == "parent.icns"
        assert device.template_file == "SidebarGrandparent.icns"
        assert device.symbol == "grandparent"

    def test_searches_ancestors_breadth_first(self, declaration):
        types = dump.parse(
            [
                declaration("com.example.foo", ["Foo1,1"], conforms=["com.example.a", "com.example.b"]),
                {"UTTypeIdentifier": "com.example.a", "UTTypeConformsTo": "com.example.a-parent"},
                {"UTTypeIdentifier": "com.example.a-parent", "UTTypeIcons": {"UTTypeIconFile": "a-parent.icns"}},
                {"UTTypeIdentifier": "com.example.b", "UTTypeIcons": {"UTTypeIconFile": "b.icns"}},
            ]
        )

        (device,) = dump.devices(types)

        assert device.icon_file == "b.icns"

    def test_leaves_an_unknown_ancestor_alone(self, declaration):
        types = dump.parse([declaration("com.example.foo", ["Foo1,1"], conforms=["com.example.missing"])])

        (device,) = dump.devices(types)

        assert device.icon_file is None

    def test_sorts_by_identifier(self, declaration):
        types = dump.parse([declaration("com.example.b", ["B"]), declaration("com.example.a", ["A"])])

        devices = dump.devices(types)

        assert [device.identifier for device in devices] == ["com.example.a", "com.example.b"]


class TestPixels:
    def test_multiplies_the_side_by_the_scale(self):
        assert dump.pixels("icon_512x512@2x.png") == 1024

    def test_reads_an_unscaled_side(self):
        assert dump.pixels("icon_16x16.png") == 16

    def test_is_none_for_a_template_image(self):
        assert dump.pixels("template_32x32@2x.png") is None


class TestLargest:
    def test_picks_the_most_pixels(self, tmp_path):
        for name in ["icon_512x512.png", "icon_512x512@2x.png", "icon_16x16.png", "template_32x32@2x.png"]:
            (tmp_path / name).write_bytes(b"")

        largest = dump.largest(tmp_path)

        assert largest == tmp_path / "icon_512x512@2x.png"

    def test_is_none_without_icon_images(self, tmp_path):
        (tmp_path / "template_32x32@2x.png").write_bytes(b"")

        assert dump.largest(tmp_path) is None


class TestSidebar:
    def test_prefers_the_template_inside_the_icon(self, tmp_path):
        own = tmp_path / "own.iconset"
        own.mkdir()
        (own / "template_32x32@2x.png").write_bytes(b"")
        template = tmp_path / "Sidebar.iconset"
        template.mkdir()
        (template / "icon_32x32@2x.png").write_bytes(b"")

        assert dump.sidebar(own, template) == own / "template_32x32@2x.png"

    def test_falls_back_to_the_template_icon(self, tmp_path):
        own = tmp_path / "own.iconset"
        own.mkdir()
        (own / "icon_32x32@2x.png").write_bytes(b"")
        template = tmp_path / "Sidebar.iconset"
        template.mkdir()
        (template / "icon_32x32@2x.png").write_bytes(b"")

        assert dump.sidebar(own, template) == template / "icon_32x32@2x.png"

    def test_is_none_without_either(self):
        assert dump.sidebar(None, None) is None


class TestBundles:
    def test_lists_the_root_and_its_nested_bundles(self, tmp_path):
        root = tmp_path / "CoreTypes.bundle"
        (root / "Contents" / "Library" / "CoreTypes-0002.bundle").mkdir(parents=True)
        (root / "Contents" / "Library" / "CoreTypes-0001.bundle").mkdir()
        (root / "Contents" / "Library" / "notes.txt").write_text("")

        bundles = dump.bundles(root)

        assert bundles == [root, root / "Contents" / "Library" / "CoreTypes-0001.bundle", root / "Contents" / "Library" / "CoreTypes-0002.bundle"]

    def test_is_just_the_root_without_a_library(self, tmp_path):
        assert dump.bundles(tmp_path) == [tmp_path]


@macos_only
class TestRenderSymbols:
    def test_writes_square_pngs_and_reports_unknown_names(self, tmp_path, png_header):
        rendered = dump.render_symbols({"circle": tmp_path / "circle.png", "no.such.symbol": tmp_path / "none.png"}, size=64)

        assert rendered == {"circle"}
        assert png_header(tmp_path / "circle.png") == (64, 64, 6)
        assert not (tmp_path / "none.png").exists()


@macos_only
class TestMain:
    def test_exports_icon_sidebar_symbol_and_index(self, tmp_path, declaration, bundle, png_header):
        foo = declaration("com.example.foo", ["Foo1,1", "Foo1,2"], icon="foo.icns", template="SidebarFoo.icns", symbol="circle")
        root = bundle(tmp_path / "CoreTypes.bundle", [foo], {"foo.icns": [16, 32, 64], "SidebarFoo.icns": [16, 64]})
        out = tmp_path / "out"

        code = dump.main([str(out), "--bundle", str(root)])

        assert code == 0
        assert png_header(out / "com.example.foo.png") == (64, 64, 6)
        assert (out / "com.example.foo-sidebar.png").readlink() == Path("sidebar/SidebarFoo.png")
        assert png_header(out / "sidebar" / "SidebarFoo.png") == (64, 64, 6)
        assert (out / "com.example.foo-symbol.png").readlink() == Path("symbols/circle.png")
        assert png_header(out / "symbols" / "circle.png") == (1024, 1024, 6)
        assert json.loads((out / "index.json").read_text()) == {
            "com.example.foo": {
                "description": "Foo",
                "model_codes": ["Foo1,1", "Foo1,2"],
                "icon": "com.example.foo.png",
                "sidebar": "sidebar/SidebarFoo.png",
                "symbol": "symbols/circle.png",
                "symbol_name": "circle",
            }
        }

    def test_links_a_symbol_svg_that_is_already_there(self, tmp_path, declaration, bundle):
        root = bundle(tmp_path / "CoreTypes.bundle", [declaration("com.example.foo", ["Foo1,1"], symbol="circle")], {})
        out = tmp_path / "out"
        (out / "symbols").mkdir(parents=True)
        (out / "symbols" / "circle.svg").write_text("<svg/>")

        dump.main([str(out), "--bundle", str(root)])

        assert (out / "com.example.foo-symbol.svg").readlink() == Path("symbols/circle.svg")
        assert sorted(path.name for path in (out / "symbols").iterdir()) == ["circle.svg"]
        assert json.loads((out / "index.json").read_text())["com.example.foo"]["symbol"] == "symbols/circle.svg"

    def test_shares_one_sidebar_file_between_types(self, tmp_path, declaration, bundle):
        foo = declaration("com.example.foo", ["Foo1,1"], template="SidebarFoo.icns")
        bar = declaration("com.example.bar", ["Bar1,1"], template="SidebarFoo.icns")
        root = bundle(tmp_path / "CoreTypes.bundle", [foo, bar], {"SidebarFoo.icns": [64]})
        out = tmp_path / "out"

        dump.main([str(out), "--bundle", str(root)])

        assert sorted(path.name for path in (out / "sidebar").iterdir()) == ["SidebarFoo.png"]
        assert (out / "com.example.foo-sidebar.png").readlink() == (out / "com.example.bar-sidebar.png").readlink()

    def test_replaces_the_links_of_an_earlier_run(self, tmp_path, declaration, bundle):
        foo = declaration("com.example.foo", ["Foo1,1"], template="SidebarFoo.icns", symbol="circle")
        root = bundle(tmp_path / "CoreTypes.bundle", [foo], {"SidebarFoo.icns": [64]})
        out = tmp_path / "out"
        dump.main([str(out), "--bundle", str(root)])
        (out / "symbols" / "circle.svg").write_text("<svg/>")

        dump.main([str(out), "--bundle", str(root)])

        assert (out / "com.example.foo-sidebar.png").readlink() == Path("sidebar/SidebarFoo.png")
        assert (out / "com.example.foo-symbol.svg").readlink() == Path("symbols/circle.svg")
        assert not (out / "com.example.foo-symbol.png").exists()

    def test_finds_declarations_and_resources_in_nested_bundles(self, tmp_path, declaration, bundle, png_header):
        parent = {"UTTypeIdentifier": "com.example.parent", "UTTypeIcons": {"UTTypeIconFile": "parent.icns"}}
        root = bundle(tmp_path / "CoreTypes.bundle", [parent], {"parent.icns": [16]})
        bundle(root / "Contents" / "Library" / "CoreTypes-0001.bundle", [declaration("com.example.foo", ["Foo1,1"], conforms=["com.example.parent"])], {})
        out = tmp_path / "out"

        dump.main([str(out), "--bundle", str(root)])

        assert png_header(out / "com.example.foo.png") == (16, 16, 6)

    def test_records_missing_images_as_null(self, tmp_path, declaration, bundle):
        root = bundle(tmp_path / "CoreTypes.bundle", [declaration("com.example.foo", ["Foo1,1"], symbol="no.such.symbol")], {})
        out = tmp_path / "out"

        dump.main([str(out), "--bundle", str(root)])

        assert json.loads((out / "index.json").read_text())["com.example.foo"] == {
            "description": "Foo",
            "model_codes": ["Foo1,1"],
            "icon": None,
            "sidebar": None,
            "symbol": None,
            "symbol_name": "no.such.symbol",
        }
        assert sorted(path.name for path in out.iterdir()) == ["index.json"]

    def test_restricts_to_the_given_identifiers(self, tmp_path, declaration, bundle):
        declarations = [declaration("com.example.foo", ["Foo1,1"], icon="foo.icns"), declaration("com.example.bar", ["Bar1,1"], icon="foo.icns")]
        root = bundle(tmp_path / "CoreTypes.bundle", declarations, {"foo.icns": [16]})
        out = tmp_path / "out"

        dump.main([str(out), "com.example.bar", "--bundle", str(root)])

        assert sorted(path.name for path in out.iterdir()) == ["com.example.bar.png", "index.json"]

    def test_refuses_an_unknown_identifier(self, tmp_path, declaration, bundle):
        root = bundle(tmp_path / "CoreTypes.bundle", [declaration("com.example.foo", ["Foo1,1"])], {})

        with pytest.raises(SystemExit, match="com.example.nope"):
            dump.main([str(tmp_path / "out"), "com.example.nope", "--bundle", str(root)])

    def test_expands_a_literal_tilde_in_the_output_directory(self, tmp_path, declaration, bundle, monkeypatch):
        root = bundle(tmp_path / "CoreTypes.bundle", [declaration("com.example.foo", ["Foo1,1"])], {})
        monkeypatch.setenv("HOME", str(tmp_path))

        dump.main(["~/out", "--bundle", str(root)])

        assert (tmp_path / "out" / "index.json").is_file()
