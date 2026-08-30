"""Dependency-free deterministic PEP 517 backend for the bootstrap package."""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import os
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

NAME = "planeon-harness-contracts"
NORMALIZED_NAME = "planeon_harness_contracts"
VERSION = "0.1.0"
DIST_INFO = f"{NORMALIZED_NAME}-{VERSION}.dist-info"
ARCHIVE_ROOT = f"{NAME}-{VERSION}"
FIXED_EPOCH = 946684800
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "src" / "planeon_harness_contracts"
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


def _metadata() -> bytes:
    return (
        "Metadata-Version: 2.4\n"
        f"Name: {NAME}\n"
        f"Version: {VERSION}\n"
        "Summary: Offline-first public contracts for the Planeon MAS harness platform\n"
        "License-Expression: Apache-2.0\n"
        "Requires-Python: ==3.12.*\n"
        "Description-Content-Type: text/markdown\n"
        "\n"
        "Planeon MAS Harness Contracts bootstrap package.\n"
    ).encode("utf-8")


def _wheel_metadata() -> bytes:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: planeon-harness-contracts deterministic-backend 1\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ).encode("utf-8")


def _entry_points() -> bytes:
    return b"[console_scripts]\nharnessctl = planeon_harness_contracts.cli:main\n"


def _source_epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        return FIXED_EPOCH
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("SOURCE_DATE_EPOCH must be an integer") from exc
    return max(value, 315532800)


def _package_files() -> Iterable[tuple[str, bytes]]:
    for path in sorted(PACKAGE_ROOT.rglob("*"), key=lambda item: item.relative_to(PACKAGE_ROOT).as_posix()):
        if path.is_file() and not path.is_symlink() and not any(part in EXCLUDED_PARTS for part in path.parts):
            relative = path.relative_to(PACKAGE_ROOT).as_posix()
            if not relative.endswith((".pyc", ".pyo")):
                yield f"planeon_harness_contracts/{relative}", path.read_bytes()


def _record_digest(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}"


def _wheel_files() -> list[tuple[str, bytes]]:
    files = list(_package_files())
    files.extend(
        [
            (f"{DIST_INFO}/METADATA", _metadata()),
            (f"{DIST_INFO}/WHEEL", _wheel_metadata()),
            (f"{DIST_INFO}/entry_points.txt", _entry_points()),
            (f"{DIST_INFO}/licenses/LICENSE", (PROJECT_ROOT / "LICENSE").read_bytes()),
        ]
    )
    return sorted(files, key=lambda item: item[0])


def _record(files: Iterable[tuple[str, bytes]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    for name, data in files:
        writer.writerow((name, _record_digest(data), len(data)))
    writer.writerow((f"{DIST_INFO}/RECORD", "", ""))
    return stream.getvalue().encode("utf-8")


def _zip_info(name: str, epoch: int) -> zipfile.ZipInfo:
    import time

    stamp = time.gmtime(epoch)[:6]
    info = zipfile.ZipInfo(name, stamp)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def get_requires_for_build_wheel(config_settings: dict[str, Any] | None = None) -> list[str]:
    """Declare the intentionally empty build dependency set."""

    del config_settings
    return []


def get_requires_for_build_sdist(config_settings: dict[str, Any] | None = None) -> list[str]:
    """Declare the intentionally empty sdist dependency set."""

    del config_settings
    return []


def get_requires_for_build_editable(config_settings: dict[str, Any] | None = None) -> list[str]:
    """Declare the intentionally empty editable dependency set."""

    del config_settings
    return []


def prepare_metadata_for_build_wheel(
    metadata_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    """Write deterministic wheel metadata for frontends that request it."""

    del config_settings
    destination = Path(metadata_directory) / DIST_INFO
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "METADATA").write_bytes(_metadata())
    (destination / "WHEEL").write_bytes(_wheel_metadata())
    (destination / "entry_points.txt").write_bytes(_entry_points())
    return DIST_INFO


def prepare_metadata_for_build_editable(
    metadata_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    """Use the same deterministic metadata for an editable frontend request."""

    return prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    """Build a byte-reproducible pure-Python wheel."""

    del config_settings, metadata_directory
    destination = Path(wheel_directory)
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"{NORMALIZED_NAME}-{VERSION}-py3-none-any.whl"
    files = _wheel_files()
    files.append((f"{DIST_INFO}/RECORD", _record(files)))
    epoch = _source_epoch()
    with zipfile.ZipFile(destination / filename, "w", strict_timestamps=True) as archive:
        for name, data in files:
            archive.writestr(_zip_info(name, epoch), data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return filename


def build_editable(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    """Build a regular deterministic wheel for offline editable requests."""

    return build_wheel(wheel_directory, config_settings, metadata_directory)


def _sdist_paths() -> Iterable[Path]:
    for path in sorted(PROJECT_ROOT.rglob("*"), key=lambda item: item.relative_to(PROJECT_ROOT).as_posix()):
        relative = path.relative_to(PROJECT_ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.is_file() and not path.is_symlink() and not path.name.endswith((".pyc", ".pyo")):
            yield path


def _tar_info(name: str, size: int, epoch: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = epoch
    return info


def build_sdist(
    sdist_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    """Build a byte-reproducible gzip-compressed source archive."""

    del config_settings
    destination = Path(sdist_directory)
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"{NAME}-{VERSION}.tar.gz"
    epoch = _source_epoch()
    with (destination / filename).open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=epoch, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                entries = [(f"{ARCHIVE_ROOT}/PKG-INFO", _metadata())]
                entries.extend(
                    (
                        f"{ARCHIVE_ROOT}/{path.relative_to(PROJECT_ROOT).as_posix()}",
                        path.read_bytes(),
                    )
                    for path in _sdist_paths()
                )
                for name, data in sorted(entries, key=lambda item: item[0]):
                    archive.addfile(
                        _tar_info(name, len(data), epoch),
                        io.BytesIO(data),
                    )
    return filename
