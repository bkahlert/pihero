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
