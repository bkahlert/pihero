"""Refreshes docs/models: the realistic icon and sidebar template of every device type the documentation pictures.

macOS only. Dumps the types with dump_model_icons into a temporary directory, quantises the PNGs to 8-bit palettes
with pngquant, and replaces the contents of docs/models with the icons, the sidebar images under ``sidebar/``, and the
``<identifier>-sidebar.png`` links. Symbols and the index stay out, and files no longer produced are removed.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

from . import dump_model_icons
from .flash import say

DOCS = Path("docs/models")
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


def update(identifiers: Iterable[str], docs: Path, bundle: Path = dump_model_icons.BUNDLE) -> list[Path]:
    """Replaces the contents of docs with the quantised icons and sidebars of the identifiers. Returns what it wrote."""
    if shutil.which("pngquant") is None:
        raise SystemExit("pngquant not found; install it with: brew bundle")
    with tempfile.TemporaryDirectory() as tmp:
        dumped = Path(tmp)
        index = dump_model_icons.export(bundle, dumped, identifiers)
        files = sorted({entry[kind] for entry in index.values() for kind in ("icon", "sidebar") if entry[kind]})
        quantize([dumped / file for file in files])
        docs.mkdir(parents=True, exist_ok=True)
        written = []
        for file in files:
            target = docs / file
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(dumped / file, target)
            written.append(target)
        for identifier, entry in index.items():
            if entry["sidebar"]:
                name = docs / f"{identifier}-sidebar.png"
                dump_model_icons.link(docs / entry["sidebar"], name)
                written.append(name)
    prune(docs, set(written))
    return sorted(written)


def quantize(files: list[Path]) -> None:
    """Rewrites each PNG as an 8-bit palette image, leaving those alone that would not get smaller."""
    if not files:
        return
    run = subprocess.run(["pngquant", "--force", "--skip-if-larger", "--strip", "--ext", ".png", *files], capture_output=True, text=True)
    if run.returncode and run.returncode not in SKIPPED:
        raise SystemExit(f"pngquant failed ({run.returncode}): {run.stderr.strip()}")


def prune(docs: Path, keep: set[Path]) -> list[Path]:
    """Removes the files and links under docs that are not in keep, except dotfiles, then the directories left empty."""
    removed = []
    for path in sorted(docs.rglob("*"), reverse=True):
        if path.name.startswith("."):
            continue
        if path.is_dir() and not path.is_symlink():
            if not any(path.iterdir()):
                path.rmdir()
                removed.append(path)
        elif path not in keep:
            path.unlink()
            removed.append(path)
    return removed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Refresh docs/models with the icons of the pictured device types.")
    parser.add_argument("identifiers", nargs="*", default=list(MODELS), help="type identifiers to picture; the documented ones when empty")
    parser.add_argument("--docs", type=dump_model_icons.directory, default=DOCS, help=f"directory to refresh (default: {DOCS})")
    parser.add_argument("--bundle", type=Path, default=dump_model_icons.BUNDLE, help=f"bundle to read (default: {dump_model_icons.BUNDLE})")
    args = parser.parse_args(argv)
    if sys.platform != "darwin":
        print("update_model_icons is macOS only", file=sys.stderr)
        return 2
    written = update(args.identifiers, args.docs, args.bundle)
    say(f"{len(written)} files and links in {args.docs}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
