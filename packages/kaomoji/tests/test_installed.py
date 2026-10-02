import pytest

pytestmark = pytest.mark.installed


class TestPackage:
    def test_is_installed_at_the_built_version(self, host, version):
        package = host.package("kaomoji")

        assert package.is_installed
        assert package.version == version

    def test_is_built_for_the_hosts_architecture(self, host):
        architecture = host.check_output("dpkg-query -W -f='${Architecture}' kaomoji")

        assert architecture == host.check_output("dpkg --print-architecture")

    def test_ships_the_binary_as_a_command_owned_by_root(self, host):
        file = host.file("/usr/bin/kaomoji")

        assert file.exists
        assert file.mode == 0o755
        assert file.user == "root"

    @pytest.mark.parametrize("path", ["/usr/bin/hero", "/usr/bin/wizard", "/usr/bin/visitor", "/usr/lib/kaomoji"])
    def test_ships_none_of_the_scripts_it_used_to(self, host, path):
        assert not host.file(path).exists


class TestFaces:
    @pytest.mark.parametrize(
        ("command", "text"),
        [
            ("kaomoji hero --mood happy --no-color", "─=≡▰▩▩[✿＾ｖ＾]⊐"),
            ("kaomoji wizard --no-color", "(つ◕౪◕)つ─｡ﾟ․☆･*ﾟ"),
            ("kaomoji visitor --no-color", "┴┬┴┤´Ｏ´)ﾉ"),
        ],
    )
    def test_render_from_path(self, host, command, text):
        assert host.check_output(command) == text

    def test_prints_the_built_version(self, host, version):
        assert host.check_output("kaomoji --version") == version

    def test_leaves_through_its_own_edge_without_a_terminal(self, host):
        frames = host.check_output("KAOMOJI_COLUMNS=0 kaomoji hero --no-color --no-entrance --loops 1 --exit --frame-ms 0").split("\r")

        assert len(frames) == 1 + 12 + 16  # the hidden cursor, a hover cycle, the exit over the hero's own width


class TestRemoval:
    @pytest.mark.mutating
    def test_purge_leaves_nothing_behind_and_reinstall_restores_the_system(self, host, target):
        target.purge(["kaomoji"])

        assert not host.file("/usr/bin/kaomoji").exists

        target.reinstall()

        assert host.package("kaomoji").is_installed
        assert host.package("pihero").is_installed
