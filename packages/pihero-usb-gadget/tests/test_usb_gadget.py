import os
import subprocess
import sys
from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0

SCRIPT = Path(__file__).resolve().parents[1] / "root" / "usr" / "lib" / "pihero" / "usb-gadget"
usb_gadget = load_script(SCRIPT)

MODPROBE = ["modprobe", "g_cdc", "host_addr=02:00:a1:b2:c3:d4", "dev_addr=06:00:a1:b2:c3:d4", 'iManufacturer="Raspberry Pi Ltd."', 'iProduct="Raspberry Pi Zero W Rev 1.1"']


class TestDeviceTreeString:
    def test_strips_the_trailing_nul_and_whitespace(self, tmp_path):
        path = tmp_path / "model"
        path.write_bytes(b"Raspberry Pi Zero W Rev 1.1 \x00")

        result = usb_gadget.device_tree_string(path)

        assert result == "Raspberry Pi Zero W Rev 1.1"

    def test_is_none_on_a_missing_file(self, tmp_path):
        result = usb_gadget.device_tree_string(tmp_path / "model")

        assert result is None

    def test_is_none_on_an_empty_file(self, tmp_path):
        path = tmp_path / "serial-number"
        path.write_bytes(b"\x00")

        result = usb_gadget.device_tree_string(path)

        assert result is None


class TestMacs:
    def test_derives_host_and_dev_addresses_from_the_last_ten_digits_of_the_serial(self):
        result = usb_gadget.macs("00000000a1b2c3d4")

        assert result == ("02:00:a1:b2:c3:d4", "06:00:a1:b2:c3:d4")


class TestModuleArgs:
    def test_quotes_the_strings_for_the_kernel(self):
        result = usb_gadget.module_args("02:00:a1:b2:c3:d4", "06:00:a1:b2:c3:d4", "Raspberry Pi Ltd.", "Raspberry Pi Zero W Rev 1.1")

        assert result == MODPROBE[1:]


class TestCli:
    def test_loads_g_cdc_named_after_the_model(self, device_tree, stubs):
        result = cli(device_tree, stubs)

        assert result.returncode == 0, result.stderr
        assert stubs.calls() == [MODPROBE]
        assert result.stdout == f"usb-gadget: loaded {' '.join(MODPROBE[1:])}\n"

    def test_product_overrides_the_model(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"PRODUCT": "Kitchen Pi"})

        assert result.returncode == 0, result.stderr
        assert stubs.calls() == [[*MODPROBE[:-1], 'iProduct="Kitchen Pi"']]

    def test_an_empty_product_falls_back_to_the_model(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"PRODUCT": ""})

        assert result.returncode == 0, result.stderr
        assert stubs.calls() == [MODPROBE]

    def test_cidr_sets_the_shared_profile_before_loading(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"CIDR": "10.10.10.10/29"})

        assert result.returncode == 0, result.stderr
        assert stubs.calls() == [["nmcli", "connection", "modify", "USB Gadget (shared)", "ipv4.addresses", "10.10.10.10/29"], MODPROBE]

    def test_exits_1_on_a_missing_serial(self, device_tree, stubs):
        (device_tree / "serial-number").unlink()

        result = cli(device_tree, stubs)

        assert result.returncode == 1
        assert "no serial number" in result.stderr
        assert stubs.calls() == []

    def test_exits_1_without_a_model_or_product(self, device_tree, stubs):
        (device_tree / "model").unlink()

        result = cli(device_tree, stubs)

        assert result.returncode == 1
        assert "PRODUCT is unset" in result.stderr
        assert stubs.calls() == []

    def test_exits_1_on_a_product_with_a_double_quote(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"PRODUCT": 'Pi "Zero"'})

        assert result.returncode == 1
        assert "double quote" in result.stderr
        assert stubs.calls() == []

    def test_exits_1_when_nmcli_fails_and_does_not_load_the_module(self, device_tree, stubs):
        result = cli(device_tree, stubs, env={"CIDR": "10.10.10.10/29"}, fail="nmcli")

        assert result.returncode == 1
        assert "could not set 10.10.10.10/29" in result.stderr
        assert [call[0] for call in stubs.calls()] == ["nmcli"]

    def test_exits_1_when_modprobe_fails(self, device_tree, stubs):
        result = cli(device_tree, stubs, fail="modprobe")

        assert result.returncode == 1
        assert "modprobe g_cdc" in result.stderr


STUB = """#!/bin/sh
printf '%s\\t' "${0##*/}" "$@" >>"$STUB_LOG"
printf '\\n' >>"$STUB_LOG"
[ "$STUB_FAIL" != "${0##*/}" ]
"""


class Stubs:
    def __init__(self, directory: Path):
        self.directory = directory
        self.log = directory / "calls.log"
        for name in ("modprobe", "nmcli"):
            (directory / name).write_text(STUB)
            (directory / name).chmod(0o755)

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [line.rstrip("\t").split("\t") for line in self.log.read_text().splitlines()]


@pytest.fixture
def stubs(tmp_path):
    directory = tmp_path / "bin"
    directory.mkdir()
    return Stubs(directory)


@pytest.fixture
def device_tree(tmp_path):
    path = tmp_path / "device-tree"
    path.mkdir()
    (path / "model").write_bytes(b"Raspberry Pi Zero W Rev 1.1\x00")
    (path / "serial-number").write_bytes(b"00000000a1b2c3d4\x00")
    return path


def cli(device_tree: Path, stubs: Stubs, env: dict | None = None, fail: str = "") -> subprocess.CompletedProcess:
    base = {key: value for key, value in os.environ.items() if key not in ("PRODUCT", "CIDR")}
    full = {**base, "PATH": f"{stubs.directory}:{base['PATH']}", "PIHERO_DEVICE_TREE": str(device_tree), "STUB_LOG": str(stubs.log), "STUB_FAIL": fail, **(env or {})}
    return subprocess.run([sys.executable, str(SCRIPT)], env=full, capture_output=True, text=True)
