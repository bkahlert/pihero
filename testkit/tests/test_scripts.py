from pathlib import Path

import pytest

from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0


class TestLoadScript:
    def test_exposes_functions_of_an_extensionless_script(self, tmp_path):
        script = tmp_path / "tool"
        script.write_text("def answer():\n    return 42\n\nif __name__ == '__main__':\n    raise SystemExit(answer())\n")

        module = load_script(script)

        assert module.answer() == 42

    def test_does_not_run_the_main_guard(self, tmp_path):
        script = tmp_path / "tool"
        script.write_text("if __name__ == '__main__':\n    raise SystemExit(3)\n")

        module = load_script(script)

        assert module.__name__.startswith("pihero_script_tool_")
