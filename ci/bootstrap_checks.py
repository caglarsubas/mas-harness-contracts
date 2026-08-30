#!/usr/bin/env python3
"""Dependency-free bootstrap and help checks for packet CON-001."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _prefetch() -> int:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit(f"CON-001 requires Python 3.12, found {sys.version.split()[0]}")
    completed = subprocess.run(
        ["uv", "--version"],
        check=False,
        shell=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0 or not completed.stdout.startswith("uv "):
        raise SystemExit("a preinstalled uv executable is required")
    lock = ROOT / "uv.lock"
    if not lock.is_file() or lock.is_symlink():
        raise SystemExit("the frozen uv.lock authority is absent or linked")
    data = lock.read_text(encoding="utf-8")
    if 'name = "planeon-harness-contracts"' not in data:
        raise SystemExit("uv.lock does not contain the package authority")
    print(
        json.dumps(
            {
                "phase": "prefetch-local-cache-only",
                "runtimeDownloads": False,
                "dependencies": 0,
                "python": sys.version.split()[0],
                "uv": completed.stdout.strip(),
                "lockSha256": _sha256(lock),
                "status": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


def _help() -> int:
    print("Available targets: prefetch zero-bill test typecheck build")
    print("All targets use closed packet-owned direct-argv descriptors.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if arguments == ("prefetch",):
        return _prefetch()
    if arguments == ("help",):
        return _help()
    print("usage: bootstrap_checks.py {prefetch|help}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

