import re
import shutil
import sys
from pathlib import Path

import pytest

from pihero_testkit import update_model_icons as update

pytestmark = pytest.mark.tier0

macos_with_pngquant = pytest.mark.skipif(sys.platform != "darwin" or shutil.which("pngquant") is None, reason="needs iconutil and pngquant")

DEVICES_README = Path("devices/README.md")


class TestModels:
    def test_are_exactly_the_icons_the_devices_readme_shows(self):
        pictured = set(re.findall(r"\(\.\./docs/models/(com\.apple\.[\w.-]+)\.png\)", DEVICES_README.read_text()))

        assert pictured == set(update.MODELS)


class TestUpdate:
    def test_refuses_to_run_without_pngquant(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: None)

        with pytest.raises(SystemExit, match="pngquant"):
            update.update(["com.example.foo"], tmp_path)


@macos_with_pngquant
class TestQuantize:
    def test_rewrites_a_truecolour_png_as_a_palette(self, tmp_path, png, png_header):
        image = tmp_path / "gradient.png"
        image.write_bytes(png(128, lambda x, y: (x * 2, y * 2, 128, 255)))
        before = image.stat().st_size

        update.quantize([image])

        assert png_header(image) == (128, 128, 3)
        assert image.stat().st_size < before

    def test_accepts_no_files(self):
        update.quantize([])


@macos_with_pngquant
class TestMain:
    def test_places_icons_sidebars_and_links_and_nothing_else(self, tmp_path, declaration, bundle, png_header):
        foo = declaration("com.example.foo", ["Foo1,1"], icon="foo.icns", template="SidebarFoo.icns", symbol="circle")
        root = bundle(tmp_path / "CoreTypes.bundle", [foo], {"foo.icns": [16, 32, 64], "SidebarFoo.icns": [16, 64]})
        docs = tmp_path / "docs"

        code = update.main(["--docs", str(docs), "--bundle", str(root), "com.example.foo"])

        assert code == 0
        assert sorted(path.relative_to(docs).as_posix() for path in docs.rglob("*")) == [
            "com.example.foo-sidebar.png",
            "com.example.foo.png",
            "sidebar",
            "sidebar/SidebarFoo.png",
        ]
        assert png_header(docs / "com.example.foo.png")[:2] == (64, 64)
        assert (docs / "com.example.foo-sidebar.png").readlink() == Path("sidebar/SidebarFoo.png")

    def test_removes_what_it_did_not_write_but_keeps_dotfiles(self, tmp_path, declaration, bundle):
        root = bundle(tmp_path / "CoreTypes.bundle", [declaration("com.example.foo", ["Foo1,1"], icon="foo.icns")], {"foo.icns": [16]})
        docs = tmp_path / "docs"
        (docs / "symbols").mkdir(parents=True)
        (docs / "symbols" / "circle.png").write_bytes(b"")
        (docs / "com.example.foo-symbol.png").symlink_to("symbols/circle.png")
        (docs / "com.example.old.png").write_bytes(b"")
        (docs / "index.json").write_text("{}")
        (docs / ".DS_Store").write_bytes(b"")

        update.main(["--docs", str(docs), "--bundle", str(root), "com.example.foo"])

        assert sorted(path.name for path in docs.iterdir()) == [".DS_Store", "com.example.foo.png"]

    def test_refuses_an_unknown_identifier(self, tmp_path, declaration, bundle):
        root = bundle(tmp_path / "CoreTypes.bundle", [declaration("com.example.foo", ["Foo1,1"])], {})

        with pytest.raises(SystemExit, match="com.example.nope"):
            update.main(["--docs", str(tmp_path / "docs"), "--bundle", str(root), "com.example.nope"])
