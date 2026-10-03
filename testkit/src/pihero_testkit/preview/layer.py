"""The disk a preview's VM boots from: the app's device file provisioned once per base image and kept as a read-only layer."""

import hashlib
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import device_file, locks, prepare
from ..vm import provisioned_vm
from . import kiosk
from .api import KioskApp

CACHE = Path.home() / ".cache" / "pihero" / "preview"
DEVICE_DIR = "preview-device"


@dataclass(frozen=True)
class Layer:
    """A provisioned disk: the overlay of the root filesystem and the boot image the VM boots with."""

    rootfs: Path
    bootfs: Path


def name(base_id: str, user_data: str) -> str:
    """Return the layer's name: twelve hex digits of the base image's id and the rendered user-data."""
    return hashlib.sha256(f"{base_id}\0{user_data}".encode()).hexdigest()[:12]


def layer_for(base: prepare.BaseImage, user_data: str, cache: Path) -> Layer:
    """Return where the layer for `base` and `user_data` lives under `cache`."""
    directory = cache / name(base.rootfs.parent.name, user_data)
    return Layer(directory / "rootfs.qcow2", directory / "bootfs.img")


def build_layer(device: Path, accel: str, display: tuple[int, int], into: Path) -> None:
    """Provision the device directory `device` in a VM, power it off, and copy its disk and boot image into `into`."""
    with provisioned_vm([], device, accel, keep=False, display=f"{display[0]}x{display[1]}") as vm:
        vm.ssh("sudo poweroff", timeout=30)
        vm.wait_exit()
        shutil.copy(vm.overlay, into / "rootfs.qcow2")
        shutil.copy(vm.bootfs, into / "bootfs.img")


def ensure(app: KioskApp, cache: Path = CACHE, accel: str = "hvf", *, build: Callable[[Path, str, tuple[int, int], Path], None] = build_layer, prepare_base=prepare.prepare, report: Callable[[str], None] = lambda message: print(message, file=sys.stderr, flush=True)) -> Layer:
    """Return the layer for the current base image and the app's device file, building it under a lock when the cache has none.

    Raise ValueError when the device file does not install pihero-kiosk.
    """
    user_data = app.user_data()
    if kiosk.PACKAGE not in user_data:
        raise ValueError(f"the preview's device file must install {kiosk.PACKAGE}; add it to its packages")
    base = prepare_base()
    device = device_file.write(app.root / "dist" / "preview" / DEVICE_DIR, user_data)
    layer = layer_for(base, user_data, cache)
    if layer.rootfs.exists() and layer.bootfs.exists():
        return layer
    directory = layer.rootfs.parent
    with locks.held(cache / f"{directory.name}.lock"):
        if layer.rootfs.exists() and layer.bootfs.exists():
            return layer
        report("building the preview's base layer, once per base image and device file (about 2.5 minutes)")
        building = cache / f"{directory.name}.building"
        shutil.rmtree(building, ignore_errors=True)
        building.mkdir(parents=True)
        build(device, accel, app.display, building)
        for artifact in building.iterdir():
            artifact.chmod(0o444)
        os.replace(building, directory)
    return layer
