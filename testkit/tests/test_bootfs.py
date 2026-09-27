import pytest

from pihero_testkit import bootfs

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
