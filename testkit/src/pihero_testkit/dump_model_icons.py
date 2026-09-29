"""Exports the Finder icons of every device type declared in CoreTypes.bundle.

For each type with a ``com.apple.device-model-code`` tag: the realistic icon as ``<identifier>.png``, the sidebar
template (64 px) as ``sidebar/<its own name>.png`` linked from ``<identifier>-sidebar.png``, the SF Symbol (1024 px)
as ``symbols/<symbol name>.png`` linked from ``<identifier>-symbol.png``, and ``index.json`` mapping identifiers to
their model codes and files. A ``symbols/<symbol name>.svg`` that is already there, exported from SF Symbols.app, is
linked instead of rendering a PNG. A type without images of its own takes them from the nearest type it conforms to,
as Finder does.

macOS only: converts icns files with iconutil and renders symbols with osascript.
"""

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from .flash import say

BUNDLE = Path("/System/Library/CoreServices/CoreTypes.bundle")
SYMBOL_SIZE = 1024
SIDEBAR = "32x32@2x.png"
ICON = re.compile(r"^icon_(?P<side>\d+)x(?P=side)(?:@(?P<scale>\d)x)?\.png$")
# JavaScript for Automation. NSImage's symbol configuration API crashes under the bridge, so the symbol is drawn at
# its own aspect ratio into a bitmap of the requested size instead.
RENDER = r"""
ObjC.import('AppKit');
function run(argv) {
  const size = parseInt(argv[0], 10);
  const results = [];
  for (const job of argv.slice(1)) {
    const [name, out] = job.split('\t');
    const image = $.NSImage.imageWithSystemSymbolNameAccessibilityDescription(name, $());
    if (image.isNil()) { results.push('missing\t' + name); continue; }
    const natural = image.size;
    const scale = Math.min(size / natural.width, size / natural.height);
    const width = natural.width * scale, height = natural.height * scale;
    const rep = $.NSBitmapImageRep.alloc
      .initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(
        null, size, size, 8, 4, true, false, $.NSCalibratedRGBColorSpace, 0, 0);
    $.NSGraphicsContext.saveGraphicsState;
    $.NSGraphicsContext.setCurrentContext($.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep));
    image.drawInRectFromRectOperationFraction(
      $.NSMakeRect((size - width) / 2, (size - height) / 2, width, height), $.NSZeroRect, $.NSCompositingOperationSourceOver, 1.0);
    $.NSGraphicsContext.restoreGraphicsState;
    const png = rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $());
    results.push((png.writeToFileAtomically(out, true) ? 'ok' : 'failed') + '\t' + name);
  }
  return results.join('\n');
}
"""


@dataclass(frozen=True)
class UTType:
    identifier: str
    description: str | None
    model_codes: tuple[str, ...]
    conforms_to: tuple[str, ...]
    icon_file: str | None
    template_file: str | None
    symbol: str | None


def parse(declarations: Iterable[dict]) -> dict[str, UTType]:
    """Returns the declared types by identifier; of duplicate identifiers the first declaration wins."""
    types: dict[str, UTType] = {}
    for declaration in declarations:
        images = declaration.get("UTTypeIcons", {})
        utype = UTType(
            identifier=declaration["UTTypeIdentifier"],
            description=declaration.get("UTTypeDescription"),
            model_codes=strings(declaration.get("UTTypeTagSpecification", {}).get("com.apple.device-model-code")),
            conforms_to=strings(declaration.get("UTTypeConformsTo")),
            icon_file=images.get("UTTypeIconFile") or declaration.get("UTTypeIconFile"),
            template_file=images.get("_UTTypeTemplateIconFile") or images.get("UTTypeTemplateIconFile"),
            symbol=images.get("UTTypeSymbolName"),
        )
        types.setdefault(utype.identifier, utype)
    return types


def strings(value: str | list[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return (value,) if isinstance(value, str) else tuple(value)


def devices(types: dict[str, UTType]) -> list[UTType]:
    """Returns the types with model codes sorted by identifier, each missing image taken from its nearest ancestor."""
    return [inherit(utype, types) for _, utype in sorted(types.items()) if utype.model_codes]


def inherit(utype: UTType, types: dict[str, UTType]) -> UTType:
    for attribute in ("icon_file", "template_file", "symbol"):
        if getattr(utype, attribute) is None:
            utype = replace(utype, **{attribute: nearest(utype, types, attribute)})
    return utype


def nearest(utype: UTType, types: dict[str, UTType], attribute: str) -> str | None:
    queue = deque(utype.conforms_to)
    seen: set[str] = set()
    while queue:
        identifier = queue.popleft()
        if identifier in seen or identifier not in types:
            continue
        seen.add(identifier)
        if (value := getattr(types[identifier], attribute)) is not None:
            return value
        queue.extend(types[identifier].conforms_to)
    return None


def bundles(root: Path) -> list[Path]:
    """Returns the bundle followed by the bundles nested in its Contents/Library, sorted by name."""
    library = root / "Contents" / "Library"
    nested = sorted(path for path in library.iterdir() if path.suffix == ".bundle") if library.is_dir() else []
    return [root, *nested]


def read(root: Path) -> dict[str, UTType]:
    """Returns the types declared by the bundle and its nested bundles."""
    declarations: list[dict] = []
    for bundle in bundles(root):
        info = bundle / "Contents" / "Info.plist"
        if info.is_file():
            with info.open("rb") as file:
                declarations.extend(plistlib.load(file).get("UTExportedTypeDeclarations", []))
    return parse(declarations)


def resource(search: list[Path], name: str) -> Path | None:
    return next((path for bundle in search if (path := bundle / "Contents" / "Resources" / name).is_file()), None)


def iconset(icns: Path, into: Path) -> Path:
    """Converts the icns file into an iconset directory under into, unless one is there already."""
    target = into / f"{icns.stem}.iconset"
    if not target.exists():
        subprocess.run(["iconutil", "-c", "iconset", "-o", target, icns], check=True, capture_output=True)
    return target


def pixels(name: str) -> int | None:
    """Returns the pixel width of an iconset image from its name, or None for template and unknown images."""
    match = ICON.match(name)
    return int(match["side"]) * int(match["scale"] or 1) if match else None


def largest(directory: Path) -> Path | None:
    images = [(pixels(path.name), path) for path in directory.iterdir()]
    return max(((size, path) for size, path in images if size), default=(0, None))[1]


def sidebar(own: Path | None, template: Path | None) -> Path | None:
    """Returns the 64 px sidebar image: the template inside the icon's own iconset, else the template icon's."""
    for candidate in [own and own / f"template_{SIDEBAR}", template and template / f"icon_{SIDEBAR}"]:
        if candidate and candidate.is_file():
            return candidate
    return None


def render_symbols(jobs: dict[str, Path], size: int = SYMBOL_SIZE) -> set[str]:
    """Renders each SF Symbol into its PNG, size by size pixels. Returns the names macOS knows."""
    if not jobs:
        return set()
    command = ["osascript", "-l", "JavaScript", "-e", RENDER, str(size), *[f"{name}\t{path}" for name, path in jobs.items()]]
    out = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    return {name for status, name in (line.split("\t") for line in out.splitlines() if line) if status == "ok"}


def export(root: Path, out: Path, only: Iterable[str] = ()) -> dict[str, dict]:
    """Writes the icons of the bundle's device types, or of those in only, into out. Returns the index written."""
    types = devices(read(root))
    if wanted := set(only):
        if unknown := sorted(wanted - {utype.identifier for utype in types}):
            raise SystemExit(f"not a device type in {root}: {', '.join(unknown)}")
        types = [utype for utype in types if utype.identifier in wanted]
    search = bundles(root)
    out.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)

        def converted(name: str | None) -> Path | None:
            icns = resource(search, name) if name and name.endswith(".icns") else None
            return iconset(icns, work) if icns else None

        symbols = symbol_files(out, {utype.symbol for utype in types if utype.symbol}, work)
        for utype in types:
            own = converted(utype.icon_file)
            entry: dict = {
                "description": utype.description,
                "model_codes": list(utype.model_codes),
                "icon": None,
                "sidebar": None,
                "symbol": None,
                "symbol_name": utype.symbol,
            }
            if own and (image := largest(own)):
                entry["icon"] = copy(image, out / f"{utype.identifier}.png")
            if image := sidebar(own, converted(utype.template_file)):
                shared = copy_once(image, out / "sidebar" / f"{image.parent.stem}.png")
                entry["sidebar"] = link(shared, out / f"{utype.identifier}-sidebar.png")
            for stale in out.glob(f"{utype.identifier}-symbol.*"):
                stale.unlink()
            if shared := symbols.get(utype.symbol or ""):
                entry["symbol"] = link(shared, out / f"{utype.identifier}-symbol{shared.suffix}")
            index[utype.identifier] = entry
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return index


def symbol_files(out: Path, names: set[str], work: Path) -> dict[str, Path]:
    """Returns the file under out/symbols for each symbol name: an SVG already there, else a PNG rendered now."""
    files = {name: out / "symbols" / f"{name}.svg" for name in names if (out / "symbols" / f"{name}.svg").is_file()}
    (work / "symbols").mkdir()
    for name in render_symbols({name: work / "symbols" / f"{name}.png" for name in names - set(files)}):
        files[name] = copy_once(work / "symbols" / f"{name}.png", out / "symbols" / f"{name}.png", replace=True)
    return files


def copy(image: Path, target: Path) -> str:
    shutil.copyfile(image, target)
    return target.name


def copy_once(image: Path, target: Path, replace: bool = False) -> Path:
    if replace or not target.exists():
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(image, target)
    return target


def link(target: Path, name: Path) -> str:
    """Points the symbolic link name at target, replacing whatever was there. Returns the relative link text."""
    relative = target.relative_to(name.parent)
    if name.is_symlink() or name.exists():
        name.unlink()
    os.symlink(relative, name)
    return relative.as_posix()


def directory(value: str) -> Path:
    """Returns the path with a leading ~ expanded, which a quoted make variable leaves for us to do."""
    return Path(value).expanduser()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Export the Finder icons of the device types in CoreTypes.bundle.")
    parser.add_argument("out", type=directory, help="directory for the PNGs and index.json; created if missing")
    parser.add_argument("identifiers", nargs="*", help="type identifiers such as com.apple.airport-express; all device types when empty")
    parser.add_argument("--bundle", type=Path, default=BUNDLE, help=f"bundle to read (default: {BUNDLE})")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("icons is macOS only", file=sys.stderr)
        return 2
    index = export(args.bundle, args.out, args.identifiers)
    counts = {kind: sum(1 for entry in index.values() if entry[kind]) for kind in ("icon", "sidebar", "symbol")}
    say(f"{len(index)} device types into {args.out}: {counts['icon']} icons, {counts['sidebar']} sidebars, {counts['symbol']} symbols")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
