import plistlib
import struct
import subprocess
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def declaration() -> Callable[..., dict]:
    """A CoreTypes type declaration with model codes, optionally with icon, template icon, symbol, and parents."""

    def build(
        identifier: str,
        codes: list[str],
        icon: str | None = None,
        template: str | None = None,
        symbol: str | None = None,
        conforms: list[str] | None = None,
    ) -> dict:
        images = {key: value for key, value in [("UTTypeIconFile", icon), ("_UTTypeTemplateIconFile", template), ("UTTypeSymbolName", symbol)] if value}
        return {
            "UTTypeIdentifier": identifier,
            "UTTypeDescription": identifier.rsplit(".", 1)[-1].capitalize(),
            "UTTypeConformsTo": conforms or ["com.example.device"],
            "UTTypeTagSpecification": {"com.apple.device-model-code": codes},
            **({"UTTypeIcons": images} if images else {}),
        }

    return build


@pytest.fixture
def bundle(png) -> Callable[[Path, list[dict], dict[str, list[int]]], Path]:
    """A bundle directory with the declarations in its Info.plist and an icns resource per name, built with iconutil."""

    def build(root: Path, declarations: list[dict], icns: dict[str, list[int]]) -> Path:
        resources = root / "Contents" / "Resources"
        resources.mkdir(parents=True)
        with (root / "Contents" / "Info.plist").open("wb") as info:
            plistlib.dump({"CFBundleIdentifier": root.stem, "UTExportedTypeDeclarations": declarations}, info)
        for name, sizes in icns.items():
            iconset = root.parent / f"{name}.iconset"
            iconset.mkdir()
            for size in sizes:
                side = size // 2 if size > 32 else size
                scale = "@2x" if size > 32 else ""
                (iconset / f"icon_{side}x{side}{scale}.png").write_bytes(png(size))
            subprocess.run(["iconutil", "-c", "icns", "-o", resources / name, iconset], check=True)
        return root

    return build


@pytest.fixture
def png() -> Callable[..., bytes]:
    """A square RGBA PNG, solid red unless a pixel function maps (x, y) to (r, g, b, a)."""

    def build(size: int, pixel: Callable[[int, int], tuple[int, int, int, int]] = lambda x, y: (200, 40, 40, 255)) -> bytes:
        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(size)) for y in range(size))
        header = chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        return b"\x89PNG\r\n\x1a\n" + header + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")

    return build


@pytest.fixture
def png_header() -> Callable[[Path], tuple[int, int, int]]:
    """Reads (width, height, colour type) from a PNG; colour type 3 is a palette, 6 is RGBA."""

    def read(path: Path) -> tuple[int, int, int]:
        header = path.read_bytes()[:26]
        assert header[:8] == b"\x89PNG\r\n\x1a\n"
        width, height, _, colour = struct.unpack(">IIBB", header[16:26])
        return width, height, colour

    return read
