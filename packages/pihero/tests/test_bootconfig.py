import os
import subprocess
import sys
from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0

SCRIPT = Path(__file__).resolve().parents[1] / "root" / "usr" / "lib" / "pihero" / "bootconfig"
bootconfig = load_script(SCRIPT)

STOCK_CONFIG = """# For more options and information see
# http://rptl.io/configtxt
dtparam=audio=on
camera_auto_detect=1
display_auto_detect=1
auto_initramfs=1
dtoverlay=vc4-kms-v3d
max_framebuffers=2
disable_fw_kms_setup=1
arm_64bit=1
disable_overscan=1
arm_boost=1

[cm4]
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
"""

STOCK_CMDLINE = "console=serial0,115200 console=tty1 root=PARTUUID=0a1b2c3d-02 rootfstype=ext4 fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles cfg80211.ieee80211_regdom=DE\n"


class TestConfig:
    class TestSet:
        def test_appends_missing_key_to_the_last_all_section(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.set_key(sections, "all", "disable_splash", "1")

            assert changed
            assert bootconfig.render_config(sections).endswith("[all]\ndisable_splash=1\n")

        def test_replaces_an_existing_value_in_place(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.set_key(sections, "all", "disable_overscan", "0")

            text = bootconfig.render_config(sections)
            assert changed
            assert "disable_overscan=0\n" in text
            assert "disable_overscan=1" not in text
            assert text.index("disable_overscan=0") < text.index("[cm4]")

        def test_is_unchanged_on_the_same_value(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.set_key(sections, "all", "arm_64bit", "1")

            assert not changed
            assert bootconfig.render_config(sections) == STOCK_CONFIG

        def test_leaves_the_same_key_in_other_sections_alone(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            bootconfig.set_key(sections, "all", "dtoverlay", "dwc2")

            text = bootconfig.render_config(sections)
            assert text.count("dtoverlay=dwc2,dr_mode=host") == 1
            assert text.splitlines()[-1] == "dtoverlay=dwc2"

        def test_changes_a_non_repeatable_key_only_in_the_named_section(self):
            sections = bootconfig.parse_config("otg_mode=0\n[cm4]\notg_mode=1\n[all]\n")

            changed = bootconfig.set_key(sections, "all", "otg_mode", "1")

            assert changed
            assert bootconfig.render_config(sections) == "otg_mode=1\n[cm4]\notg_mode=1\n[all]\n"

        def test_adds_a_repeatable_key_as_a_new_line(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            bootconfig.set_key(sections, "all", "dtoverlay", "dwc2")

            text = bootconfig.render_config(sections)
            assert "dtoverlay=vc4-kms-v3d\n" in text
            assert "dtoverlay=dwc2\n" in text

        def test_creates_a_missing_section_at_the_end(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.set_key(sections, "pi0", "gpu_mem", "16")

            assert changed
            assert bootconfig.render_config(sections).endswith("[all]\n[pi0]\ngpu_mem=16\n")

        def test_collapses_duplicate_keys_into_one(self):
            sections = bootconfig.parse_config("arm_boost=1\narm_boost=0\n")

            bootconfig.set_key(sections, "all", "arm_boost", "1")

            assert bootconfig.render_config(sections) == "arm_boost=1\n"

        def test_matches_section_names_case_insensitively(self):
            sections = bootconfig.parse_config("[CM4]\notg_mode=1\n")

            changed = bootconfig.set_key(sections, "cm4", "otg_mode", "1")

            assert not changed

    class TestUnset:
        def test_removes_the_key(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.unset_key(sections, "all", "arm_boost")

            assert changed
            assert "arm_boost" not in bootconfig.render_config(sections)

        def test_removes_only_the_matching_value_of_a_repeatable_key(self):
            sections = bootconfig.parse_config("dtoverlay=vc4-kms-v3d\ndtoverlay=dwc2\n")

            bootconfig.unset_key(sections, "all", "dtoverlay", "dwc2")

            assert bootconfig.render_config(sections) == "dtoverlay=vc4-kms-v3d\n"

        def test_is_unchanged_on_a_missing_key(self):
            sections = bootconfig.parse_config(STOCK_CONFIG)

            changed = bootconfig.unset_key(sections, "all", "gpu_mem")

            assert not changed


class TestCmdline:
    class TestAdd:
        def test_appends_a_missing_parameter(self):
            params = bootconfig.parse_cmdline(STOCK_CMDLINE)

            changed = bootconfig.add_param(params, "logo.nologo")

            assert changed
            assert bootconfig.render_cmdline(params) == STOCK_CMDLINE.rstrip("\n") + " logo.nologo\n"

        def test_replaces_a_parameter_with_the_same_name(self):
            params = bootconfig.parse_cmdline("quiet loglevel=7 splash\n")

            changed = bootconfig.add_param(params, "loglevel=3")

            assert changed
            assert bootconfig.render_cmdline(params) == "quiet loglevel=3 splash\n"

        def test_is_unchanged_on_a_present_parameter(self):
            params = bootconfig.parse_cmdline(STOCK_CMDLINE)

            changed = bootconfig.add_param(params, "quiet")

            assert not changed

    class TestRemove:
        def test_removes_all_occurrences_by_name(self):
            params = bootconfig.parse_cmdline(STOCK_CMDLINE)

            changed = bootconfig.remove_param(params, "console")

            assert changed
            assert "console=" not in bootconfig.render_cmdline(params)

        def test_is_unchanged_on_a_missing_parameter(self):
            params = bootconfig.parse_cmdline(STOCK_CMDLINE)

            changed = bootconfig.remove_param(params, "logo.nologo")

            assert not changed

    def test_keeps_a_single_line_with_a_trailing_newline(self):
        params = bootconfig.parse_cmdline("quiet  splash")

        assert bootconfig.render_cmdline(params) == "quiet splash\n"

    def test_refuses_a_file_with_more_than_one_line(self):
        with pytest.raises(ValueError):
            bootconfig.parse_cmdline("quiet\nsplash\n")


class TestCli:
    def test_set_writes_the_file_and_marks_a_reboot_required(self, bootfs, run_dir):
        result = cli("set", "config", "disable_splash", "1", "--package", "pihero-splash", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 0
        assert result.stdout.strip() == "changed"
        assert (bootfs / "config.txt").read_text().endswith("[all]\ndisable_splash=1\n")
        assert (run_dir / "reboot-required").exists()
        assert (run_dir / "reboot-required.pkgs").read_text() == "pihero-splash\n"

    def test_unchanged_run_does_not_mark_a_reboot(self, bootfs, run_dir):
        result = cli("add", "cmdline", "quiet", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 0
        assert result.stdout.strip() == "unchanged"
        assert not (run_dir / "reboot-required").exists()

    def test_records_each_package_once(self, bootfs, run_dir):
        cli("add", "cmdline", "a=1", "--package", "pihero-splash", bootfs=bootfs, run_dir=run_dir)
        cli("add", "cmdline", "b=1", "--package", "pihero-splash", bootfs=bootfs, run_dir=run_dir)
        cli("add", "cmdline", "c=1", "--package", "pihero-display-hdmi", bootfs=bootfs, run_dir=run_dir)

        assert (run_dir / "reboot-required.pkgs").read_text() == "pihero-splash\npihero-display-hdmi\n"

    def test_multiline_cmdline_exits_1_without_writing(self, bootfs, run_dir):
        (bootfs / "cmdline.txt").write_text("quiet\nsplash\n")

        result = cli("add", "cmdline", "logo.nologo", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 1
        assert "single line" in result.stderr
        assert (bootfs / "cmdline.txt").read_text() == "quiet\nsplash\n"

    def test_missing_file_exits_1(self, bootfs, run_dir):
        (bootfs / "config.txt").unlink()

        result = cli("set", "config", "a", "1", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 1

    def test_unknown_action_exits_2(self, bootfs, run_dir):
        result = cli("frob", "config", "a", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 2

    def test_unset_of_a_repeatable_key_needs_a_value(self, bootfs, run_dir):
        result = cli("unset", "config", "dtoverlay", "--value", "vc4-kms-v3d", bootfs=bootfs, run_dir=run_dir)

        assert result.stdout.strip() == "changed"
        assert "dtoverlay=vc4-kms-v3d" not in (bootfs / "config.txt").read_text()

    def test_unset_with_a_positional_value_removes_only_that_line(self, bootfs, run_dir):
        cli("set", "config", "dtoverlay", "dwc2", bootfs=bootfs, run_dir=run_dir)

        result = cli("unset", "config", "dtoverlay", "dwc2", bootfs=bootfs, run_dir=run_dir)

        text = (bootfs / "config.txt").read_text()
        assert result.stdout.strip() == "changed"
        assert "dtoverlay=dwc2\n" not in text
        assert "dtoverlay=vc4-kms-v3d\n" in text

    def test_add_with_a_stray_value_exits_2_without_writing(self, bootfs, run_dir):
        result = cli("add", "cmdline", "quiet", "extra", bootfs=bootfs, run_dir=run_dir)

        assert result.returncode == 2
        assert (bootfs / "cmdline.txt").read_text() == STOCK_CMDLINE

    def test_leaves_no_temporary_file_behind(self, bootfs, run_dir):
        cli("set", "config", "disable_splash", "1", bootfs=bootfs, run_dir=run_dir)

        assert sorted(p.name for p in bootfs.iterdir()) == ["cmdline.txt", "config.txt"]


@pytest.fixture
def bootfs(tmp_path):
    path = tmp_path / "bootfs"
    path.mkdir()
    (path / "config.txt").write_text(STOCK_CONFIG)
    (path / "cmdline.txt").write_text(STOCK_CMDLINE)
    return path


@pytest.fixture
def run_dir(tmp_path):
    path = tmp_path / "run"
    path.mkdir()
    return path


def cli(*args, bootfs, run_dir):
    env = {**os.environ, "PIHERO_BOOTFS": str(bootfs), "PIHERO_RUN": str(run_dir)}
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True)
