import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "root"
SCRIPT = PACKAGE_ROOT / "usr" / "lib" / "pihero" / "avahi-render"
TEMPLATES = PACKAGE_ROOT / "usr" / "share" / "pihero" / "avahi"
render_script = load_script(SCRIPT)


class TestRender:
    def test_uses_the_name_for_both_services(self):
        files = render_script.render(TEMPLATES, "Foo", "AirPort4", None)

        assert sorted(files) == ["device-info.service", "ssh.service"]
        assert all('<name replace-wildcards="yes">Foo</name>' in content for content in files.values())

    def test_escapes_xml_special_characters_in_the_name(self):
        files = render_script.render(TEMPLATES, "Foo & <Bar>", "AirPort4", None)

        assert "Foo &amp; &lt;Bar&gt;" in files["ssh.service"]
        ET.fromstring(files["ssh.service"])

    def test_keeps_unicode_names(self):
        files = render_script.render(TEMPLATES, "(ノಠ益ಠ)ノ彡 ⬬", "AirPort4", None)

        assert "(ノಠ益ಠ)ノ彡 ⬬" in files["device-info.service"]
        ET.fromstring(files["device-info.service"])

    def test_publishes_the_model_record_as_plain_text(self):
        files = render_script.render(TEMPLATES, "Foo", "MacPro7,1@ECOLOR=226,226,224", None)

        records = txt_records(files["device-info.service"])
        assert records == ["model=MacPro7,1@ECOLOR=226,226,224"]

    def test_escapes_xml_special_characters_in_the_model(self):
        files = render_script.render(TEMPLATES, "Foo", "A&B<C>", None)

        assert txt_records(files["device-info.service"]) == ["model=A&B<C>"]

    def test_adds_the_machine_record_when_known(self):
        files = render_script.render(TEMPLATES, "Foo", "AirPort4", "Raspberry Pi Zero W Rev 1.1")

        assert txt_records(files["device-info.service"]) == ["model=AirPort4", "machine=Raspberry Pi Zero W Rev 1.1"]

    def test_omits_the_machine_record_when_unknown(self):
        files = render_script.render(TEMPLATES, "Foo", "AirPort4", None)

        assert not any(record.startswith("machine=") for record in txt_records(files["device-info.service"]))


class TestMachine:
    def test_reads_the_device_tree_model_and_strips_the_trailing_nul(self, tmp_path):
        model = tmp_path / "model"
        model.write_bytes(b"Raspberry Pi Zero W Rev 1.1\x00")

        assert render_script.machine(model) == "Raspberry Pi Zero W Rev 1.1"

    def test_is_none_on_a_missing_file(self, tmp_path):
        assert render_script.machine(tmp_path / "model") is None


class TestWriteIfChanged:
    def test_writes_once_and_reports_no_change_afterwards(self, tmp_path):
        target = tmp_path / "x.service"

        first = render_script.write_if_changed(target, "a")
        second = render_script.write_if_changed(target, "a")

        assert (first, second) == (True, False)
        assert target.read_text() == "a"


class TestCli:
    def test_renders_both_services_with_defaults(self, tmp_path):
        services = tmp_path / "services"
        services.mkdir()

        result = cli(services, tmp_path / "missing-model", env={})

        assert result.returncode == 0, result.stderr
        device_info = ET.parse(services / "pihero-device-info.service").getroot()
        ET.parse(services / "pihero-ssh.service")
        assert txt_records(ET.tostring(device_info, encoding="unicode")) == ["model=AirPort4"]

    def test_applies_model_from_the_environment_unchanged(self, tmp_path):
        services = tmp_path / "services"
        services.mkdir()
        model_file = tmp_path / "model"
        model_file.write_bytes(b"QEMU virt\x00")

        cli(services, model_file, env={"MODEL": "MacPro7,1@ECOLOR=226,226,224"})

        assert txt_records((services / "pihero-device-info.service").read_text()) == ["model=MacPro7,1@ECOLOR=226,226,224", "machine=QEMU virt"]


def txt_records(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    return [element.text for element in root.iter("txt-record")]


def cli(services: Path, model_file: Path, env: dict) -> subprocess.CompletedProcess:
    base_env = {key: value for key, value in os.environ.items() if key != "MODEL"}
    full_env = {**base_env, "PIHERO_AVAHI_SERVICES": str(services), "PIHERO_AVAHI_TEMPLATES": str(TEMPLATES), "PIHERO_DEVICE_TREE_MODEL": str(model_file), **env}
    return subprocess.run([sys.executable, str(SCRIPT)], env=full_env, capture_output=True, text=True)
