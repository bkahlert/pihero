import pytest

from pihero_testkit.preview import kiosk

pytestmark = pytest.mark.tier0
URL = "http://10.0.2.2:8081/?broker.host=10.0.2.2&broker.port=8080"
QUOTED = 'URL=http://localhost/\nCOG_PLATFORM_DRM_VIDEO_MODE=800x480\nCOG_ARGS="--doc-viewer --web-mem-limit=200"\nJSC_useJIT=false\n'
LISTING = """<html><body><ul><li><a href="javascript:void(0)" onclick="window.open('Main.html?ws=' + window.location.host + '/socket/1/1/WebPage', '_blank')">Inspect</a></li></ul></body></html>"""


class TestSessionConf:
    def test_replaces_the_url_and_keeps_the_other_lines(self):
        text = kiosk.session_conf(QUOTED, URL)

        assert text.startswith(f"URL={URL}\nCOG_PLATFORM_DRM_VIDEO_MODE=800x480\n")
        assert "JSC_useJIT=false\n" in text

    def test_puts_developer_extras_in_front_of_quoted_cog_args(self):
        text = kiosk.session_conf(QUOTED, URL)

        assert 'COG_ARGS="--enable-developer-extras=true --doc-viewer --web-mem-limit=200"\n' in text

    def test_quotes_unquoted_cog_args(self):
        text = kiosk.session_conf("URL=http://localhost/\nCOG_ARGS=--platform-params=renderer=gles\n", URL)

        assert 'COG_ARGS="--enable-developer-extras=true --platform-params=renderer=gles"\n' in text

    def test_takes_single_quoted_cog_args(self):
        text = kiosk.session_conf("URL=http://localhost/\nCOG_ARGS='--doc-viewer'\n", URL)

        assert 'COG_ARGS="--enable-developer-extras=true --doc-viewer"\n' in text

    def test_adds_cog_args_when_absent(self):
        text = kiosk.session_conf("URL=http://localhost/\n", URL)

        assert 'COG_ARGS="--enable-developer-extras=true"\n' in text

    def test_adds_the_url_when_absent(self):
        text = kiosk.session_conf("", URL)

        assert text.startswith(f"URL={URL}\n")

    def test_ends_with_the_inspector_and_the_memory_settings_backend(self):
        text = kiosk.session_conf(QUOTED, URL)

        assert text.endswith("WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:2999\nGSETTINGS_BACKEND=memory\n")

    def test_takes_another_inspector_port(self):
        text = kiosk.session_conf(QUOTED, URL, inspector_port=3999)

        assert "WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:3999\n" in text

    def test_replaces_session_lines_already_present(self):
        once = kiosk.session_conf(QUOTED, URL)

        twice = kiosk.session_conf(once, URL)

        assert twice.count("WEBKIT_INSPECTOR_HTTP_SERVER=") == 1
        assert twice.count("GSETTINGS_BACKEND=") == 1
        assert twice.count("--enable-developer-extras=true") == 2

    def test_keeps_comments_and_blank_lines(self):
        text = kiosk.session_conf("# the kiosk\n\nURL=http://localhost/\n", URL)

        assert text.startswith(f"# the kiosk\n\nURL={URL}\n")


class TestUnquote:
    @pytest.mark.parametrize("value, expected", [('"a b"', "a b"), ("'a b'", "a b"), ("a b", "a b"), ('"', '"'), ("", "")])
    def test_strips_one_pair_of_matching_quotes(self, value, expected):
        assert kiosk.unquote(value) == expected


class TestParseConf:
    def test_reads_assignments_without_quotes_and_skips_comments_and_blanks(self):
        conf = kiosk.parse_conf("# note\n\nURL=http://x/\nCOG_ARGS=\"--a --b\"\nbroken line\n")

        assert conf == {"URL": "http://x/", "COG_ARGS": "--a --b"}


class TestInspectorUrl:
    def test_is_the_inspector_of_the_first_target(self):
        url = kiosk.inspector_url(LISTING, "127.0.0.1:2999")

        assert url == "http://127.0.0.1:2999/Main.html?ws=127.0.0.1:2999/socket/1/1/WebPage"

    def test_is_none_without_a_target(self):
        assert kiosk.inspector_url("<html></html>", "127.0.0.1:2999") is None


class TestWaitForInspector:
    def test_returns_the_inspector_once_the_list_names_a_target(self):
        listings = iter(["<html></html>", LISTING])

        url = kiosk.wait_for_inspector("127.0.0.1:2999", fetch=lambda address: next(listings), sleep=lambda s: None, clock=counter())

        assert url.endswith("/socket/1/1/WebPage")

    def test_falls_back_to_the_list_after_the_timeout(self):
        url = kiosk.wait_for_inspector("127.0.0.1:2999", timeout=3, fetch=lambda address: "", sleep=lambda s: None, clock=counter())

        assert url == "http://127.0.0.1:2999/"


class TestOpenCommand:
    def test_opens_the_url_in_the_application(self):
        assert kiosk.open_command("Safari", "http://127.0.0.1:2999/") == ["open", "-a", "Safari", "http://127.0.0.1:2999/"]


class TestJournal:
    def test_counts_the_loaded_lines_of_the_kiosk_since_a_time(self):
        command = kiosk.loaded_command("2026-10-03 10:00:00")

        assert command == "sudo journalctl -u pihero-kiosk --since '2026-10-03 10:00:00' --no-pager | grep -c 'Loaded successfully'"

    @pytest.mark.parametrize("output, expected", [("", False), ("0\n", False), ("1\n", True), ("3\n", True)])
    def test_loaded_reads_the_count(self, output, expected):
        assert kiosk.loaded(output) is expected

    def test_since_is_the_guests_clock_in_journalctl_form(self):
        assert kiosk.since_command() == "date '+%Y-%m-%d %H:%M:%S'"


def counter(step: float = 1.0):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock
