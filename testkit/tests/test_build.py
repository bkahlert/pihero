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
        pkg = Path("packages") / "pihero-zz-probe"
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
            subprocess.run(["rm", "-rf", str(pkg), "dist/probe"], check=True)
