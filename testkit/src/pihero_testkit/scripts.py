"""Imports extensionless Python scripts, such as /usr/lib/pihero/bootconfig, as modules for unit tests."""

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType


class _NoBytecodeLoader(SourceFileLoader):
    # Scripts live in package trees that nfpm ships verbatim, so a __pycache__ next to them would land in the .deb.
    def set_data(self, path, data, *, _mode=0o666):
        pass


def load_script(path: Path) -> ModuleType:
    name = f"pihero_script_{path.name}_{abs(hash(str(path.resolve())))}"
    loader = _NoBytecodeLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module
