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
MODEL_INPUT_LOCK = Path("contracts/model-inputs.lock.json")
MODEL_INPUT_LOCK_SHA256 = "sha256:bd685478590aec63055fbfe7fd21732d5ba4279a8871779aee0d95dbfca04e62"
MODEL_SCHEMAS = ["chat-chunk.schema.json","chat-request.schema.json","chat-response.schema.json","common.schema.json","completion-chunk.schema.json","completion-request.schema.json","completion-response.schema.json","embedding-request.schema.json","embedding-response.schema.json","error.schema.json","health-response.schema.json","lifecycle-trace.schema.json","models-response.schema.json","ready-response.schema.json","request-binding.schema.json","rerank-request.schema.json","rerank-response.schema.json","response-event.schema.json","response-request.schema.json","response-response.schema.json","usage-observation.schema.json"]
MODEL_FIXTURES = ("schema-vectors.json", "semantic-vectors.json", "stream-vectors.json", "usage-mapping.json")


def _regular_model_input(root: Path, relative: Path) -> bytes:
    """Refuse linked/escaped input components, not just a linked final file."""
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("model input path is not repository relative")
    absolute = root
    for component in relative.parts:
        absolute = absolute / component
        if absolute.is_symlink():
            raise ValueError(f"model input is linked: {relative}")
    if not absolute.is_file():
        raise ValueError(f"model input is missing: {relative}")
    return absolute.read_bytes()


def _model_release_sources(root: Path) -> dict[Path, str]:
    raw = _regular_model_input(root, MODEL_INPUT_LOCK)
    if _sha256(raw) != MODEL_INPUT_LOCK_SHA256:
        raise ValueError("model input lock differs from the immutable authority")
    lock = json.loads(raw)
    sources = {MODEL_INPUT_LOCK: "MODEL_INPUT_LOCK"}
    expected = set()
    for entry in lock["entries"]:
        relative = Path(entry["path"])
        if relative.parent != Path("contracts/model-inputs") or relative.name in expected:
            raise ValueError("model snapshot inventory is ambiguous")
        expected.add(relative.name)
        if _sha256(_regular_model_input(root, relative)) != entry["sha256"]:
            raise ValueError(f"model snapshot digest mismatch: {relative}")
        sources[relative] = "IMMUTABLE_MODEL_INPUT"
    inventories = (("contracts/model-inputs", expected),
                   ("tests/fixtures/model", set(MODEL_FIXTURES)),
                   ("schemas/v1alpha1/model", set(MODEL_SCHEMAS)))
    for directory, names in inventories:
        absolute = root / directory
        if absolute.is_symlink() or not absolute.is_dir():
            raise ValueError(f"model input directory is missing or linked: {directory}")
        if {p.name for p in absolute.iterdir()} != names:
            raise ValueError(f"model input inventory mismatch: {directory}")
        for name in names:
            _regular_model_input(root, Path(directory) / name)
    for name in MODEL_FIXTURES:
        relative = Path("tests/fixtures/model") / name
        content = json.loads(_regular_model_input(root, relative))
        if content.get("provenance") != "INDEPENDENT_CONTRACT_VECTOR":
            raise ValueError(f"model vector provenance is invalid: {relative}")
        sources[relative] = "INDEPENDENT_CONTRACT_VECTOR"
    for name in ("model-api.md", "model-usage-compatibility.md"):
        relative = Path("docs") / name
        _regular_model_input(root, relative)
        sources[relative] = "DOCUMENTATION"
    _regular_model_input(root, Path("openapi/model.openapi.json"))
    return sources


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _json_contract_paths(root: Path = ROOT) -> tuple[Path, ...]:
    roots = (
        root / "schemas" / "v1alpha1" / "composition",
        root / "schemas" / "v1alpha1" / "lifecycle",
        root / "schemas" / "v1alpha1" / "status",
        root / "schemas" / "v1alpha1" / "events",
        root / "schemas" / "v1alpha1" / "runtime",
        root / "schemas" / "v1alpha1" / "model",
        root / "openapi",
        root / "asyncapi",
    )
    paths: list[Path] = []
    for directory in roots:
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"contract directory is missing or linked: {directory.relative_to(root)}")
        entries = tuple(sorted(directory.iterdir(), key=lambda item: item.name))
        for entry in entries:
            if entry.is_symlink() or not entry.is_file() or entry.suffix != ".json":
                raise ValueError(f"contract entry must be regular JSON: {entry.relative_to(root)}")
            paths.append(entry.relative_to(root))
    return tuple(sorted(paths, key=lambda item: item.as_posix()))


def _read_canonical_source(path: Path, root: Path = ROOT) -> bytes:
    try:
        value = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid contract JSON: {path.as_posix()}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"contract root must be an object: {path.as_posix()}")
    return canonical_json_bytes(value)


def expected_outputs(*, root: Path = ROOT) -> dict[Path, bytes]:
    """Build every generated file in dependency order without writing."""

    model_sources = _model_release_sources(root)
    outputs: dict[Path, bytes] = {
        GENERATED_TARGETS[0]: canonical_json_bytes(generated_lifecycle_contract()),
        GENERATED_TARGETS[1]: canonical_json_bytes(generated_status_contract()),
        COMPATIBILITY_TARGETS[0]: canonical_json_bytes(mapping_document()),
        COMPATIBILITY_TARGETS[1]: canonical_json_bytes(deprecation_document()),
    }
    entries: list[dict[str, Any]] = []
    for path in _json_contract_paths(root):
        content = _read_canonical_source(path, root)
        role = "PREDECESSOR_CONTRACT" if "/composition/" in path.as_posix() else "PUBLIC_CONTRACT"
        entries.append({"path": path.as_posix(), "sha256": _sha256(content), "role": role})
    for path in GENERATED_TARGETS[:2]:
        entries.append({"path": path.as_posix(), "sha256": _sha256(outputs[path]), "role": "GENERATED_AUTHORITY"})
    entries.sort(key=lambda entry: entry["path"])
    outputs[GENERATED_TARGETS[2]] = canonical_json_bytes(
        {
            "schemaVersion": "harness.planeon.ai/contract-index/v1alpha1",
            "canonicalization": "SORTED_UTF8_JSON_V1",
            "packetId": "CON-007",
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
        Path("docs/runtime-admission.md"): "DOCUMENTATION",
        Path("docs/status-projections.md"): "DOCUMENTATION",
        Path("tests/fixtures/runtime/interoperability-vectors.json"): "INTEROPERABILITY_VECTOR",
        Path("tests/fixtures/runtime/valid-admission-envelope.json"): "INTEROPERABILITY_VECTOR",
        Path("tests/fixtures/runtime/valid-admission-receipt.json"): "INTEROPERABILITY_VECTOR",
        Path("tests/fixtures/runtime/valid-budget-consumption.json"): "INTEROPERABILITY_VECTOR",
        Path("tests/fixtures/runtime/valid-replay-record.json"): "INTEROPERABILITY_VECTOR",
        Path("tests/fixtures/runtime/valid-trust-bundle.json"): "INTEROPERABILITY_VECTOR",
        Path("tests/fixtures/status/aggregation-interoperability.json"): "INDEPENDENT_CONTRACT_VECTOR",
        **model_sources,
    }
    for path, role in release_sources.items():
        absolute = root / path
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
            "extensionPacketIds": ["CON-007", "CON-FIX-001", "CON-MODEL-001"],
            "canonicalization": "SORTED_UTF8_JSON_V1",
            "artifactState": "SOURCE_CONTRACT_ONLY",
            "runtimeEvidenceIncluded": False,
            "tenantAcceptanceIncluded": False,
            "entries": release_entries,
        }
    )
    return outputs


def _check(outputs: dict[Path, bytes], *, root: Path = ROOT) -> None:
    for path, expected in outputs.items():
        absolute = root / path
        if not absolute.is_file() or absolute.is_symlink():
            raise ValueError(f"generated output is missing or linked: {path.as_posix()}")
        if absolute.read_bytes() != expected:
            raise ValueError(f"generated output is stale: {path.as_posix()}")
    generated = root / "generated"
    actual = {path.relative_to(root) for path in generated.iterdir() if path.is_file()}
    if actual != set(GENERATED_TARGETS):
        raise ValueError("generated directory contains an undeclared output")
    compatibility = root / "compatibility" / "data-harness-v1"
    if not compatibility.is_dir() or compatibility.is_symlink():
        raise ValueError("compatibility output directory is missing or linked")
    compatibility_entries = tuple(compatibility.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in compatibility_entries):
        raise ValueError("compatibility directory contains a non-regular output")
    actual_compatibility = {path.relative_to(root) for path in compatibility_entries}
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
