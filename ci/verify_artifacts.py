#!/usr/bin/env python3
"""Verify deterministic wheel/sdist structure and print immutable digests."""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from planeon_harness_contracts import build_backend  # noqa: E402


def sha256(path: Path) -> str:
    """Hash a file without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("wheel entries are not uniquely sorted")
        timestamps = {info.date_time for info in archive.infolist()}
        if len(timestamps) != 1:
            raise ValueError("wheel timestamps are not deterministic")
        if not any(name.endswith(".dist-info/RECORD") for name in names):
            raise ValueError("wheel RECORD is absent")


def _verify_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("sdist entries are not uniquely sorted")
        if len({member.mtime for member in members}) != 1:
            raise ValueError("sdist timestamps are not deterministic")
        if any(member.uid != 0 or member.gid != 0 or member.uname or member.gname for member in members):
            raise ValueError("sdist ownership metadata is not normalized")


def _two_build_digests() -> tuple[dict[str, str], dict[str, str]]:
    results: list[dict[str, str]] = []
    for _index in range(2):
        with tempfile.TemporaryDirectory(prefix="con-001-reproducible-") as directory:
            root = Path(directory)
            wheel = root / build_backend.build_wheel(str(root))
            sdist = root / build_backend.build_sdist(str(root))
            results.append({wheel.name: sha256(wheel), sdist.name: sha256(sdist)})
    return results[0], results[1]


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: verify_artifacts.py DIST_DIRECTORY", file=sys.stderr)
        return 2
    directory = Path(arguments[0])
    wheel = directory / "planeon_harness_contracts-0.1.0-py3-none-any.whl"
    sdist = directory / "planeon-harness-contracts-0.1.0.tar.gz"
    try:
        if not wheel.is_file() or wheel.is_symlink() or not sdist.is_file() or sdist.is_symlink():
            raise ValueError("expected wheel and sdist are absent or linked")
        if sorted(path.name for path in directory.iterdir() if path.is_file()) != sorted((wheel.name, sdist.name)):
            raise ValueError("dist contains an undeclared artifact")
        _verify_wheel(wheel)
        _verify_sdist(sdist)
        first, second = _two_build_digests()
        if first != second or first != {wheel.name: sha256(wheel), sdist.name: sha256(sdist)}:
            raise ValueError("two-build artifact digests are not reproducible")
    except (OSError, tarfile.TarError, zipfile.BadZipFile, ValueError) as exc:
        print(f"artifact verification refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"artifacts": first, "reproducibleBuilds": 2, "status": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

