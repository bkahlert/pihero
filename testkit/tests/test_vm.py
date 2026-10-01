from pathlib import Path

import pytest

from pihero_testkit import prepare, vm

pytestmark = pytest.mark.tier0
BASE = prepare.BaseImage(Path("/b/rootfs.qcow2"), Path("/b/vmlinuz"), Path("/b/initrd.img"), Path("/b/boot"))


class TestParseDisplay:
    def test_reads_width_and_height(self):
        size = vm.parse_display("480x320")

        assert size == (480, 320)

    def test_is_none_for_none(self):
        size = vm.parse_display("none")

        assert size is None

    @pytest.mark.parametrize("display", ["800", "800×480", "800x", "x480", "", "800x480x60"])
    def test_rejects_anything_but_width_x_height_or_none(self, display):
        with pytest.raises(ValueError, match="WIDTHxHEIGHT"):
            vm.parse_display(display)


class TestQemuCommand:
    def test_has_a_gpu_of_the_default_size_and_a_qmp_port(self):
        command = qemu_command(display=(800, 480))

        assert "virtio-gpu-pci,xres=800,yres=480" in command
        assert "tcp:127.0.0.1:4444,server,nowait" in command
        assert command[command.index("tcp:127.0.0.1:4444,server,nowait") - 1] == "-qmp"

    def test_sizes_the_gpu_as_asked(self):
        command = qemu_command(display=(480, 320))

        assert "virtio-gpu-pci,xres=480,yres=320" in command

    def test_leaves_the_gpu_out_for_none(self):
        command = qemu_command(display=None)

        assert not any("virtio-gpu" in word for word in command)
        assert "-qmp" in command

    def test_keeps_the_headless_console_and_the_serial_log(self):
        command = qemu_command(display=(800, 480))

        assert command[command.index("-display") + 1] == "none"
        assert "file,id=serial0,path=/w/serial.log,append=on" in command


def qemu_command(display):
    return vm.qemu_command(BASE, Path("/w/overlay.qcow2"), Path("/w/bootfs.img"), Path("/w/serial.log"), "root=LABEL=rootfs", "hvf", 1024, 2222, 4444, display)
