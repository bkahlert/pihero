"""Flat apt repository: index generation with apt-ftparchive, signing, and a local HTTP server for the VM."""

import functools
import http.server
import shlex
import shutil
import threading
from pathlib import Path

from . import tools



def release_options(origin: str = "pihero", label: str = "pihero", description: str = "Pi Hero packages") -> list[str]:
    """apt-ftparchive options for the Release file; an application publishing its own repository passes its name."""
    return [
        "-o", f"APT::FTPArchive::Release::Origin={origin}",
        "-o", f"APT::FTPArchive::Release::Label={label}",
        "-o", "APT::FTPArchive::Release::Suite=stable",
        "-o", "APT::FTPArchive::Release::Architectures=all",
        "-o", f"APT::FTPArchive::Release::Description={description}",
    ]


def build_repo(debs: list[Path], out: Path, *, origin: str = "pihero", label: str = "pihero", description: str = "Pi Hero packages") -> Path:
    out.mkdir(parents=True, exist_ok=True)
    for deb in debs:
        shutil.copy(deb, out / deb.name)
    relative = out.relative_to(Path.cwd())
    options = shlex.join(release_options(origin, label, description))
    tools.run(["sh", "-c", f"cd /work/{relative} && apt-ftparchive packages . > Packages && gzip -kf Packages && apt-ftparchive {options} release . > Release"])
    return out


def sign_repo(repo: Path, private_key: Path) -> None:
    relative = repo.relative_to(Path.cwd())
    tools.run(
        ["sh", "-c", f"gpg --batch --import /key/{private_key.name} && cd /work/{relative} && gpg --batch --yes -abs -o Release.gpg Release && gpg --batch --yes --clearsign -o InRelease Release"],
        mounts=[f"{private_key.parent}:/key:ro"],
    )


class Server:
    def __init__(self, directory: Path, port: int = 8000):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.port = port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def main(argv: list[str]) -> int:
    import argparse
    import glob

    parser = argparse.ArgumentParser(description="Maintain the flat apt repository.")
    sub = parser.add_subparsers(dest="command", required=True)
    publish = sub.add_parser("publish", help="copy packages into the repo directory, regenerate and sign the index")
    publish.add_argument("--debs", required=True, help="glob of .deb files")
    publish.add_argument("--repo", required=True, help="repository directory, existing packages are kept")
    publish.add_argument("--key", required=True, help="armored private signing key")
    publish.add_argument("--origin", default="pihero", help="Release Origin, the repository's name (default: pihero)")
    publish.add_argument("--label", default="pihero", help="Release Label (default: pihero)")
    publish.add_argument("--description", default="Pi Hero packages", help="Release Description (default: Pi Hero packages)")
    args = parser.parse_args(argv)
    repo_dir = Path(args.repo).resolve()
    build_repo([Path(p) for p in sorted(glob.glob(args.debs))], repo_dir, origin=args.origin, label=args.label, description=args.description)
    sign_repo(repo_dir, Path(args.key).resolve())
    print(repo_dir)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
