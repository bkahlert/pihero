"""Builds the FAT boot partition image for a device directory and derives the kernel command line from it."""

import shutil
from pathlib import Path

from . import repo, tools

SIZE_KIB = 65536
HARNESS_OWNED = ("root=", "console=", "init=")


def build_bootfs(device_dir: Path, stock_boot: Path, out: Path, repo_port: int) -> Path:
    staging = stage(device_dir, stock_boot, out.parent / f"{out.stem}.d", repo_port)
    out.parent.mkdir(parents=True, exist_ok=True)
    tools.run(
        ["sh", "-c", f"rm -f /out/{out.name} && mkfs.vfat -n bootfs -C /out/{out.name} {SIZE_KIB} >/dev/null && mcopy -i /out/{out.name} -s /staging/* ::/"],
        mounts=[f"{out.parent}:/out", f"{staging}:/staging:ro"],
    )
    return out


def stage(device_dir: Path, stock_boot: Path, staging: Path, repo_port: int) -> Path:
    """Collects the boot partition under staging: the stock config.txt and cmdline.txt, the device directory's files with
    user-data's harness repository source pointed at repo_port, and a meta-data when the device has none."""
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    for name in ("config.txt", "cmdline.txt"):
        shutil.copy(stock_boot / name, staging / name)
    for file in device_dir.iterdir():
        if file.is_file():
            shutil.copy(file, staging / file.name)
    user_data = staging / "user-data"
    if user_data.exists():
        user_data.write_text(user_data.read_text().replace(repo.URL, repo.url(repo_port)))
    if not (staging / "meta-data").exists():
        (staging / "meta-data").write_text(f"instance-id: pihero-{device_dir.name}-1\nlocal-hostname: {device_dir.name}\n")
    return staging


def read_cmdline(image: Path) -> str:
    result = tools.run(["mtype", "-i", f"/out/{image.name}", "::/cmdline.txt"], mounts=[f"{image.parent}:/out:ro"], capture=True)
    return result.stdout.strip()


def kernel_args(cmdline: str) -> str:
    """Returns cmdline.txt adapted for QEMU virt: root by label, serial console on ttyAMA0, no firstboot init."""
    kept = [p for p in cmdline.split() if not p.startswith(HARNESS_OWNED)]
    return " ".join(["root=LABEL=rootfs", "console=ttyAMA0,115200", *kept])
