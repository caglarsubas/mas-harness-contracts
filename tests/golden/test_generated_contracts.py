from __future__ import annotations

import json

from planeon_harness_contracts.canonical import canonical_json_bytes
from scripts.generate_contracts import RELEASE_MANIFEST, expected_outputs, main
from tests.model.schema_support import ROOT, load_json


def test_generated_outputs_are_exact_and_check_mode_passes(capsys) -> None:
    outputs = expected_outputs()
    assert set(outputs) == {
        RELEASE_MANIFEST,
        *(path.relative_to(ROOT) for path in sorted((ROOT / "generated").glob("*.json"))),
    }
    for path, expected in outputs.items():
        assert (ROOT / path).read_bytes() == expected
    assert main(("--check",)) == 0
    assert '"mode":"CHECK"' in capsys.readouterr().out


def test_every_generated_json_file_is_canonical() -> None:
    for path in (*sorted((ROOT / "generated").glob("*.json")), ROOT / RELEASE_MANIFEST):
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


def test_contract_index_contains_five_openapi_and_one_asyncapi_document() -> None:
    index = load_json(ROOT / "generated/contract-index.json")
    paths = {entry["path"] for entry in index["entries"]}
    assert len({path for path in paths if path.startswith("openapi/")}) == 5
    assert paths & {"asyncapi/harness-events.asyncapi.json"}
    assert "schemas/v1alpha1/composition/compiled-profile-document.schema.json" in paths
    assert {
        entry["role"]
        for entry in index["entries"]
        if entry["path"].startswith("schemas/v1alpha1/composition/")
    } == {"PREDECESSOR_CONTRACT"}
    assert all(entry["sha256"].startswith("sha256:") for entry in index["entries"])
