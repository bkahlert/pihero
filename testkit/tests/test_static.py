import re
import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from pihero_testkit import tools

pytestmark = pytest.mark.tier0

ROOT = Path.cwd()
TESTKIT_DEVICES = Path(str(files("pihero_testkit") / "devices"))
STRIP_RPI_KEYS = (
    "import sys, yaml; d = yaml.safe_load(open(sys.argv[1])); "
    "[d.pop(k, None) for k in ('rpi', 'enable_ssh')]; "
    "open(sys.argv[2], 'w').write('#cloud-config\\n' + yaml.safe_dump(d))"
)


def shell_files():
    for path in (ROOT / "packages").rglob("*"):
        if not path.is_file() or path.is_symlink() or ".build" in path.parts:
            continue
        first_line = path.open("rb").readline()
        if path.suffix == ".sh" or (first_line.startswith(b"#!") and b"sh" in first_line):
            yield path


def unit_files():
    yield from (ROOT / "packages").glob("*/root/usr/lib/systemd/system/*.service")


def go_files():
    for path in (ROOT / "packages").rglob("*.go"):
        if ".build" not in path.parts:
            yield path


def package_dirs():
    yield from (p for p in (ROOT / "packages").iterdir() if (p / "nfpm.yaml").is_file())


def declared_depends(nfpm: Path) -> list[str]:
    """The package names under `depends:` of an nfpm.yaml, version constraints stripped."""
    names, inside = [], False
    for line in nfpm.read_text().splitlines():
        if line.startswith("depends:"):
            inside = True
        elif inside and line.startswith("  - "):
            names.append(line[4:].split()[0])
        elif inside and line and not line.startswith(" "):
            break
    return names


def device_files():
    yield from (ROOT / "devices").glob("*/user-data")
    yield from TESTKIT_DEVICES.glob("*/user-data")


@pytest.mark.parametrize("script", sorted(shell_files()), ids=lambda p: str(p.relative_to(ROOT)))
def test_shell_file_passes_shellcheck(script):
    result = tools.run(["shellcheck", f"/work/{script.relative_to(ROOT)}"], check=False, capture=True)

    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("source", sorted(go_files()), ids=lambda p: str(p.relative_to(ROOT)))
def test_go_file_is_formatted_and_vets_clean(source):
    path = f"/work/{source.relative_to(ROOT)}"
    unformatted = tools.run(["gofmt", "-l", path], capture=True).stdout
    vet = tools.run(["go", "vet", path], check=False, capture=True, mounts=[tools.GO_CACHE])

    assert unformatted == ""
    assert vet.returncode == 0, vet.stderr


@pytest.mark.parametrize("package", sorted(package_dirs()), ids=lambda p: p.name)
def test_manifest_is_architecture_all_in_section_admin(package):
    manifest = (package / "nfpm.yaml").read_text()

    assert "\narch: all\n" in manifest
    assert "\nsection: admin\n" in manifest


@pytest.mark.parametrize("package", sorted(package_dirs()), ids=lambda p: p.name)
def test_maintainer_scripts_that_manage_users_depend_on_adduser(package):
    """Trixie's minimal images carry no adduser: a postinst that calls it without the dependency fails the install with 127."""
    fragments = " ".join(f.read_text() for f in (package / "scripts").glob("*.sh"))
    if not re.search(r"\b(adduser|addgroup|deluser|delgroup)\b", fragments):
        pytest.skip("the maintainer scripts manage no users")

    assert "adduser" in declared_depends(package / "nfpm.yaml")


@pytest.mark.parametrize("unit", sorted(unit_files()), ids=lambda p: p.name)
def test_unit_passes_systemd_analyze_verify(unit):
    package_root = unit.parents[4]
    result = tools.run(
        ["systemd-analyze", "verify", "--man=no", f"/work/{unit.relative_to(ROOT)}"],
        mounts=[f"{package_root / 'usr' / 'lib' / 'pihero'}:/usr/lib/pihero:ro"],
        check=False, capture=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("user_data", sorted(device_files()), ids=lambda p: p.parent.name)
def test_device_file_validates_against_cloud_init_schema(user_data):
    staged = ROOT / "dist" / "schema" / user_data.parent.name
    staged.mkdir(parents=True, exist_ok=True)
    shutil.copy(user_data, staged / "user-data")
    relative = staged.relative_to(ROOT)

    result = tools.run(
        ["sh", "-c", f"python3 -c \"{STRIP_RPI_KEYS}\" /work/{relative}/user-data /work/{relative}/stripped && cloud-init schema --config-file /work/{relative}/stripped"],
        check=False, capture=True,
    )

    assert user_data.read_text().startswith("#cloud-config\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Valid schema" in result.stdout
