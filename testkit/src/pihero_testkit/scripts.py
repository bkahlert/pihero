"""Imports extensionless Python scripts, such as /usr/lib/pihero/bootconfig, as modules for unit tests."""

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType


def load_script(path: Path) -> ModuleType:
    name = f"pihero_script_{path.name}_{abs(hash(str(path.resolve())))}"
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module
