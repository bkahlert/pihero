#!/usr/bin/env python3
"""Refreshes docs/models: the icon and sidebar template of every device type the READMEs picture.

Usage: python3 experiments/model-icons/update_docs_models.py

For each type in MODELS: docs/models/<identifier>.png, the sidebar image as docs/models/sidebar/<icns name>.png, and
docs/models/<identifier>-sidebar.png linking to it. The PNGs are quantised to 8-bit palettes with pngquant
(brew install pngquant) to keep the repository small; files no longer produced are removed. macOS only: iconutil.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import dump_model_icons as dump

DOCS = Path(__file__).resolve().parents[2] / "docs" / "models"
MODELS = (
    "com.apple.airport-express",
    "com.apple.airport",
    "com.apple.time-capsule",
    "com.apple.macmini-2018",
    "com.apple.macmini-2020",
    "com.apple.macpro-cylinder",
    "com.apple.macpro-firewire",
    "com.apple.macpro-2019",
    "com.apple.macpro-2019-rackmount",
    "com.apple.xserve-xeon",
)
# pngquant's exit codes for a file left as it was: 98 when the palette version would be larger, 99 when below --quality.
SKIPPED = {98, 99}


def images(utype: dump.UTType, search: list[Path], work: Path) -> tuple[Path, Path] | None:
    """Returns the largest icon image and the sidebar template of the type, or None when either is missing."""
    icns = dump.resource(search, utype.icon_file) if utype.icon_file else None
    own = dump.iconset(icns, work) if icns else None
    template_icns = dump.resource(search, utype.template_file) if utype.template_file else None
    template = dump.sidebar(own, dump.iconset(template_icns, work) if template_icns else None)
    icon = dump.largest(own) if own else None
    return (icon, template) if icon and template else None


def quantize(files: list[Path]) -> None:
    """Rewrites each PNG as an 8-bit palette image, leaving those alone that would not get smaller."""
    run = subprocess.run(["pngquant", "--force", "--skip-if-larger", "--strip", "--ext", ".png", *files], capture_output=True, text=True)
    if run.returncode and run.returncode not in SKIPPED:
        sys.exit(f"pngquant failed ({run.returncode}): {run.stderr.strip()}")


def prune(docs: Path, keep: set[Path]) -> None:
    """Removes the files and links under docs that are not in keep, except dotfiles, then the directories left empty."""
    for path in sorted(docs.rglob("*"), reverse=True):
        if path.name.startswith("."):
            continue
        if path.is_dir() and not path.is_symlink():
            if not any(path.iterdir()):
                path.rmdir()
        elif path not in keep:
            path.unlink()


def main() -> int:
    if sys.platform != "darwin":
        sys.exit("macOS only: needs iconutil")
    if shutil.which("pngquant") is None:
        sys.exit("pngquant not found; install it with: brew install pngquant")
    types = dump.read(dump.BUNDLE)
    search = dump.bundles(dump.BUNDLE)
    if unknown := [identifier for identifier in MODELS if identifier not in types]:
        sys.exit(f"not declared in {dump.BUNDLE}: {', '.join(unknown)}")
    staged: dict[Path, Path] = {}
    links: dict[Path, Path] = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for identifier in MODELS:
            found = images(dump.inherit(types[identifier], types), search, work)
            if found is None:
                sys.exit(f"{identifier}: no icon or no sidebar template in {dump.BUNDLE}")
            icon, template = found
            sidebar = DOCS / "sidebar" / f"{template.parent.stem}.png"
            staged[DOCS / f"{identifier}.png"] = icon
            staged[sidebar] = template
            links[DOCS / f"{identifier}-sidebar.png"] = sidebar
        copies = {target: work / "staged" / target.relative_to(DOCS) for target in staged}
        for target, copy in copies.items():
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staged[target], copy)
        quantize(list(copies.values()))
        for target, copy in copies.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(copy, target)
    for name, target in links.items():
        if name.is_symlink() or name.exists():
            name.unlink()
        dump.link(target, name)
    prune(DOCS, set(staged) | set(links))
    print(f"{len(staged)} files and {len(links)} links in {DOCS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
