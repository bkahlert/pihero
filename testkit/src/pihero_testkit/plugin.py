"""pytest plugin: markers shared by all Pi Hero tests. Target fixtures are added in later tasks."""


def pytest_configure(config):
    config.addinivalue_line("markers", "tier0: runs on the Mac against fixtures and the tools container, no target")
    config.addinivalue_line("markers", "installed: runs against any target with the packages installed (podman, vm, ssh)")
    config.addinivalue_line("markers", "boot: cross-cutting checks that need a booted VM or device (vm, ssh)")
    config.addinivalue_line("markers", "mutating: changes the target's state; skipped on --target=ssh")
