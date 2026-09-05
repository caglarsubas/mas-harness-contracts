from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from planeon_harness_contracts.canonical import canonical_json_bytes
from scripts.generate_contracts import RELEASE_MANIFEST, _check, expected_outputs, main
from tests.model.schema_support import ROOT, load_json


# Independent predecessor obligations, not imported from the generator under test.
MANDATORY_OUTPUTS = {
    Path("generated/lifecycle-transitions.json"),
    Path("generated/status-semantics.json"),
    Path("generated/contract-index.json"),
    Path("compatibility/data-harness-v1/mappings.json"),
    Path("compatibility/data-harness-v1/deprecation.json"),
    Path("contracts/release-manifest.json"),
}
MANDATORY_APIS = {
    "openapi/control-plane.openapi.json", "openapi/distribution.openapi.json",
    "openapi/operator.openapi.json", "openapi/status.openapi.json",
    "openapi/trust.openapi.json", "asyncapi/harness-events.asyncapi.json",
}
REGRESSION_INPUTS = ROOT / "contracts/regression-inputs"


def _require_raw_digest(path: Path, expected_digest: str) -> None:
    assert path.is_file() and not path.is_symlink()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_digest, path.as_posix()


def _require_output_inventory(outputs: dict[Path, bytes], root: Path) -> None:
    actual = {Path("contracts/release-manifest.json")}
    for relative in ("generated", "compatibility/data-harness-v1"):
        directory = root / relative
        assert directory.is_dir() and not directory.is_symlink()
        for path in directory.iterdir():
            assert path.is_file() and not path.is_symlink() and path.suffix == ".json"
            actual.add(path.relative_to(root))
    assert MANDATORY_OUTPUTS <= actual
    assert set(outputs) == actual


def _require_api_inventory(index: dict, root: Path) -> None:
    paths = [entry["path"] for entry in index["entries"]]
    assert len(paths) == len(set(paths)), "duplicate index entry"
    actual: set[str] = set()
    for relative in ("openapi", "asyncapi"):
        directory = root / relative
        assert directory.is_dir() and not directory.is_symlink()
        for path in directory.iterdir():
            assert path.is_file() and not path.is_symlink() and path.suffix == ".json"
            actual.add(path.relative_to(root).as_posix())
    assert MANDATORY_APIS <= actual, "dropped predecessor API"
    assert {path for path in paths if path.startswith(("openapi/", "asyncapi/"))} == actual
    for entry in index["entries"]:
        if entry["path"] in actual:
            content = canonical_json_bytes(load_json(root / entry["path"]))
            assert entry["sha256"] == "sha256:" + hashlib.sha256(content).hexdigest()
            assert entry["role"] == "PUBLIC_CONTRACT"


def _copy_generation_inputs(destination: Path) -> None:
    for relative in (
        "schemas", "openapi", "asyncapi", "src", "docs",
        "tests/fixtures/runtime", "tests/fixtures/status", "contracts/regression-inputs",
    ):
        shutil.copytree(ROOT / relative, destination / relative)


def _stage_outputs(root: Path, outputs: dict[Path, bytes]) -> None:
    for relative, content in outputs.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def test_generated_outputs_are_exact_and_check_mode_passes(capsys) -> None:
    outputs = expected_outputs()
    _require_output_inventory(outputs, ROOT)
    for path, expected in outputs.items():
        assert (ROOT / path).read_bytes() == expected
    assert main(("--check",)) == 0
    assert '"mode":"CHECK"' in capsys.readouterr().out


def test_every_generated_json_file_is_canonical() -> None:
    for path in (
        *sorted((ROOT / "generated").glob("*.json")),
        *sorted((ROOT / "compatibility/data-harness-v1").glob("*.json")),
        ROOT / RELEASE_MANIFEST,
    ):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert path.read_bytes() == canonical_json_bytes(value)


def test_release_manifest_covers_contract_index_without_claiming_runtime() -> None:
    manifest = load_json(ROOT / RELEASE_MANIFEST)
    paths = [entry["path"] for entry in manifest["entries"]]
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
    assert "generated/contract-index.json" in paths
    assert "src/planeon_harness_contracts/state_machine.py" in paths
    assert "src/planeon_harness_contracts/events.py" in paths
    assert manifest["artifactState"] == "SOURCE_CONTRACT_ONLY"
    assert manifest["runtimeEvidenceIncluded"] is False
    assert manifest["tenantAcceptanceIncluded"] is False


def test_contract_index_matches_independent_api_inventory_and_retains_predecessors() -> None:
    index = load_json(ROOT / "generated/contract-index.json")
    _require_api_inventory(index, ROOT)
    paths = {entry["path"] for entry in index["entries"]}
    assert "schemas/v1alpha1/composition/compiled-profile-document.schema.json" in paths
    assert {
        entry["role"]
        for entry in index["entries"]
        if entry["path"].startswith("schemas/v1alpha1/composition/")
    } == {"PREDECESSOR_CONTRACT"}
    assert all(entry["sha256"].startswith("sha256:") for entry in index["entries"])


@pytest.mark.parametrize("mutation", ["omit", "invent", "duplicate", "wrong-digest"])
def test_api_inventory_rejects_incomplete_or_invented_index(mutation: str) -> None:
    index = copy.deepcopy(load_json(ROOT / "generated/contract-index.json"))
    entry = next(item for item in index["entries"] if item["path"] == "openapi/status.openapi.json")
    if mutation == "omit":
        index["entries"].remove(entry)
    elif mutation == "invent":
        index["entries"].append({**entry, "path": "openapi/invented.openapi.json"})
    elif mutation == "duplicate":
        index["entries"].append(copy.deepcopy(entry))
    else:
        entry["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(AssertionError):
        _require_api_inventory(index, ROOT)


def test_added_local_api_is_generated_and_accepted_without_fixed_count(tmp_path: Path) -> None:
    _copy_generation_inputs(tmp_path)
    added = tmp_path / "openapi/additive-regression.openapi.json"
    added.write_bytes(canonical_json_bytes({
        "openapi": "3.1.1", "info": {"title": "Local additive regression", "version": "0.1.0"},
        "paths": {},
    }))
    outputs = expected_outputs(root=tmp_path)
    _stage_outputs(tmp_path, outputs)
    index = json.loads(outputs[Path("generated/contract-index.json")])
    _require_api_inventory(index, tmp_path)
    assert any(item["path"] == added.relative_to(tmp_path).as_posix() for item in index["entries"])
    _require_output_inventory(outputs, tmp_path)
    _check(outputs, root=tmp_path)


def test_dropped_predecessor_api_fails_even_when_index_agrees(tmp_path: Path) -> None:
    _copy_generation_inputs(tmp_path)
    (tmp_path / "openapi/status.openapi.json").unlink()
    outputs = expected_outputs(root=tmp_path)
    with pytest.raises(AssertionError, match="dropped predecessor"):
        _require_api_inventory(json.loads(outputs[Path("generated/contract-index.json")]), tmp_path)


@pytest.mark.parametrize("mutation", ["missing", "stale", "extra"])
def test_generated_check_rejects_mutated_compatibility_outputs(tmp_path: Path, mutation: str) -> None:
    outputs = expected_outputs()
    _stage_outputs(tmp_path, outputs)
    mapping = tmp_path / "compatibility/data-harness-v1/mappings.json"
    if mutation == "missing":
        mapping.unlink()
    elif mutation == "stale":
        mapping.write_text("{}\n", encoding="utf-8")
    else:
        (mapping.parent / "undeclared.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        _check(outputs, root=tmp_path)


def test_output_inventory_rejects_omitted_and_invented_outputs() -> None:
    outputs = expected_outputs()
    del outputs[Path("compatibility/data-harness-v1/mappings.json")]
    with pytest.raises(AssertionError):
        _require_output_inventory(outputs, ROOT)
    outputs = expected_outputs()
    outputs[Path("generated/invented.json")] = b"{}\n"
    with pytest.raises(AssertionError):
        _require_output_inventory(outputs, ROOT)


def test_con007_baseline_manifest_and_raw_predecessor_bytes_are_retained() -> None:
    _require_raw_digest(REGRESSION_INPUTS / "con-007-baseline.json",
                        "db816527a9eca1dae81cb91709c9917c9e47fac1dffe21509d07a702e26f1f35")
    baseline = load_json(REGRESSION_INPUTS / "con-007-baseline.json")
    frozen_bytes = (REGRESSION_INPUTS / "con-007-release-manifest.json").read_bytes()
    assert baseline["commit"] == "2146278a95344cd2a8e22596b2f315b46edffc88"
    assert hashlib.sha256(frozen_bytes).hexdigest() == baseline["manifestSha256"] == (
        "c5dd4c39d1c69d07f8d8de3d1a09584bb906172fee2d5ac20ad25ff344b0db79"
    )
    frozen = json.loads(frozen_bytes)
    current = load_json(ROOT / RELEASE_MANIFEST)
    current_paths = [entry["path"] for entry in current["entries"]]
    assert len(current_paths) == len(set(current_paths))
    current_entries = {entry["path"]: entry for entry in current["entries"]}
    boundary = baseline["implementationBoundary"]
    assert baseline["derivedIndexPaths"] == ["generated/contract-index.json"]
    exceptions = {"generated/contract-index.json", "src/planeon_harness_contracts/state_machine.py"}
    assert boundary["path"] == "src/planeon_harness_contracts/state_machine.py"
    assert set(baseline["rawFileSha256"]) == {
        *(entry["path"] for entry in frozen["entries"]), "contracts/catalog.lock.json", "uv.lock",
    }
    for entry in frozen["entries"]:
        assert entry["path"] in current_entries
        if entry["path"] not in exceptions:
            assert current_entries[entry["path"]] == entry
    for relative, expected_digest in baseline["rawFileSha256"].items():
        path = ROOT / relative
        assert path.is_file() and not path.is_symlink()
        if relative not in exceptions:
            _require_raw_digest(path, expected_digest)
    source = (ROOT / boundary["path"]).read_bytes()
    assert source.count(b"def aggregate_status(") == 1
    assert source.count(b"def generated_lifecycle_contract(") == 1
    prefix = source.split(b"def aggregate_status(")[0]
    suffix = b"def generated_lifecycle_contract(" + source.split(b"def generated_lifecycle_contract(")[1]
    assert hashlib.sha256(prefix).hexdigest() == boundary["prefixSha256"]
    assert hashlib.sha256(suffix).hexdigest() == boundary["suffixSha256"]
    implementation_digest = hashlib.sha256(source).hexdigest()
    assert current_entries[boundary["path"]] == {
        "path": boundary["path"], "role": "MODEL_IMPLEMENTATION", "sha256": "sha256:" + implementation_digest,
    }
    change_record = REGRESSION_INPUTS / "implementation-change.json"
    if implementation_digest != boundary["beforeSha256"]:
        change = load_json(change_record)
        assert change["beforeSha256"] == boundary["beforeSha256"]
        assert change["afterSha256"] == implementation_digest
        assert change["path"] == boundary["path"] and change["function"] == "aggregate_status"
        assert change["preFixEvidence"]["expected"] == "BLOCKED"
        assert change["preFixEvidence"]["actual"] == "DEGRADED"


@pytest.mark.parametrize("relative", [
    "openapi/status.openapi.json", "compatibility/data-harness-v1/mappings.json",
])
def test_changed_predecessor_wire_bytes_fail_even_when_json_is_semantically_identical(tmp_path, relative) -> None:
    baseline = load_json(REGRESSION_INPUTS / "con-007-baseline.json")
    candidate = tmp_path / "wire.json"
    original = (ROOT / relative).read_bytes()
    candidate.write_bytes(original)
    _require_raw_digest(candidate, baseline["rawFileSha256"][relative])
    candidate.write_bytes(original + b" ")
    assert json.loads(candidate.read_bytes()) == json.loads(original)
    with pytest.raises(AssertionError):
        _require_raw_digest(candidate, baseline["rawFileSha256"][relative])
