"""pytest plugin: target selection, tier markers, and the testinfra host fixture shared by all package tests."""

from pathlib import Path

import pytest

from . import build


def pytest_addoption(parser):
    group = parser.getgroup("pihero")
    group.addoption("--target", choices=["podman", "vm", "ssh"], default="podman", help="where 'installed' and 'boot' tests run")
    group.addoption("--target-uri", default=None, help="for --target=ssh: user@host[:port]")
    group.addoption("--platform", default="linux/arm64", help="for --target=podman: container platform")
    group.addoption("--qemu-accel", default="hvf", help="for --target=vm: hvf or tcg")
    group.addoption("--device", default=None, help="for --target=vm: device directory (default: the testkit's all-features device)")
    group.addoption("--display", default="800x480", help="for --target=vm: the virtual display's WIDTHxHEIGHT, or none")
    group.addoption("--keep", action="store_true", help="keep the VM or container running after the session")


def pytest_configure(config):
    config.addinivalue_line("markers", "tier0: runs on the Mac against fixtures and the tools container, no target")
    config.addinivalue_line("markers", "installed: runs against any target with the packages installed (podman, vm, ssh)")
    config.addinivalue_line("markers", "boot: cross-cutting checks that need a booted VM or device (vm, ssh)")
    config.addinivalue_line("markers", "mutating: changes the target's state; skipped on --target=ssh")
    if config.getoption("--target") == "vm":
        from .vm import parse_display

        parse_display(config.getoption("--display"))


def package_of(path: Path) -> str | None:
    """Returns the name of the package whose directory holds path, or None for a path outside every package."""
    return next((build.package_name(directory) for directory in path.parents if build.is_package(directory)), None)


def pytest_collection_modifyitems(config, items):
    target = config.getoption("--target")
    installed, uri = None, config.getoption("--target-uri")
    if target == "ssh" and items:
        from .ssh import installed_packages

        try:
            installed = installed_packages(uri)
        except SystemExit as exc:  # pytest reports a SystemExit from a hook as an internal error
            raise pytest.UsageError(str(exc)) from None
        under_test = {package for item in items if (package := package_of(item.path))}
        if under_test and under_test.isdisjoint(installed):
            raise pytest.UsageError(f"none of the packages under test is installed on {uri}; flash a device file to put Pi Hero on it")
    for item in items:
        if "mutating" in item.keywords and target == "ssh":
            item.add_marker(pytest.mark.skip(reason="mutating test on a real device"))
        if "boot" in item.keywords and target == "podman":
            item.add_marker(pytest.mark.skip(reason="needs a booted system"))
        if installed is not None and (package := package_of(item.path)) and package not in installed:
            item.add_marker(pytest.mark.skip(reason=f"{package} is not installed on {uri}"))


@pytest.fixture(scope="session")
def version(request) -> str:
    """The version the tests assert against: what a real device has installed, otherwise what gets built."""
    if request.config.getoption("--target") == "ssh":
        from .ssh import installed_version

        return installed_version(request.config.getoption("--target-uri"))
    return build.version_from_git()


@pytest.fixture(scope="session")
def packages(request, version):
    if request.config.getoption("--target") == "ssh":
        return []
    return build.build_all(version)


@pytest.fixture(scope="session")
def target(request, version, packages):
    kind = request.config.getoption("--target")
    keep = request.config.getoption("--keep")
    if kind == "podman":
        from .podman import SystemdContainer

        container = SystemdContainer(request.config.getoption("--platform"), build.DIST, packages).start()
        container.install(packages)
        yield container
        if not keep:
            container.stop()
    elif kind == "vm":
        from .vm import provisioned_vm

        with provisioned_vm(packages, request.config.getoption("--device"), request.config.getoption("--qemu-accel"), keep, display=request.config.getoption("--display")) as vm:
            yield vm
    else:
        from .ssh import SshTarget

        yield SshTarget(request.config.getoption("--target-uri"), packages)


@pytest.fixture
def host(target):
    return target.host
