"""Generates Debian maintainer scripts for a package directory from its units.txt and hook fragments.

The systemd handling is the snippet debhelper emits, so packages behave like any Debian package.
"""

from pathlib import Path

HEADER = "#!/bin/sh\nset -e\n"


def units_of(pkg_dir: Path) -> list[str]:
    path = pkg_dir / "units.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def fragment_of(pkg_dir: Path, name: str) -> str:
    path = pkg_dir / "scripts" / f"{name}.sh"
    return path.read_text() if path.exists() else ""


def postinst(units: list[str], fragment: str) -> str:
    lines = [HEADER, 'if [ "$1" = "configure" ] || [ "$1" = "abort-upgrade" ] || [ "$1" = "abort-deconfigure" ] || [ "$1" = "abort-remove" ]; then']
    lines.append(_indent(fragment))
    for unit in units:
        lines.append(
            f"  deb-systemd-helper unmask '{unit}' >/dev/null || true\n"
            f"  if deb-systemd-helper --quiet was-enabled '{unit}'; then\n"
            f"    deb-systemd-helper enable '{unit}' >/dev/null || true\n"
            f"  else\n"
            f"    deb-systemd-helper update-state '{unit}' >/dev/null || true\n"
            f"  fi"
        )
    if units:
        lines.append("  if [ -d /run/systemd/system ]; then\n    systemctl --system daemon-reload >/dev/null || true")
        lines.extend(f"    deb-systemd-invoke restart '{unit}' >/dev/null || true" for unit in units)
        lines.append("  fi")
    lines.append("fi\n")
    return "\n".join(lines)


def prerm(units: list[str], fragment: str) -> str:
    lines = [HEADER, 'if [ "$1" = "remove" ]; then']
    if units:
        lines.append("  if [ -d /run/systemd/system ]; then")
        lines.extend(f"    deb-systemd-invoke stop '{unit}' >/dev/null || true" for unit in units)
        lines.append("  fi")
    lines.append(_indent(fragment))
    lines.append("fi\n")
    return "\n".join(lines)


def postrm(units: list[str], fragment: str) -> str:
    lines = [HEADER]
    if units:
        lines.append("if [ -d /run/systemd/system ]; then\n  systemctl --system daemon-reload >/dev/null || true\nfi")
        lines.append('if [ "$1" = "remove" ] && [ -x /usr/bin/deb-systemd-helper ]; then')
        lines.extend(f"  deb-systemd-helper mask '{unit}' >/dev/null || true" for unit in units)
        lines.append("fi")
    lines.append('if [ "$1" = "purge" ]; then')
    if units:
        lines.append("  if [ -x /usr/bin/deb-systemd-helper ]; then")
        for unit in units:
            lines.append(f"    deb-systemd-helper purge '{unit}' >/dev/null || true\n    deb-systemd-helper unmask '{unit}' >/dev/null || true")
        lines.append("  fi")
    lines.append(_indent(fragment))
    lines.append("fi\n")
    return "\n".join(lines)


def write(pkg_dir: Path) -> None:
    units = units_of(pkg_dir)
    out = pkg_dir / ".build"
    out.mkdir(exist_ok=True)
    for name, render in (("postinst", postinst), ("prerm", prerm), ("postrm", postrm)):
        (out / name).write_text(render(units, fragment_of(pkg_dir, name)))
        (out / name).chmod(0o755)


def _indent(fragment: str) -> str:
    return "\n".join(f"  {line}" if line.strip() else "" for line in fragment.rstrip("\n").splitlines()) if fragment.strip() else "  :"
