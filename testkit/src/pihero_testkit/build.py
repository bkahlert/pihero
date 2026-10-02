"""Builds every package under packages/ into dist/: nfpm manifests and plain build scripts in the tools container, build scripts with a Containerfile in their own image."""

import os
import re
import subprocess
import sys
from pathlib import Path

from . import maintscripts, tools

PACKAGES = Path.cwd() / "packages"
DIST = Path.cwd() / "dist"
# The devices' architecture; a package that builds itself builds for it, whatever the host is.
TARGET_PLATFORM = "linux/arm64"
NAME_LINE = re.compile(r"^name:\s*(?P<name>\S+)")


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


def is_package(directory: Path) -> bool:
    """Returns whether directory builds a package: nfpm.yaml is there, or a build script."""
    return (directory / "nfpm.yaml").is_file() or (directory / "build").is_file()


def package_name(directory: Path) -> str:
    """Returns the name of the package directory builds: the `name:` of its nfpm manifest, else the directory's name."""
    manifest = directory / "nfpm.yaml"
    if manifest.is_file():
        for line in manifest.read_text().splitlines():
            if match := NAME_LINE.match(line):
                return match["name"]
    return directory.name


def discover() -> list[Path]:
    return sorted(p for p in PACKAGES.iterdir() if is_package(p))


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


def build_script(pkg_dir: Path, dist: Path = DIST) -> list[Path]:
    """Runs the package directory's build script in the image from its Containerfile; returns the debs the script printed."""
    pkg_dir = pkg_dir.resolve()
    dist = dist.resolve()
    dist.mkdir(parents=True, exist_ok=True)
    # A self-built package carries its own version, so a deb of it in dist is the one the script would reuse anyway;
    # returning it here spares building the image, which a CI runner would otherwise do on every job.
    existing = sorted(dist.glob(f"{pkg_dir.name}_*.deb"))
    if existing:
        return existing
    image = tools.ensure_image(pkg_dir / "Containerfile", TARGET_PLATFORM)
    script = f"/work/{pkg_dir.relative_to(Path.cwd())}/build"
    # Only the deb paths come through stdout; the build's own output stays on the terminal.
    command = tools.command([script, "--dist", f"/work/{dist.relative_to(Path.cwd())}"], image=image)
    result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE)
    debs = [Path.cwd() / line.removeprefix("/work/") for line in result.stdout.splitlines() if line.startswith("/work/")]
    if not debs:
        raise RuntimeError(f"{pkg_dir.name}: the build script printed no .deb path")
    return debs


def build_in_tools(pkg_dir: Path, version: str, dist: Path = DIST) -> list[Path]:
    """Runs the package directory's build script in the tools image with the version; returns the debs the script printed."""
    pkg_dir = pkg_dir.resolve()
    dist = dist.resolve()
    dist.mkdir(parents=True, exist_ok=True)
    script = f"/work/{pkg_dir.relative_to(Path.cwd())}/build"
    # Only the deb paths come through stdout; the build's own output stays on the terminal.
    command = tools.command([script, "--dist", f"/work/{dist.relative_to(Path.cwd())}", "--version", version], mounts=[tools.GO_CACHE])
    result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE)
    debs = [Path.cwd() / line.removeprefix("/work/") for line in result.stdout.splitlines() if line.startswith("/work/")]
    if not debs:
        raise RuntimeError(f"{pkg_dir.name}: the build script printed no .deb path")
    return debs


def build_all(version: str, dist: Path = DIST) -> list[Path]:
    debs = []
    for pkg_dir in discover():
        if (pkg_dir / "nfpm.yaml").exists():
            debs.append(build(pkg_dir, version, dist))
        elif (pkg_dir / "Containerfile").exists():
            debs.extend(build_script(pkg_dir, dist))
        else:
            debs.extend(build_in_tools(pkg_dir, version, dist))
    return debs


if __name__ == "__main__":
    for path in build_all(version_from_git()):
        print(path)
    sys.exit(0)
