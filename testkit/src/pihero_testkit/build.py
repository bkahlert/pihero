"""Builds every package under packages/ into dist/ with nfpm running in the tools container."""

import os
import re
import subprocess
import sys
from pathlib import Path

from . import maintscripts, tools

PACKAGES = Path.cwd() / "packages"
DIST = Path.cwd() / "dist"


def version_from_describe(describe: str) -> str:
    match = re.fullmatch(r"v(\d+\.\d+\.\d+)(?:-([0-9A-Za-z.]+))?-(\d+)-g([0-9a-f]+)(-dirty)?", describe)
    if not match:
        return "0.0.0+" + describe.replace("-dirty", ".dirty")
    base, pre, ahead, sha, dirty = match.groups()
    if pre:
        base = f"{base}~{pre}"
    if ahead == "0" and not dirty:
        return base
    return f"{base}+{ahead}.{sha}{'.dirty' if dirty else ''}"


def version_from_git() -> str:
    if env := os.environ.get("VERSION"):
        return env
    out = subprocess.run(
        ["git", "describe", "--tags", "--match", "v*", "--long", "--dirty", "--always"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return version_from_describe(out)


def discover() -> list[Path]:
    return sorted(p for p in PACKAGES.iterdir() if (p / "nfpm.yaml").exists())


def build(pkg_dir: Path, version: str, dist: Path = DIST) -> Path:
    pkg_dir = pkg_dir.resolve()
    dist = dist.resolve()
    maintscripts.write(pkg_dir)
    dist.mkdir(parents=True, exist_ok=True)
    deb = dist / f"{pkg_dir.name}_{version}_all.deb"
    tools.run(
        ["nfpm", "package", "-f", "nfpm.yaml", "-p", "deb", "-t", f"/work/{deb.relative_to(Path.cwd())}"],
        workdir=f"/work/{pkg_dir.relative_to(Path.cwd())}",
        env={"VERSION": version},
    )
    return deb


def build_all(version: str, dist: Path = DIST) -> list[Path]:
    return [build(pkg_dir, version, dist) for pkg_dir in discover()]


if __name__ == "__main__":
    for path in build_all(version_from_git()):
        print(path)
    sys.exit(0)
