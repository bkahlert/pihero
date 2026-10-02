import time
import urllib.request

import pytest

from pihero_testkit import repo

pytestmark = pytest.mark.tier0


def test_release_options_default_to_pihero():
    options = repo.release_options()

    assert "APT::FTPArchive::Release::Origin=pihero" in options
    assert "APT::FTPArchive::Release::Label=pihero" in options
    assert "APT::FTPArchive::Release::Description=Pi Hero packages" in options


def test_release_options_take_an_apps_origin():
    options = repo.release_options(origin="netmon", label="netmon", description="Netmon packages")

    assert "APT::FTPArchive::Release::Origin=netmon" in options
    assert "APT::FTPArchive::Release::Label=netmon" in options
    assert "APT::FTPArchive::Release::Description=Netmon packages" in options
    assert "APT::FTPArchive::Release::Suite=stable" in options


def test_release_options_name_the_architectures_the_repository_carries():
    options = repo.release_options()

    assert "APT::FTPArchive::Release::Architectures=all arm64" in options


class TestServer:
    def test_runs_next_to_another_server(self, server, tmp_path):
        second = repo.Server(tmp_path)
        second.close()

        assert second.port != server.port

    def test_serves_the_directory(self, server):
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/Packages") as response:
            body = response.read()

        assert body == b"Package: pihero\n"

    def test_names_the_source_as_the_guest_reaches_it(self, server):
        assert server.url == f"http://10.0.2.2:{server.port}/"

    def test_closes_at_once(self, tmp_path):
        server = repo.Server(tmp_path)
        started = time.monotonic()

        server.close()

        assert time.monotonic() - started < 0.25

    @pytest.fixture
    def server(self, tmp_path):
        (tmp_path / "Packages").write_text("Package: pihero\n")
        server = repo.Server(tmp_path)
        yield server
        server.close()
