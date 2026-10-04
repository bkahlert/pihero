import pytest

from pihero_testkit import device_file, repo

pytestmark = pytest.mark.tier0

KEY = "ssh-ed25519 AAAATEST pihero-testkit"
SAMPLE = """\
#cloud-config
hostname: sample
users:
  - name: pi
    groups: users,sudo
    # the login shell
    shell: /bin/bash

    ssh_authorized_keys:
      - ssh-ed25519 AAAA...your public key... you@mac
packages:
  - pihero
  - myapp
write_files:
  - path: /etc/apt/sources.list.d/pihero.sources
    content: |
      Types: deb
      URIs: https://bkahlert.github.io/pihero/apt
      Suites: ./
  # the app's own repository
  - path: /etc/apt/sources.list.d/myapp.sources
    content: |
      Types: deb
      URIs: https://example.org/apt
      Suites: ./
  - path: /etc/pihero/kiosk.conf
    content: |
      URL=http://localhost/
runcmd:
  - echo done
"""


class TestBlock:
    def test_is_the_line_and_what_is_indented_under_it(self):
        text = device_file.block(SAMPLE, "  - path: /etc/pihero/kiosk.conf")

        assert text == "  - path: /etc/pihero/kiosk.conf\n    content: |\n      URL=http://localhost/\n"

    def test_keeps_blank_and_comment_lines_inside_the_block(self):
        text = device_file.block(SAMPLE, "users:")

        assert "    # the login shell\n" in text
        assert "\n\n    ssh_authorized_keys:\n" in text

    def test_leaves_a_comment_before_the_next_sibling_to_what_follows(self):
        text = device_file.block(SAMPLE, "  - path: /etc/apt/sources.list.d/pihero.sources")

        assert not text.endswith("  # the app's own repository\n")
        assert text.endswith("      Suites: ./\n")

    def test_keeps_a_trailing_comment_indented_deeper_than_the_block(self):
        text = device_file.block(SAMPLE.replace("      URL=http://localhost/\n", "      URL=http://localhost/\n      # trailing\n"), "  - path: /etc/pihero/kiosk.conf")

        assert text.endswith("      URL=http://localhost/\n      # trailing\n")

    def test_leaves_blank_lines_after_the_last_content_line_to_what_follows(self):
        text = device_file.block(SAMPLE.replace("      URL=http://localhost/\n", "      URL=http://localhost/\n\n"), "  - path: /etc/pihero/kiosk.conf")

        assert text.endswith("      URL=http://localhost/\n")

    def test_on_a_missing_line_raises(self):
        with pytest.raises(ValueError, match="no line 'nope:'"):
            device_file.block(SAMPLE, "nope:")


class TestDrop:
    def test_removes_the_block_and_nothing_else(self):
        text = device_file.drop(SAMPLE, "  - path: /etc/pihero/kiosk.conf")

        assert "kiosk.conf" not in text
        assert text.count("\n") == SAMPLE.count("\n") - 3


class TestWithUser:
    def test_renames_the_user_and_sets_the_key(self):
        text = device_file.with_user(SAMPLE, KEY)

        assert "  - name: pihero\n" in text
        assert "  - name: pi\n" not in text
        assert f"    ssh_authorized_keys:\n      - {KEY}\n" in text

    def test_takes_another_user_name(self):
        text = device_file.with_user(SAMPLE, KEY, user="tester")

        assert "  - name: tester\n" in text

    def test_changes_nothing_else(self):
        expected = SAMPLE.replace("  - name: pi\n", "  - name: pihero\n").replace("      - ssh-ed25519 AAAA...your public key... you@mac\n", f"      - {KEY}\n")

        text = device_file.with_user(SAMPLE, KEY)

        assert text == expected

    def test_sets_the_key_under_ssh_authorized_keys_and_not_an_earlier_list(self):
        imported = SAMPLE.replace("    ssh_authorized_keys:\n", "    ssh_import_id:\n      - gh:someone\n    ssh_authorized_keys:\n")

        text = device_file.with_user(imported, KEY)

        assert "    ssh_import_id:\n      - gh:someone\n" in text
        assert f"    ssh_authorized_keys:\n      - {KEY}\n" in text

    def test_on_a_file_without_a_users_block_raises(self):
        with pytest.raises(ValueError, match="users:"):
            device_file.with_user("#cloud-config\nhostname: x\n", KEY)

    def test_on_two_users_raises(self):
        two = SAMPLE.replace("packages:\n", "  - name: second\n    ssh_authorized_keys:\n      - ssh-ed25519 BBBB second\npackages:\n")

        with pytest.raises(ValueError, match="one user"):
            device_file.with_user(two, KEY)

    def test_on_a_users_block_without_a_key_raises(self):
        keyless = SAMPLE.replace("    ssh_authorized_keys:\n      - ssh-ed25519 AAAA...your public key... you@mac\n", "")

        with pytest.raises(ValueError, match="ssh_authorized_keys"):
            device_file.with_user(keyless, KEY)


class TestWithSource:
    def test_replaces_the_entry_with_a_trusted_source_at_the_harness_url(self):
        text = device_file.with_source(SAMPLE, "/etc/apt/sources.list.d/myapp.sources")

        assert "  - path: /etc/apt/sources.list.d/myapp.sources\n    content: |\n      Types: deb\n      URIs: http://10.0.2.2:8000/\n      Suites: ./\n      Trusted: yes\n" in text
        assert "example.org" not in text
        assert "https://bkahlert.github.io/pihero/apt" in text

    def test_takes_another_url(self):
        text = device_file.with_source(SAMPLE, "/etc/apt/sources.list.d/myapp.sources", url="http://10.0.2.2:9000/")

        assert "      URIs: http://10.0.2.2:9000/\n" in text

    def test_uses_the_repositorys_conventional_url(self):
        assert repo.URL == "http://10.0.2.2:8000/"


class TestWrite:
    def test_writes_user_data_into_the_directory_and_returns_it(self, tmp_path):
        out = device_file.write(tmp_path / "device", "#cloud-config\n")

        assert out == tmp_path / "device"
        assert [p.name for p in out.iterdir()] == ["user-data"]
        assert (out / "user-data").read_text() == "#cloud-config\n"


class TestConstants:
    def test_the_public_key_is_the_testkits(self):
        assert device_file.PUBLIC_KEY.read_text().strip().endswith(" pihero-testkit")

    def test_the_user_is_pihero(self):
        assert device_file.USER == "pihero"
