#!/usr/bin/env python3
"""Generate deterministic lifecycle/status tables and the release index."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from planeon_harness_contracts.canonical import canonical_json_bytes  # noqa: E402
from planeon_harness_contracts.compatibility_data_harness_v1 import (  # noqa: E402
    deprecation_document,
    mapping_document,
)
from planeon_harness_contracts.state_machine import (  # noqa: E402
    generated_lifecycle_contract,
    generated_status_contract,
)

GENERATED_TARGETS = (
    Path("generated/lifecycle-transitions.json"),
    Path("generated/status-semantics.json"),
    Path("generated/contract-index.json"),
)
COMPATIBILITY_TARGETS = (
    Path("compatibility/data-harness-v1/mappings.json"),
    Path("compatibility/data-harness-v1/deprecation.json"),
)
RELEASE_MANIFEST = Path("contracts/release-manifest.json")


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _json_contract_paths() -> tuple[Path, ...]:
    roots = (
        ROOT / "schemas" / "v1alpha1" / "composition",
        ROOT / "schemas" / "v1alpha1" / "lifecycle",
        ROOT / "schemas" / "v1alpha1" / "status",
        ROOT / "schemas" / "v1alpha1" / "events",
        ROOT / "openapi",
        ROOT / "asyncapi",
    )
    paths: list[Path] = []
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"contract directory is missing or linked: {root.relative_to(ROOT)}")
        entries = tuple(sorted(root.iterdir(), key=lambda item: item.name))
        for entry in entries:
            if entry.is_symlink() or not entry.is_file() or entry.suffix != ".json":
                raise ValueError(f"contract entry must be regular JSON: {entry.relative_to(ROOT)}")
            paths.append(entry.relative_to(ROOT))
    return tuple(sorted(paths, key=lambda item: item.as_posix()))


def _read_canonical_source(path: Path) -> bytes:
    try:
        value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid contract JSON: {path.as_posix()}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"contract root must be an object: {path.as_posix()}")
    return canonical_json_bytes(value)


def expected_outputs() -> dict[Path, bytes]:
    """Build every generated file in dependency order without writing."""

    outputs: dict[Path, bytes] = {
        GENERATED_TARGETS[0]: canonical_json_bytes(generated_lifecycle_contract()),
        GENERATED_TARGETS[1]: canonical_json_bytes(generated_status_contract()),
        COMPATIBILITY_TARGETS[0]: canonical_json_bytes(mapping_document()),
        COMPATIBILITY_TARGETS[1]: canonical_json_bytes(deprecation_document()),
    }
    entries: list[dict[str, Any]] = []
    for path in _json_contract_paths():
        content = _read_canonical_source(path)
        role = "PREDECESSOR_CONTRACT" if "/composition/" in path.as_posix() else "PUBLIC_CONTRACT"
        entries.append({"path": path.as_posix(), "sha256": _sha256(content), "role": role})
    for path in GENERATED_TARGETS[:2]:
        entries.append({"path": path.as_posix(), "sha256": _sha256(outputs[path]), "role": "GENERATED_AUTHORITY"})
    entries.sort(key=lambda entry: entry["path"])
    outputs[GENERATED_TARGETS[2]] = canonical_json_bytes(
        {
            "schemaVersion": "harness.planeon.ai/contract-index/v1alpha1",
            "canonicalization": "SORTED_UTF8_JSON_V1",
            "packetId": "CON-005",
            "entries": entries,
        }
    )
    release_entries = [
        *entries,
        {
            "path": GENERATED_TARGETS[2].as_posix(),
            "sha256": _sha256(outputs[GENERATED_TARGETS[2]]),
            "role": "GENERATED_AUTHORITY",
        },
    ]
    for path in COMPATIBILITY_TARGETS:
        release_entries.append(
            {
                "path": path.as_posix(),
                "sha256": _sha256(outputs[path]),
                "role": "PUBLIC_COMPATIBILITY_CONTRACT",
            }
        )
    release_sources = {
        Path("src/planeon_harness_contracts/compatibility_data_harness_v1.py"): "MODEL_IMPLEMENTATION",
        Path("src/planeon_harness_contracts/commands/compatibility.json"): "COMMAND_REGISTRATION",
        Path("src/planeon_harness_contracts/events.py"): "EVENT_VALIDATOR",
        Path("src/planeon_harness_contracts/state_machine.py"): "MODEL_IMPLEMENTATION",
        Path("src/planeon_harness_contracts/validation.py"): "COMMAND_DISPATCH",
        Path("docs/lifecycle.md"): "DOCUMENTATION",
        Path("docs/migrations/data-harness-v1.md"): "MIGRATION_GUIDE",
        Path("docs/status-projections.md"): "DOCUMENTATION",
    }
    for path, role in release_sources.items():
        absolute = ROOT / path
        if not absolute.is_file() or absolute.is_symlink():
            raise ValueError(f"release source is missing or linked: {path.as_posix()}")
        release_entries.append(
            {"path": path.as_posix(), "sha256": _sha256(absolute.read_bytes()), "role": role}
        )
    release_entries.sort(key=lambda entry: entry["path"])
    outputs[RELEASE_MANIFEST] = canonical_json_bytes(
        {
            "schemaVersion": "harness.planeon.ai/contract-release-manifest/v1alpha1",
            "apiVersion": "harness.planeon.ai/v1alpha1",
            "releaseVersion": "0.1.0",
            "packetId": "CON-006",
            "canonicalization": "SORTED_UTF8_JSON_V1",
            "artifactState": "SOURCE_CONTRACT_ONLY",
            "runtimeEvidenceIncluded": False,
            "tenantAcceptanceIncluded": False,
            "entries": release_entries,
        }
    )
    return outputs


def _check(outputs: dict[Path, bytes]) -> None:
    for path, expected in outputs.items():
        absolute = ROOT / path
        if not absolute.is_file() or absolute.is_symlink():
            raise ValueError(f"generated output is missing or linked: {path.as_posix()}")
        if absolute.read_bytes() != expected:
            raise ValueError(f"generated output is stale: {path.as_posix()}")
    generated = ROOT / "generated"
    actual = {path.relative_to(ROOT) for path in generated.iterdir() if path.is_file()}
    if actual != set(GENERATED_TARGETS):
        raise ValueError("generated directory contains an undeclared output")
    compatibility = ROOT / "compatibility" / "data-harness-v1"
    if not compatibility.is_dir() or compatibility.is_symlink():
        raise ValueError("compatibility output directory is missing or linked")
    compatibility_entries = tuple(compatibility.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in compatibility_entries):
        raise ValueError("compatibility directory contains a non-regular output")
    actual_compatibility = {path.relative_to(ROOT) for path in compatibility_entries}
    if actual_compatibility != set(COMPATIBILITY_TARGETS):
        raise ValueError("compatibility directory contains an undeclared output")


def _write(outputs: dict[Path, bytes]) -> None:
    for path, content in outputs.items():
        absolute = ROOT / path
        absolute.parent.mkdir(parents=True, exist_ok=True)
        if absolute.is_file() and not absolute.is_symlink() and absolute.read_bytes() == content:
            continue
        absolute.write_bytes(content)


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare without modifying files")
    namespace = parser.parse_args(argv)
    try:
        outputs = expected_outputs()
        if namespace.check:
            _check(outputs)
        else:
            _write(outputs)
    except (OSError, ValueError) as exc:
        print(f"contract generation refused: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "accepted": True,
                "mode": "CHECK" if namespace.check else "WRITE",
                "outputs": {
                    path.as_posix(): _sha256(content)
                    for path, content in sorted(outputs.items(), key=lambda item: item[0].as_posix())
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
