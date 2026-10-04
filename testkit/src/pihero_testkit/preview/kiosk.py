"""Pure helpers for the kiosk a preview drives: its settings file, its journal, the Web Inspector's address, and the package's names."""

import re
import time
import urllib.request

UNIT = "pihero-kiosk"
PACKAGE = "pihero-kiosk"
CONF = "/etc/pihero/kiosk.conf"
INSPECTOR_PORT = 2999
LOADED = "Loaded successfully"
DEVELOPER_EXTRAS = "--enable-developer-extras=true"
SESSION_KEYS = ("WEBKIT_INSPECTOR_HTTP_SERVER", "GSETTINGS_BACKEND")
VIDEO_MODE_KEY = "COG_PLATFORM_DRM_VIDEO_MODE"
INSPECTOR = re.compile(r"window\.open\('Main\.html\?ws=' \+ window\.location\.host \+ '(?P<path>/socket/[^']+)'")


def unquote(value: str) -> str:
    """Return `value` without one pair of matching double or single quotes around it."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def session_conf(current: str, url: str, inspector_port: int = INSPECTOR_PORT, video_mode: str | None = None) -> str:
    """Return the kiosk.conf `current` for a session: URL set to `url` (added when absent), developer extras in front of
    COG_ARGS (quoted, unquoted or absent), and the inspector address and GSETTINGS_BACKEND=memory replacing any such lines.

    With `video_mode` (WIDTHxHEIGHT), COG_PLATFORM_DRM_VIDEO_MODE is set to it, replacing any such line; without, a present
    line stays as it is."""
    lines, has_url, has_args = [], False, False
    for line in current.splitlines():
        name, separator, value = line.partition("=")
        name = name.strip()
        if separator and name == "URL":
            line, has_url = f"URL={url}", True
        elif separator and name == "COG_ARGS":
            words = " ".join(word for word in (DEVELOPER_EXTRAS, unquote(value)) if word)
            line, has_args = f'COG_ARGS="{words}"', True
        elif separator and (name in SESSION_KEYS or (video_mode and name == VIDEO_MODE_KEY)):
            continue
        lines.append(line)
    if not has_url:
        lines.insert(0, f"URL={url}")
    if not has_args:
        lines.append(f'COG_ARGS="{DEVELOPER_EXTRAS}"')
    if video_mode:
        lines.append(f"{VIDEO_MODE_KEY}={video_mode}")
    lines += [f"WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:{inspector_port}", "GSETTINGS_BACKEND=memory"]
    return "\n".join(lines) + "\n"


def parse_conf(text: str) -> dict[str, str]:
    """Return the assignments of an EnvironmentFile, quotes stripped, comments, blanks and lines without = skipped."""
    result = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        result[name.strip()] = unquote(value)
    return result


def inspector_url(listing: str, address: str) -> str | None:
    """Return the Web Inspector's URL for the first target in the inspector's page list at `address`, or None without one."""
    match = INSPECTOR.search(listing)
    return f"http://{address}/Main.html?ws={address}{match['path']}" if match else None


def fetch_listing(address: str) -> str:
    """Return the inspector's page list at `address`, or an empty string when it does not answer."""
    try:
        return urllib.request.urlopen(f"http://{address}/", timeout=2).read().decode()
    except OSError:
        return ""


def wait_for_inspector(address: str, timeout: float = 30, fetch=fetch_listing, sleep=time.sleep, clock=time.monotonic) -> str:
    """Return the Web Inspector's URL once its page list names a target, or the list's own URL after `timeout` seconds."""
    deadline = clock() + timeout
    while clock() < deadline:
        found = inspector_url(fetch(address), address)
        if found:
            return found
        sleep(1)
    return f"http://{address}/"


def open_command(app: str, url: str) -> list[str]:
    """Return the command that opens `url` in the macOS application `app`."""
    return ["open", "-a", app, url]


def since_command() -> str:
    """Return the command printing the target's clock in the form journalctl's --since takes."""
    return "date '+%Y-%m-%d %H:%M:%S'"


def loaded_command(since: str) -> str:
    """Return the command counting the kiosk's page loads since `since`."""
    return f"sudo journalctl -u {UNIT} --since '{since}' --no-pager | grep -c '{LOADED}'"


def loaded(output: str) -> bool:
    """Return whether the output of `loaded_command` counts at least one load."""
    return output.strip() not in ("", "0")
