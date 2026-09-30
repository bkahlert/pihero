#!/usr/bin/env python3
"""Which model codes give which Finder icon and sidebar icon, laid out for picking in Finder.

Usage: python3 experiments/model-icons/dump_model_icons.py [OUT]        default OUT: out/ next to the script

  icons/<icns name>.png                the largest image of the icns, written once
  sidebar/<icns name>.png              64 px sidebar template, written once
  by-sidebar/<sidebar>/                folder whose icon is the sidebar image, kept in a hidden Icon file inside
  by-sidebar/<sidebar>/<icon>.png      -> ../../icons/<icon>.png, one per icon that comes with the sidebar
  index.json                           "sidebars": sidebar -> icons -> model codes and the types behind them;
                                       "dropped": the codes left out, by reason

Every com.apple.device-model-code declared in CoreTypes.bundle is resolved the way Finder resolves the model= of a
_device-info._tcp record: LaunchServices names the preferred type, which settles the codes several types claim. The
icon and sidebar template of that type, its own or the nearest one it conforms to, place the code; codes whose type
lacks either are left out and counted.

OUT is cleared first, but only when it is missing, empty, or holds an earlier dump. macOS only: iconutil and osascript.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

BUNDLE = Path("/System/Library/CoreServices/CoreTypes.bundle")
DEFAULT_OUT = Path(__file__).resolve().parent / "out"
SIDEBAR = "32x32@2x.png"
ICON = re.compile(r"^icon_(?P<side>\d+)x(?P=side)(?:@(?P<scale>\d)x)?\.png$")
OURS = ("index.json", "icons", "sidebar", "by-sidebar")
# JavaScript for Automation: the preferred type of each model code, as Finder asks LaunchServices for it. Finder only
# takes devices: a display's code, whose type conforms to public.display, gets a question mark in Network.
RESOLVE = r"""
ObjC.import('CoreServices');
function run(argv) {
  return argv.map(code => {
    const ref = $.UTTypeCreatePreferredIdentifierForTag($('com.apple.device-model-code'), $(code), $('public.device'));
    return code + '\t' + ObjC.castRefToObject(ref).js;
  }).join('\n');
}
"""
# JavaScript for Automation: gives each folder an image as its icon, as pasting one into Finder's Get Info does. The
# sidebar templates are black shapes, so they are tinted grey first to show in dark and light appearance alike.
FOLDER_ICON = r"""
ObjC.import('AppKit');
function tinted(path) {
  const image = $.NSImage.alloc.initWithContentsOfFile(path);
  const size = image.size;
  const rep = $.NSBitmapImageRep.alloc
    .initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(
      null, size.width, size.height, 8, 4, true, false, $.NSCalibratedRGBColorSpace, 0, 0);
  const rect = $.NSMakeRect(0, 0, size.width, size.height);
  $.NSGraphicsContext.saveGraphicsState;
  $.NSGraphicsContext.setCurrentContext($.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep));
  image.drawInRectFromRectOperationFraction(rect, $.NSZeroRect, $.NSCompositingOperationSourceOver, 1.0);
  $.NSColor.systemGrayColor.set;
  $.NSRectFillUsingOperation(rect, $.NSCompositingOperationSourceIn);
  $.NSGraphicsContext.restoreGraphicsState;
  const result = $.NSImage.alloc.initWithSize(size);
  result.addRepresentation(rep);
  return result;
}
function run(argv) {
  const workspace = $.NSWorkspace.sharedWorkspace;
  return argv.map(job => {
    const [image, folder] = job.split('\t');
    const ok = workspace.setIconForFileOptions(tinted(image), folder, 0);
    return (ok ? 'ok' : 'failed') + '\t' + folder;
  }).join('\n');
}
"""


@dataclass(frozen=True)
class UTType:
    identifier: str
    model_codes: tuple[str, ...]
    conforms_to: tuple[str, ...]
    icon_file: str | None
    template_file: str | None


def strings(value) -> tuple[str, ...]:
    if value is None:
        return ()
    return (value,) if isinstance(value, str) else tuple(value)


def bundles(root: Path) -> list[Path]:
    library = root / "Contents" / "Library"
    nested = sorted(path for path in library.iterdir() if path.suffix == ".bundle") if library.is_dir() else []
    return [root, *nested]


def read(root: Path) -> dict[str, UTType]:
    """Returns the types declared by the bundle and its nested bundles; of duplicate identifiers the first wins."""
    types: dict[str, UTType] = {}
    for bundle in bundles(root):
        info = bundle / "Contents" / "Info.plist"
        if not info.is_file():
            continue
        with info.open("rb") as file:
            declarations = plistlib.load(file).get("UTExportedTypeDeclarations", [])
        for declaration in declarations:
            images = declaration.get("UTTypeIcons", {})
            utype = UTType(
                identifier=declaration["UTTypeIdentifier"],
                model_codes=strings(declaration.get("UTTypeTagSpecification", {}).get("com.apple.device-model-code")),
                conforms_to=strings(declaration.get("UTTypeConformsTo")),
                icon_file=images.get("UTTypeIconFile") or declaration.get("UTTypeIconFile"),
                template_file=images.get("_UTTypeTemplateIconFile") or images.get("UTTypeTemplateIconFile"),
            )
            types.setdefault(utype.identifier, utype)
    return types


def inherit(utype: UTType, types: dict[str, UTType]) -> UTType:
    """Fills the missing icon and template from the nearest type it conforms to, as Finder does."""
    queue, seen = deque(utype.conforms_to), set()
    while queue and (utype.icon_file is None or utype.template_file is None):
        identifier = queue.popleft()
        if identifier in seen or identifier not in types:
            continue
        seen.add(identifier)
        parent = types[identifier]
        for attribute in ("icon_file", "template_file"):
            if getattr(utype, attribute) is None and getattr(parent, attribute) is not None:
                utype = replace(utype, **{attribute: getattr(parent, attribute)})
        queue.extend(parent.conforms_to)
    return utype


def resolve(codes: list[str]) -> dict[str, str]:
    """Returns the preferred type identifier of each model code; dyn.* for codes no type claims."""
    out = subprocess.run(["osascript", "-l", "JavaScript", "-e", RESOLVE, *codes], check=True, capture_output=True, text=True).stdout
    return dict(line.split("\t") for line in out.splitlines() if line)


def folder_icons(jobs: dict[Path, Path]) -> None:
    """Gives each folder its image as icon. Finder keeps it in a hidden file inside, named Icon plus a carriage return."""
    command = ["osascript", "-l", "JavaScript", "-e", FOLDER_ICON, *[f"{image.resolve()}\t{folder.resolve()}" for folder, image in jobs.items()]]
    out = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    if failed := [line.split("\t")[1] for line in out.splitlines() if line.startswith("failed")]:
        print(f"no folder icon for {', '.join(failed)}", file=sys.stderr)


def clear(out: Path) -> None:
    """Empties OUT. Refuses a directory that is neither empty nor an earlier dump."""
    if not out.exists():
        out.mkdir(parents=True)
        return
    if not out.is_dir():
        sys.exit(f"{out} is not a directory")
    contents = [path for path in out.iterdir() if path.name != ".DS_Store"]
    if not all(path.name in OURS for path in contents):
        sys.exit(f"{out} is not empty and not an earlier dump; refusing to clear it")
    for path in contents:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def resource(search: list[Path], name: str) -> Path | None:
    return next((path for bundle in search if (path := bundle / "Contents" / "Resources" / name).is_file()), None)


def iconset(icns: Path, work: Path) -> Path:
    target = work / f"{icns.stem}.iconset"
    if not target.exists():
        subprocess.run(["iconutil", "-c", "iconset", "-o", target, icns], check=True, stdout=subprocess.DEVNULL)
    return target


def pixels(name: str) -> int:
    match = ICON.match(name)
    return int(match["side"]) * int(match["scale"] or 1) if match else 0


def largest(folder: Path) -> Path | None:
    images = [path for path in folder.iterdir() if pixels(path.name)]
    return max(images, key=lambda path: pixels(path.name), default=None)


def sidebar(own: Path | None, template: Path | None) -> Path | None:
    for candidate in [own and own / f"template_{SIDEBAR}", template and template / f"icon_{SIDEBAR}"]:
        if candidate and candidate.is_file():
            return candidate
    return None


def copy_once(image: Path, target: Path) -> Path:
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, target)
    return target


def link(target: Path, name: Path) -> None:
    if not name.is_symlink():
        name.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(target, name.parent), name)


def main(argv: list[str]) -> int:
    if sys.platform != "darwin":
        sys.exit("macOS only: needs iconutil and osascript")
    out = Path(argv[0]).expanduser() if argv else DEFAULT_OUT
    types = read(BUNDLE)
    search = bundles(BUNDLE)
    codes = sorted({code for utype in types.values() for code in utype.model_codes})
    winners = resolve(codes)
    dropped: dict[str, list[str]] = {"unknown type": [], "no icon": [], "no sidebar": []}
    index: dict[str, dict] = {}
    folders: dict[Path, Path] = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        chosen = {identifier: inherit(types[identifier], types) for identifier in set(winners.values()) if identifier in types}
        needed = {name for utype in chosen.values() for name in (utype.icon_file, utype.template_file) if name and name.endswith(".icns")}
        found = {name: path for name in needed if (path := resource(search, name))}
        with ThreadPoolExecutor() as pool:
            sets = dict(zip(found, pool.map(lambda icns: iconset(icns, work), found.values())))
        clear(out)
        for code in codes:
            utype = chosen.get(winners[code])
            if utype is None:
                dropped["unknown type"].append(code)
                continue
            own = sets.get(utype.icon_file)
            icon = own and largest(own)
            if icon is None:
                dropped["no icon"].append(code)
                continue
            template = sidebar(own, sets.get(utype.template_file))
            if template is None:
                dropped["no sidebar"].append(code)
                continue
            icon_file = copy_once(icon, out / "icons" / f"{own.stem}.png")
            sidebar_file = copy_once(template, out / "sidebar" / f"{template.parent.stem}.png")
            folder = out / "by-sidebar" / sidebar_file.stem
            folders[folder] = sidebar_file
            link(icon_file, folder / f"{icon_file.stem}.png")
            group = index.setdefault(sidebar_file.stem, {"sidebar": sidebar_file.relative_to(out).as_posix(), "icons": {}})
            entry = group["icons"].setdefault(icon_file.stem, {"icon": icon_file.relative_to(out).as_posix(), "types": [], "codes": []})
            if utype.identifier not in entry["types"]:
                entry["types"].append(utype.identifier)
            entry["codes"].append(code)
    folder_icons(folders)
    for group in index.values():
        group["icons"] = dict(sorted(group["icons"].items()))
    (out / "index.json").write_text(json.dumps({"sidebars": dict(sorted(index.items())), "dropped": dropped}, indent=2) + "\n")
    placed = sum(len(entry["codes"]) for group in index.values() for entry in group["icons"].values())
    icons = sum(len(group["icons"]) for group in index.values())
    print(f"{len(codes)} model codes: {placed} placed under {len(index)} sidebars and {icons} icons in {out}; "
          + ", ".join(f"{len(names)} {reason}" for reason, names in dropped.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
