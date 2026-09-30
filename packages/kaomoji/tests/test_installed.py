import pytest

pytestmark = pytest.mark.installed


class TestPackage:
    def test_is_installed_at_the_built_version(self, host, version):
        package = host.package("kaomoji")

        assert package.is_installed
        assert package.version == version

    @pytest.mark.parametrize("path", ["/usr/bin/hero", "/usr/bin/wizard", "/usr/bin/visitor"])
    def test_ships_the_faces_as_commands_owned_by_root(self, host, path):
        file = host.file(path)

        assert file.exists
        assert file.mode == 0o755
        assert file.user == "root"

    def test_ships_the_engine_owned_by_root_read_only(self, host):
        file = host.file("/usr/lib/kaomoji/kaomoji.bash")

        assert file.exists
        assert file.mode == 0o644
        assert file.user == "root"


class TestFaces:
    @pytest.mark.parametrize(
        ("command", "text"),
        [
            ("hero --mood happy --no-color", "─=≡▰▩▩[✿＾ｖ＾]⊐"),
            ("wizard --no-color", "(つ◕౪◕)つ─｡ﾟ․☆･*ﾟ"),
            ("visitor --no-color", "┴┬┴┤´Ｏ´)ﾉ"),
        ],
    )
    def test_render_from_path_through_the_installed_engine(self, host, command, text):
        output = host.check_output(command)

        assert output == text


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_leaves_nothing_behind_and_reinstall_restores_the_system(self, host, target):
        target.purge(["kaomoji"])

        for path in SHIPPED:
            assert not host.file(path).exists

        target.reinstall()

        assert host.package("kaomoji").is_installed
        assert host.package("pihero").is_installed


SHIPPED = ["/usr/bin/hero", "/usr/bin/wizard", "/usr/bin/visitor", "/usr/lib/kaomoji/kaomoji.bash"]
