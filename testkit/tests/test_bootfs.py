import pytest

from pihero_testkit import bootfs, vm

pytestmark = pytest.mark.tier0

STOCK = "console=serial0,115200 console=tty1 root=PARTUUID=0a1b2c3d-02 rootfstype=ext4 fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles cfg80211.ieee80211_regdom=DE"


class TestKernelArgs:
    def test_replaces_root_and_console_and_keeps_the_rest(self):
        args = bootfs.kernel_args(STOCK)

        assert args.startswith("root=LABEL=rootfs console=ttyAMA0,115200 ")
        assert "PARTUUID" not in args
        assert "console=tty1" not in args
        assert args.endswith("rootfstype=ext4 fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles cfg80211.ieee80211_regdom=DE")

    def test_drops_a_firstboot_init(self):
        args = bootfs.kernel_args(STOCK + " init=/usr/lib/raspberrypi-sys-mods/firstboot")

        assert "init=" not in args

    def test_keeps_parameters_added_by_bootconfig(self):
        args = bootfs.kernel_args(STOCK + " logo.nologo pihero.probe=1")

        assert args.endswith("logo.nologo pihero.probe=1")


class TestStage:
    def test_points_the_harness_repository_source_at_the_served_port(self, device, stock, tmp_path):
        staged = bootfs.stage(device, stock, tmp_path / "bootfs.d", repo_port=54321)

        user_data = (staged / "user-data").read_text()
        assert "      URIs: http://10.0.2.2:54321/\n" in user_data
        assert "8000" not in user_data

    def test_copies_the_other_files_unchanged(self, device, stock, tmp_path):
        staged = bootfs.stage(device, stock, tmp_path / "bootfs.d", repo_port=54321)

        assert (staged / "network-config").read_text() == "version: 2\n"
        assert (staged / "config.txt").read_text() == "arm_64bit=1\n"
        assert (staged / "cmdline.txt").read_text() == STOCK

    def test_leaves_a_user_data_without_the_source_as_it_is(self, device, stock, tmp_path):
        (device / "user-data").write_text("#cloud-config\nhostname: plain\n")

        staged = bootfs.stage(device, stock, tmp_path / "bootfs.d", repo_port=54321)

        assert (staged / "user-data").read_text() == "#cloud-config\nhostname: plain\n"

    def test_writes_a_meta_data_for_a_device_without_one(self, device, stock, tmp_path):
        staged = bootfs.stage(device, stock, tmp_path / "bootfs.d", repo_port=54321)

        assert (staged / "meta-data").read_text() == "instance-id: pihero-sample-1\nlocal-hostname: sample\n"

    def test_points_every_source_at_the_served_port(self, device, stock, tmp_path):
        (device / "user-data").write_text(USER_DATA + USER_DATA.replace("pihero.sources", "app.sources").split("write_files:\n")[1])

        staged = bootfs.stage(device, stock, tmp_path / "bootfs.d", repo_port=54321)

        user_data = (staged / "user-data").read_text()
        assert user_data.count("      URIs: http://10.0.2.2:54321/\n") == 2
        assert "8000" not in user_data

    def test_rewrites_the_source_the_all_features_device_writes(self, stock, tmp_path):
        staged = bootfs.stage(vm.DEFAULT_DEVICE, stock, tmp_path / "bootfs.d", repo_port=54321)

        user_data = (staged / "user-data").read_text()
        assert "      URIs: http://10.0.2.2:54321/\n" in user_data
        assert "8000" not in user_data

    @pytest.fixture
    def device(self, tmp_path):
        device = tmp_path / "sample"
        device.mkdir()
        (device / "user-data").write_text(USER_DATA)
        (device / "network-config").write_text("version: 2\n")
        return device

    @pytest.fixture
    def stock(self, tmp_path):
        stock = tmp_path / "boot"
        stock.mkdir()
        (stock / "config.txt").write_text("arm_64bit=1\n")
        (stock / "cmdline.txt").write_text(STOCK)
        return stock


USER_DATA = """\
#cloud-config
write_files:
  - path: /etc/apt/sources.list.d/pihero.sources
    content: |
      Types: deb
      URIs: http://10.0.2.2:8000/
      Suites: ./
      Trusted: yes
"""
