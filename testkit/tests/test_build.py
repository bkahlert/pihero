import subprocess
from pathlib import Path

import pytest

from pihero_testkit import build, tools

pytestmark = pytest.mark.tier0


class TestVersionFromGit:
    @pytest.mark.parametrize(
        ("describe", "version"),
        [
            ("v2.0.0-0-gabc1234", "2.0.0"),
            ("v2.0.0-3-gabc1234", "2.0.0+3.abc1234"),
            ("v2.0.0-3-gabc1234-dirty", "2.0.0+3.abc1234.dirty"),
            ("v2.0.0-0-gabc1234-dirty", "2.0.0+0.abc1234.dirty"),
            ("abc1234", "0.0.0+abc1234"),
            ("abc1234-dirty", "0.0.0+abc1234.dirty"),
            ("v2.0.0-rc.1-0-gabc1234", "2.0.0~rc.1"),
            ("v2.0.0-rc.1-3-gabc1234", "2.0.0~rc.1+3.abc1234"),
        ],
    )
    def test_maps_git_describe_to_a_debian_version(self, describe, version):
        assert build.version_from_describe(describe) == version


class TestBuild:
    def test_builds_a_package_from_a_directory(self, tmp_path, monkeypatch):
        pkg = Path("dist") / "probe" / "src" / "pihero-zz-probe"
        (pkg / "root" / "usr" / "lib" / "pihero").mkdir(parents=True)
        (pkg / "root" / "usr" / "lib" / "pihero" / "probe").write_text("#!/bin/sh\necho probe\n")
        (pkg / "root" / "usr" / "lib" / "pihero" / "probe").chmod(0o755)
        (pkg / "nfpm.yaml").write_text(
            "name: pihero-zz-probe\narch: all\nplatform: linux\nversion: ${VERSION}\nsection: admin\npriority: optional\n"
            "maintainer: Björn Kahlert <bkahlert@users.noreply.github.com>\ndescription: probe\nlicense: MIT\n"
            "contents:\n  - src: root/\n    dst: /\n    type: tree\n"
            "scripts:\n  postinstall: .build/postinst\n  preremove: .build/prerm\n  postremove: .build/postrm\n"
        )
        try:
            deb = build.build(pkg, "9.9.9", dist=Path("dist") / "probe")

            info = tools.run(["dpkg-deb", "--info", f"/work/{deb.relative_to(Path.cwd())}"], capture=True).stdout
            contents = tools.run(["dpkg-deb", "--contents", f"/work/{deb.relative_to(Path.cwd())}"], capture=True).stdout
            assert deb.name == "pihero-zz-probe_9.9.9_all.deb"
            assert " Architecture: all" in info
            assert " Version: 9.9.9" in info
            assert "-rwxr-xr-x" in contents and "./usr/lib/pihero/probe" in contents
        finally:
            subprocess.run(["rm", "-rf", "dist/probe"], check=True)


class TestDiscover:
    def test_finds_manifests_and_build_scripts_but_not_plain_directories(self, tmp_path, monkeypatch):
        (tmp_path / "a-nfpm").mkdir()
        (tmp_path / "a-nfpm" / "nfpm.yaml").write_text("name: a\n")
        (tmp_path / "b-script").mkdir()
        (tmp_path / "b-script" / "build").write_text("#!/bin/sh\n")
        (tmp_path / "b-script" / "Containerfile").write_text("FROM scratch\n")
        (tmp_path / "c-plain").mkdir()
        (tmp_path / "c-plain" / "README.md").write_text("")
        monkeypatch.setattr(build, "PACKAGES", tmp_path)

        found = build.discover()

        assert [p.name for p in found] == ["a-nfpm", "b-script"]


class TestBuildScript:
    def test_runs_the_script_in_its_image_and_returns_the_debs_it_prints(self):
        pkg, dist = probe_script("pihero-zz-probe", 'deb="$1/pihero-zz-probe_9.9.9_arm64.deb"\n: > "$deb"\nprintf "%s\\n" "$deb"\n')
        try:
            debs = build.build_script(pkg, dist=dist)

            assert debs == [dist / "pihero-zz-probe_9.9.9_arm64.deb"]
            assert debs[0].exists()
        finally:
            remove_probe(pkg)

    def test_fails_on_a_script_that_prints_no_deb(self):
        pkg, dist = probe_script("pihero-zz-silent", 'echo building >&2\n')
        try:
            with pytest.raises(RuntimeError, match="pihero-zz-silent"):
                build.build_script(pkg, dist=dist)
        finally:
            remove_probe(pkg)

    def test_returns_the_packages_debs_already_in_dist_without_building_its_image(self):
        pkg, dist = probe_script("pihero-zz-built", 'exit 1\n')
        (pkg / "Containerfile").write_text("FROM localhost/pihero-no-such-image:0\n")
        deb = dist / "pihero-zz-built_1.0_arm64.deb"
        deb.write_bytes(b"")
        try:
            debs = build.build_script(pkg, dist=dist)

            assert debs == [deb]
        finally:
            remove_probe(pkg)


def probe_script(name: str, body: str) -> tuple[Path, Path]:
    pkg = Path("dist") / f"probe-{name}" / "src" / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "Containerfile").write_text(f"FROM {tools.ensure_image()}\nHEALTHCHECK NONE\n")
    script = pkg / "build"
    script.write_text('#!/bin/sh\nset -e\n[ "$1" = --dist ] && shift\n' + body)
    script.chmod(0o755)
    return pkg, Path.cwd() / "dist" / f"probe-{name}"


def remove_probe(pkg: Path) -> None:
    subprocess.run([*tools.PODMAN, "rmi", "-f", tools.image(pkg / "Containerfile")], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["rm", "-rf", str(pkg.parents[1])], check=True)


class TestIsPackage:
    def test_is_true_for_a_directory_with_an_nfpm_manifest(self, tmp_path):
        (tmp_path / "nfpm.yaml").write_text("name: probe\n")

        assert build.is_package(tmp_path)

    def test_is_true_for_a_build_script_with_its_containerfile(self, tmp_path):
        (tmp_path / "build").write_text("#!/bin/sh\n")
        (tmp_path / "Containerfile").write_text("FROM scratch\n")

        assert build.is_package(tmp_path)

    def test_is_false_for_a_build_script_alone(self, tmp_path):
        (tmp_path / "build").write_text("#!/bin/sh\n")

        assert not build.is_package(tmp_path)

    def test_is_false_for_a_tests_directory(self, tmp_path):
        (tmp_path / "test_installed.py").write_text("")

        assert not build.is_package(tmp_path)


class TestPackageName:
    def test_is_the_name_the_nfpm_manifest_declares(self, tmp_path):
        (tmp_path / "nfpm.yaml").write_text("name: pihero-netmon\narch: all\n")

        name = build.package_name(tmp_path)

        assert name == "pihero-netmon"

    def test_is_the_directorys_name_for_a_build_script_package(self, tmp_path):
        (tmp_path / "build").write_text("#!/bin/sh\n")
        (tmp_path / "Containerfile").write_text("FROM scratch\n")

        name = build.package_name(tmp_path)

        assert name == tmp_path.name
