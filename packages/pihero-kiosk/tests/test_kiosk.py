from pathlib import Path

import pytest
from pihero_testkit.scripts import load_script

pytestmark = pytest.mark.tier0
kiosk = load_script(Path(__file__).parents[1] / "root/usr/lib/pihero/kiosk")


def test_a_file_url_is_reachable_when_the_file_exists(tmp_path):
    page = tmp_path / "index.html"
    page.write_text("<html></html>")

    assert kiosk.reachable(page.as_uri())


def test_a_file_url_is_not_reachable_when_the_file_is_missing(tmp_path):
    assert not kiosk.reachable((tmp_path / "missing.html").as_uri())


def test_an_http_url_nobody_serves_is_not_reachable():
    assert not kiosk.reachable("http://127.0.0.1:9/", timeout=1)


def test_wait_for_returns_at_once_when_reachable(tmp_path):
    page = tmp_path / "index.html"
    page.write_text("x")
    slept = []

    assert kiosk.wait_for(page.as_uri(), sleep=slept.append)
    assert slept == []


def test_wait_for_sleeps_until_the_deadline_and_gives_up(tmp_path):
    clock = iter([0, 2, 4, 6])
    slept = []

    ok = kiosk.wait_for((tmp_path / "missing").as_uri(), interval=2, deadline=5, sleep=slept.append, now=lambda: next(clock))

    assert not ok
    assert slept == [2, 2, 2]


def test_main_execs_cog_on_drm_with_the_configured_url(tmp_path):
    page = tmp_path / "index.html"
    page.write_text("x")
    calls = []

    rc = kiosk.main([], environ={"URL": page.as_uri(), "COG_ARGS": "--scale=2"}, execvp=lambda file, args: calls.append((file, args)))

    assert rc == 0
    assert calls == [("cog", ["cog", "--platform=drm", "--scale=2", page.as_uri()])]


def test_main_falls_back_to_the_default_page_without_a_url(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(kiosk, "reachable", lambda url, timeout=5.0: True)

    kiosk.main([], environ={}, execvp=lambda file, args: calls.append(args))

    assert calls == [["cog", "--platform=drm", "file:///usr/share/pihero/kiosk/index.html"]]
