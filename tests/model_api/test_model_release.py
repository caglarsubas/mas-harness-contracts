from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import urldefrag, urljoin

import pytest
from jsonschema import Draft202012Validator

from scripts.generate_contracts import _model_release_sources, expected_outputs
from tests.golden.test_generated_contracts import _copy_generation_inputs
from tests.model.schema_support import ROOT, load_json

INPUTS = ROOT / "contracts/model-inputs"
LOCK_SHA = "3ad9e9ce794adecf506cb5ca8a7a1ab6a804c9dcd060a0b1fd8a11eed1734b43"
BASELINE_SHA = "5c182a3b29e5f63141301ba0ea77fe66660d0b411538615cb56d5f4c05c087e2"
LEGACY_SHA = "856b1d14e0f4d4ee84f6c4f973db412f9905559124091355bec7de85cc818080"
BEFORE = '''def _copy_generation_inputs(destination: Path) -> None:
    for relative in (
        "schemas", "openapi", "asyncapi", "src", "docs",
        "tests/fixtures/runtime", "tests/fixtures/status", "contracts/regression-inputs",
    ):
        shutil.copytree(ROOT / relative, destination / relative)
'''
AFTER = '''def _copy_generation_inputs(destination: Path) -> None:
    for relative in (
        "schemas", "openapi", "asyncapi", "src", "docs",
        "tests/fixtures/runtime", "tests/fixtures/status", "contracts/regression-inputs",
        "tests/fixtures/model", "contracts/model-inputs",
    ):
        shutil.copytree(ROOT / relative, destination / relative)
    shutil.copy2(ROOT / "contracts/model-inputs.lock.json", destination / "contracts/model-inputs.lock.json")
'''


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require_exact_fixture_edit(baseline: bytes, candidate: bytes) -> None:
    assert digest(baseline) == LEGACY_SHA
    assert baseline.count(BEFORE.encode()) == 1
    assert candidate == baseline.replace(BEFORE.encode(), AFTER.encode(), 1)


def test_exact_amended_helper_and_every_other_legacy_byte():
    baseline = (INPUTS / "test_generated_contracts.before.txt").read_bytes()
    current = (ROOT / "tests/golden/test_generated_contracts.py").read_bytes()
    require_exact_fixture_edit(baseline, current)
    amendment = load_json(INPUTS / "fixture-scope-amendment.json")
    assert amendment["testChange"]["beforeHelper"] == BEFORE
    assert amendment["testChange"]["afterHelper"] == AFTER
    assert amendment["packetDigests"]["CON-MODEL-001"] == "fff08209e76c2287c257a8d37a29aba159f82019e70f51d36bcaebf9d6805f33"
    before, suffix = baseline.split(BEFORE.encode())
    assert digest(before) == "057dd3b6f8e6f97f78957ae6e359e7fda6dd03038b4e9d05bc0f6ccfbc8e0a4c"
    assert digest(suffix) == "c1cb7096aa6e2ef684e5b9533c7493974bb47d71e48ac95ae82b9c56a85b4e3b"


@pytest.mark.parametrize("mutation", ["prefix", "suffix", "assertion", "missing-dir", "missing-lock", "extra-dir", "duplicate-dir", "conditional"])
def test_fixture_authority_rejects_widening_or_incomplete_input_copy(mutation):
    baseline = (INPUTS / "test_generated_contracts.before.txt").read_bytes()
    candidate = baseline.replace(BEFORE.encode(), AFTER.encode(), 1)
    if mutation == "prefix":
        candidate = b"# changed\n" + candidate
    elif mutation == "suffix":
        candidate += b"# changed\n"
    elif mutation == "assertion":
        candidate = candidate.replace(b"assert ", b"assert True or ", 1)
    elif mutation == "missing-dir":
        candidate = candidate.replace(b'"tests/fixtures/model", ', b"", 1)
    elif mutation == "missing-lock":
        candidate = candidate.replace(AFTER.splitlines()[-1].encode() + b"\n", b"")
    elif mutation == "extra-dir":
        candidate = candidate.replace(b'"contracts/model-inputs",', b'"contracts/model-inputs", "private",', 1)
    elif mutation == "duplicate-dir":
        candidate = candidate.replace(b'"tests/fixtures/model",', b'"tests/fixtures/model", "tests/fixtures/model",', 1)
    else:
        candidate = candidate.replace(b"        shutil.copytree(ROOT / relative, destination / relative)", b"        if (ROOT / relative).exists():\n            shutil.copytree(ROOT / relative, destination / relative)", 1)
    with pytest.raises(AssertionError):
        require_exact_fixture_edit(baseline, candidate)


def test_full_predecessor_source_and_758_collected_test_identities_remain(request):
    raw = (INPUTS / "con-fix-001-baseline.json").read_bytes()
    assert digest(raw) == BASELINE_SHA
    baseline = json.loads(raw)
    assert baseline["commit"] == "fb365aabfd8c5560e064be5d97ff9f2bcc69c57c"
    exceptions = set(baseline["derivedPaths"]) | {"tests/golden/test_generated_contracts.py"}
    assert exceptions == {"scripts/generate_contracts.py", "scripts/check_generated.py", "generated/contract-index.json", "contracts/release-manifest.json", "tests/golden/test_generated_contracts.py"}
    for name, sha in baseline["rawFileSha256"].items():
        path = ROOT / name
        assert path.is_file() and not path.is_symlink(), name
        if name not in exceptions:
            assert digest(path.read_bytes()) == sha, name
    predecessor = [item for item in request.session.items if not item.nodeid.startswith("tests/model_api/")]
    assert len(predecessor) == len({item.nodeid for item in predecessor}) == 758
    for item in request.session.items:
        assert not any(item.iter_markers(name="skip"))
        assert not any(item.iter_markers(name="skipif"))
        assert not any(item.iter_markers(name="xfail"))


def test_lock_and_predecessor_release_entries_are_immutable_and_additive():
    raw = (ROOT / "contracts/model-inputs.lock.json").read_bytes()
    assert digest(raw) == LOCK_SHA
    lock = json.loads(raw)
    assert lock["metaCommit"] == "f8137eab6acfa8b13051f1c4e548854fc7dc934f"
    assert lock["con007Commit"] == "2146278a95344cd2a8e22596b2f315b46edffc88"
    assert lock["originalSourceTests"] == "NOT_RUN_ENV_UNAVAILABLE"
    assert lock["originalSourceBehavioralParity"] == "NOT_ESTABLISHED"
    assert lock["sourceExecution"] == "DENIED" and lock["copyAuthority"] == "NONE"
    for entry in lock["entries"]:
        assert "sha256:" + digest((ROOT / entry["path"]).read_bytes()) == entry["sha256"]
    old = load_json(INPUTS / "con-fix-001-release-manifest.json")
    new = load_json(ROOT / "contracts/release-manifest.json")
    entries = {row["path"]: row for row in new["entries"]}
    assert len(entries) == len(new["entries"])
    assert new["extensionPacketIds"] == ["CON-007", "CON-FIX-001", "CON-MODEL-001"]
    for entry in old["entries"]:
        assert entry["path"] in entries
        if entry["path"] != "generated/contract-index.json":
            assert entries[entry["path"]] == entry
    assert new["artifactState"] == "SOURCE_CONTRACT_ONLY"
    assert new["runtimeEvidenceIncluded"] is new["tenantAcceptanceIncluded"] is False
    for path, role in _model_release_sources(ROOT).items():
        assert entries[path.as_posix()] == {"path": path.as_posix(), "role": role, "sha256": "sha256:" + digest((ROOT / path).read_bytes())}


@pytest.mark.parametrize("relative", [
    "contracts/model-inputs.lock.json", "contracts/model-inputs/model-usage-v2.json",
    "tests/fixtures/model/schema-vectors.json", "tests/fixtures/model/stream-vectors.json",
    "tests/fixtures/model/semantic-vectors.json", "tests/fixtures/model/usage-mapping.json",
    "schemas/v1alpha1/model/chat-request.schema.json", "openapi/model.openapi.json", "docs/model-api.md",
])
def test_generator_requires_every_model_input_without_fallback(tmp_path, relative):
    _copy_generation_inputs(tmp_path)
    (tmp_path / relative).unlink()
    with pytest.raises(ValueError):
        expected_outputs(root=tmp_path)


@pytest.mark.parametrize("mutation", ["linked-file", "linked-parent", "lock-digest", "snapshot-digest", "extra-snapshot", "extra-vector", "extra-model-schema", "false-provenance"])
def test_generator_rejects_model_input_custody_mutations(tmp_path, mutation):
    _copy_generation_inputs(tmp_path)
    snapshot = tmp_path / "contracts/model-inputs/model-usage-v2.json"
    if mutation == "linked-file":
        snapshot.unlink()
        snapshot.symlink_to(INPUTS / "model-usage-v2.json")
    elif mutation == "linked-parent":
        directory = tmp_path / "contracts/model-inputs"
        target = tmp_path / "archived-inputs"
        directory.rename(target)
        directory.symlink_to(target, target_is_directory=True)
    elif mutation == "lock-digest":
        (tmp_path / "contracts/model-inputs.lock.json").write_text("{}\n")
    elif mutation == "snapshot-digest":
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
    elif mutation.startswith("extra-"):
        directory = {"extra-snapshot": "contracts/model-inputs", "extra-vector": "tests/fixtures/model", "extra-model-schema": "schemas/v1alpha1/model"}[mutation]
        (tmp_path / directory / "extra.json").write_text("{}\n")
    else:
        path = tmp_path / "tests/fixtures/model/schema-vectors.json"
        doc = load_json(path)
        doc["provenance"] = "CAPTURED_SOURCE_RESULT"
        path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        expected_outputs(root=tmp_path)


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_all_model_schema_refs_are_registered_local_and_resolve_without_fetch():
    registry = {}
    for path in (ROOT / "schemas").rglob("*.json"):
        doc = load_json(path)
        if "$id" in doc:
            assert doc["$id"] not in registry
            registry[doc["$id"]] = doc
    for path in (ROOT / "schemas/v1alpha1/model").glob("*.json"):
        doc = load_json(path)
        Draft202012Validator.check_schema(doc)
        for node in _walk(doc):
            if "$ref" in node:
                assert not node["$ref"].startswith(("http:", "https:", "file:", "/"))
                uri, fragment = urldefrag(urljoin(doc["$id"], node["$ref"]))
                target = registry[uri]
                if fragment:
                    assert fragment.startswith("/")
                    for token in fragment[1:].split("/"):
                        target = target[token.replace("~1", "/").replace("~0", "~")]


def test_openapi_exposes_only_the_explicit_local_subset_and_signed_boundary():
    api = load_json(ROOT / "openapi/model.openapi.json")
    expected = {"/v1/models": "get", "/v1/chat/completions": "post", "/v1/completions": "post",
                "/v1/responses": "post", "/v1/embeddings": "post", "/v1/rerank": "post",
                "/healthz": "get", "/readyz": "get", "/metrics": "get"}
    assert api["openapi"] == "3.1.1" and api["servers"] == [{"url": "/"}]
    assert api["x-external-schema-resolution"] is False
    assert set(api["paths"]) == set(expected)
    assert api["components"]["securitySchemes"]["localMutualTLS"]["type"] == "mutualTLS"
    operation_ids = set()
    for path, method in expected.items():
        assert set(api["paths"][path]) == {method}
        op = api["paths"][path][method]
        assert op["security"] == [{"localMutualTLS": []}]
        assert op["operationId"] not in operation_ids
        operation_ids.add(op["operationId"])
        assert {"200", "400", "401", "403", "404", "422", "429", "500", "503", "504"} <= set(op["responses"])
        if method == "post":
            assert [p["name"] for p in op["parameters"]] == ["X-Harness-Admission", "X-Harness-Binding"]
            assert all(p["required"] is True for p in op["parameters"])
            assert op["requestBody"]["required"] is True
        for node in _walk(op):
            if "$ref" in node:
                target = (ROOT / "openapi" / node["$ref"]).resolve()
                assert target.is_relative_to(ROOT / "schemas/v1alpha1/model") and target.is_file()
    assert "text/event-stream" in api["paths"]["/v1/responses"]["post"]["responses"]["200"]["content"]
    assert "text/event-stream" not in api["paths"]["/v1/embeddings"]["post"]["responses"]["200"]["content"]
