"""Immutable taxonomy registry, catalog loader, and canonical lock verifier."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from planeon_harness_contracts.errors import ContractRegistryError
from planeon_harness_contracts.validation import (
    API_VERSION,
    CATALOG_KINDS,
    ValidationResult,
    reject_unregistered_kind,
    validate_catalog,
    validate_taxonomy_resource,
)

CATALOG_DOCUMENT_VERSION = "harness.planeon.ai/catalog-document/v1alpha1"
CATALOG_LOCK_VERSION = "harness.planeon.ai/catalog-lock/v1alpha1"
CATALOG_VERSION = "0.1.0"
CANONICALIZATION = "SORTED_UTF8_JSON_V1"

Validator = Callable[[str, Mapping[str, Any]], ValidationResult]


@dataclass(frozen=True, slots=True)
class RegisteredContract:
    """A contract kind and its in-process, side-effect-free validator."""

    kind: str
    api_version: str
    validator: Validator

    def __post_init__(self) -> None:
        if not self.kind or not self.kind.replace("-", "").isalnum():
            raise ContractRegistryError(f"invalid contract kind: {self.kind!r}")
        if not self.api_version.startswith("harness.planeon.ai/"):
            raise ContractRegistryError(
                f"contract api_version must use harness.planeon.ai authority: {self.api_version!r}"
            )
        if not callable(self.validator):
            raise ContractRegistryError("contract validator must be callable")


class ContractRegistry:
    """Read-only registry with duplicate rejection and fail-closed lookup."""

    def __init__(self, contracts: Iterable[RegisteredContract] = ()) -> None:
        by_kind: dict[str, RegisteredContract] = {}
        for contract in contracts:
            if contract.kind in by_kind:
                raise ContractRegistryError(f"duplicate contract kind: {contract.kind}")
            by_kind[contract.kind] = contract
        self._contracts = MappingProxyType(dict(sorted(by_kind.items())))

    @classmethod
    def empty(cls) -> ContractRegistry:
        """Construct the CON-001-compatible registry with zero public kinds."""

        return cls()

    @classmethod
    def taxonomy(cls) -> ContractRegistry:
        """Construct the closed CON-002 registry of four v1alpha1 kinds."""

        return cls(
            RegisteredContract(kind=kind, api_version=API_VERSION, validator=validate_taxonomy_resource)
            for kind in sorted(CATALOG_KINDS)
        )

    @property
    def contracts(self) -> Mapping[str, RegisteredContract]:
        """Return an immutable, lexically ordered mapping."""

        return self._contracts

    @property
    def kinds(self) -> tuple[str, ...]:
        """Return registered kind names in deterministic order."""

        return tuple(self._contracts)

    def validate(self, kind: str, document: Mapping[str, Any]) -> ValidationResult:
        """Validate through the registered kind or reject unknown authority."""

        contract = self._contracts.get(kind)
        if contract is None:
            return reject_unregistered_kind(kind, document)
        return contract.validator(kind, document)


def canonical_json_bytes(value: object) -> bytes:
    """Return the repository's documented UTF-8, sorted-key canonical form."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _catalog_files(catalog_root: Path) -> tuple[Path, ...]:
    if not catalog_root.is_dir() or catalog_root.is_symlink():
        raise ValueError("catalog root must be a regular directory")
    paths = tuple(sorted(catalog_root.rglob("*"), key=lambda item: item.relative_to(catalog_root).as_posix()))
    linked = [path for path in paths if path.is_symlink()]
    if linked:
        raise ValueError(f"catalog links are forbidden: {linked[0].relative_to(catalog_root).as_posix()}")
    unexpected = [path for path in paths if path.is_file() and path.suffix != ".json"]
    if unexpected:
        raise ValueError(
            f"catalog contains a non-JSON file: {unexpected[0].relative_to(catalog_root).as_posix()}"
        )
    files = tuple(path for path in paths if path.is_file() and path.suffix == ".json")
    if not files:
        raise ValueError("catalog contains no JSON documents")
    return files


def _load_document(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid catalog JSON: {path.as_posix()}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"catalog document must be an object: {path.as_posix()}")
    if set(document) != {"schemaVersion", "resources"}:
        raise ValueError(f"catalog document fields are closed: {path.as_posix()}")
    if document["schemaVersion"] != CATALOG_DOCUMENT_VERSION:
        raise ValueError(f"unknown catalog document version: {path.as_posix()}")
    resources = document["resources"]
    if not isinstance(resources, list) or not resources:
        raise ValueError(f"catalog document resources must be a non-empty list: {path.as_posix()}")
    if not all(isinstance(resource, dict) for resource in resources):
        raise ValueError(f"catalog resources must be objects: {path.as_posix()}")
    return document


def load_catalog(catalog_root: Path) -> tuple[dict[str, Any], ...]:
    """Load regular JSON catalog documents in deterministic path order."""

    resources: list[dict[str, Any]] = []
    for path in _catalog_files(catalog_root):
        resources.extend(_load_document(path)["resources"])
    return tuple(resources)


def expected_catalog_lock(catalog_root: Path) -> dict[str, Any]:
    """Compute the deterministic lock without modifying the catalog or lock file."""

    entries: list[dict[str, Any]] = []
    for path in _catalog_files(catalog_root):
        document = _load_document(path)
        resource_ids = sorted(
            resource["metadata"]["id"]
            for resource in document["resources"]
            if isinstance(resource.get("metadata"), dict)
            and isinstance(resource["metadata"].get("id"), str)
        )
        digest = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
        entries.append(
            {
                "path": path.relative_to(catalog_root).as_posix(),
                "digest": f"sha256:{digest}",
                "resourceIds": resource_ids,
            }
        )
    catalog_digest = hashlib.sha256(canonical_json_bytes(entries)).hexdigest()
    return {
        "schemaVersion": CATALOG_LOCK_VERSION,
        "catalogVersion": CATALOG_VERSION,
        "canonicalization": CANONICALIZATION,
        "entries": entries,
        "catalogDigest": f"sha256:{catalog_digest}",
    }


def _read_lock(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("catalog lock must be a regular file")
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("catalog lock is invalid JSON") from exc
    if not isinstance(lock, dict):
        raise ValueError("catalog lock must be an object")
    return lock


def catalog_command(argv: Sequence[str]) -> int:
    """Implement the read-only ``harnessctl catalog lock --check`` command."""

    if tuple(argv) != ("lock", "--check"):
        print("usage: harnessctl catalog lock --check", file=sys.stderr)
        return 2
    catalog_root = Path("catalog")
    lock_path = Path("contracts/catalog.lock.json")
    try:
        resources = load_catalog(catalog_root)
        validation = validate_catalog(resources)
        if not validation.accepted:
            first = validation.issues[0]
            raise ValueError(f"catalog validation failed: {first.code}: {first.message}")
        expected = expected_catalog_lock(catalog_root)
        actual = _read_lock(lock_path)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"catalog lock refused: {exc}", file=sys.stderr)
        return 1
    if actual != expected:
        print("catalog lock refused: canonical lock is stale", file=sys.stderr)
        return 1
    counts = Counter(resource["kind"] for resource in resources)
    print(
        json.dumps(
            {
                "accepted": True,
                "catalogDigest": expected["catalogDigest"],
                "entries": len(expected["entries"]),
                "resources": dict(sorted(counts.items())),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0
