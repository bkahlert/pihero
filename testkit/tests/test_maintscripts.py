import pytest

from pihero_testkit import maintscripts, tools

pytestmark = pytest.mark.tier0


class TestPostinst:
    def test_enables_and_restarts_each_unit(self):
        script = maintscripts.postinst(["a.service", "b.service"], fragment="")

        assert "deb-systemd-helper enable 'a.service'" in script
        assert "deb-systemd-invoke restart 'b.service'" in script

    def test_runs_fragment_before_enabling_units(self):
        script = maintscripts.postinst(["a.service"], fragment="touch /tmp/fragment\n")

        assert script.index("touch /tmp/fragment") < script.index("deb-systemd-helper enable")

    def test_without_units_only_contains_fragment(self):
        script = maintscripts.postinst([], fragment="echo hi\n")

        assert "deb-systemd" not in script
        assert "echo hi" in script


class TestPrerm:
    def test_stops_units_on_remove(self):
        script = maintscripts.prerm(["a.service"], fragment="")

        assert "deb-systemd-invoke stop 'a.service'" in script
        assert '"$1" = "remove"' in script


class TestPostrm:
    def test_purges_unit_state_and_runs_fragment_on_purge_only(self):
        script = maintscripts.postrm(["a.service"], fragment="rm -f /etc/x\n")

        purge_block = script[script.index('"$1" = "purge"'):]
        assert "deb-systemd-helper purge 'a.service'" in purge_block
        assert "rm -f /etc/x" in purge_block


class TestWrite:
    def test_writes_three_scripts_that_pass_shellcheck(self, tmp_path):
        pkg = tmp_path / "pihero-x"
        (pkg / "scripts").mkdir(parents=True)
        (pkg / "units.txt").write_text("# units\npihero-x.service\n")
        (pkg / "scripts" / "postinst.sh").write_text("# shellcheck shell=sh\n/usr/lib/pihero/bootconfig add cmdline x=1 --package pihero-x\n")

        maintscripts.write(pkg)

        names = sorted(p.name for p in (pkg / ".build").iterdir())
        assert names == ["postinst", "postrm", "prerm"]
        for name in names:
            result = tools.run(["shellcheck", "-s", "sh", f"/pkg/.build/{name}"], mounts=[f"{pkg}:/pkg:ro"], check=False, capture=True)
            assert result.returncode == 0, result.stdout
