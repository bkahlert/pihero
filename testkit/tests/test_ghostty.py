from pathlib import Path

import pytest

from pihero_testkit import ghostty

pytestmark = pytest.mark.tier0


class TestBinary:
    def test_prefers_the_dir_a_ghostty_shell_exports(self, tmp_path, monkeypatch):
        exported = executable(tmp_path / "exported" / "ghostty")
        executable(tmp_path / "path" / "ghostty")
        monkeypatch.setenv("GHOSTTY_BIN_DIR", str(exported.parent))
        monkeypatch.setenv("PATH", str(tmp_path / "path"))

        found = ghostty.binary()

        assert found == exported

    def test_skips_an_exported_dir_without_the_binary(self, tmp_path, monkeypatch):
        on_path = executable(tmp_path / "path" / "ghostty")
        monkeypatch.setenv("GHOSTTY_BIN_DIR", str(tmp_path / "moved"))
        monkeypatch.setenv("PATH", str(on_path.parent))

        found = ghostty.binary()

        assert found == on_path

    def test_falls_back_to_the_app_bundle(self, tmp_path, monkeypatch):
        bundle = tmp_path / "Ghostty.app"
        bundled = executable(bundle / "Contents" / "MacOS" / "ghostty")
        without_ghostty(tmp_path, monkeypatch)
        monkeypatch.setattr(ghostty, "APP_BUNDLES", (tmp_path / "Other.app", bundle))

        found = ghostty.binary()

        assert found == bundled

    def test_is_none_without_ghostty(self, tmp_path, monkeypatch):
        without_ghostty(tmp_path, monkeypatch)

        found = ghostty.binary()

        assert found is None


class TestCachedHosts:
    def test_lists_the_entries(self, tmp_path):
        script, _ = fake_ghostty(tmp_path, ["pi@busy-screen.local", "netmon.local"])

        hosts = ghostty.cached_hosts(script)

        assert hosts == ["pi@busy-screen.local", "netmon.local"]

    def test_is_empty_on_an_empty_cache(self, tmp_path):
        script, _ = fake_ghostty(tmp_path, [])

        hosts = ghostty.cached_hosts(script)

        assert hosts == []


class TestEntriesFor:
    def test_matches_the_host_with_and_without_local_for_any_user(self):
        entries = ghostty.entries_for("busy-screen", ["pi@busy-screen.local", "root@busy-screen", "busy-screen.local", "pi@netmon.local"])

        assert entries == ["pi@busy-screen.local", "root@busy-screen", "busy-screen.local"]

    def test_ignores_hosts_that_merely_start_with_the_name(self):
        entries = ghostty.entries_for("busy-screen", ["pi@busy-screen-2.local", "pi@busy-screen.local.example"])

        assert entries == []

    def test_ignores_case_as_mdns_does(self):
        entries = ghostty.entries_for("Busy-Screen", ["pi@busy-screen.local"])

        assert entries == ["pi@busy-screen.local"]


class TestForget:
    def test_removes_the_hosts_entries_and_reports_them(self, tmp_path, monkeypatch):
        script, log = fake_ghostty(tmp_path, ["pi@busy-screen.local", "pi@netmon.local", "busy-screen"])
        monkeypatch.setenv("GHOSTTY_BIN_DIR", str(script.parent))
        said = []

        removed = ghostty.forget("busy-screen", said.append)

        assert removed == ["pi@busy-screen.local", "busy-screen"]
        assert log.read_text().splitlines() == ["+ssh-cache", "+ssh-cache --remove=pi@busy-screen.local", "+ssh-cache --remove=busy-screen"]
        assert said == ["forgot pi@busy-screen.local, busy-screen in Ghostty's ssh-terminfo cache; the next ssh from Ghostty installs its terminfo again"]

    def test_is_silent_when_the_host_is_not_cached(self, tmp_path, monkeypatch):
        script, log = fake_ghostty(tmp_path, ["pi@netmon.local"])
        monkeypatch.setenv("GHOSTTY_BIN_DIR", str(script.parent))
        said = []

        removed = ghostty.forget("busy-screen", said.append)

        assert removed == []
        assert log.read_text().splitlines() == ["+ssh-cache"]
        assert said == []

    def test_does_nothing_without_ghostty(self, tmp_path, monkeypatch):
        without_ghostty(tmp_path, monkeypatch)
        said = []

        removed = ghostty.forget("busy-screen", said.append)

        assert removed == []
        assert said == []


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def without_ghostty(tmp_path, monkeypatch) -> None:
    (tmp_path / "empty").mkdir(exist_ok=True)
    monkeypatch.delenv("GHOSTTY_BIN_DIR", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(ghostty, "APP_BUNDLES", ())


def fake_ghostty(tmp_path, cached: list[str]) -> tuple[Path, Path]:
    """Returns a `ghostty` that answers `+ssh-cache` like the real one and the file it logs every call to."""
    log = tmp_path / "calls"
    listing = f"Cached hosts ({len(cached)}):\\n" + "".join(f"  {entry} (today)\\n" for entry in cached) if cached else "No hosts in cache.\\n"
    script = tmp_path / "bin" / "ghostty"
    script.parent.mkdir()
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{log}'\n"
        'case "$*" in\n'
        f"  '+ssh-cache') printf '{listing}' ;;\n"
        "  *) printf \"Removed '%s' from cache.\\n\" \"${2#--remove=}\" ;;\n"
        "esac\n"
    )
    script.chmod(0o755)
    return script, log
