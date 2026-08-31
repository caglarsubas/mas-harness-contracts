from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from planeon_harness_contracts.compatibility_data_harness_v1 import (
    API_VERSION,
    CONTRACTS,
    INTENTIONAL_LOSS_CODES,
    OBSERVATION_SHA256,
    WARNING_CODES,
    CompatibilityError,
    check_fixtures,
    compatibility_command,
    convert_legacy_document,
    deprecation_document,
    mapping_document,
    restore_legacy_document,
    round_trip_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "compatibility"


def load_fixture(contract: str) -> dict[str, object]:
    return json.loads((FIXTURES / f"{contract}.round-trip.json").read_text(encoding="utf-8"))


def test_mapping_and_deprecation_are_closed_and_complete() -> None:
    mapping = mapping_document()
    assert set(mapping) == {
        "schemaVersion",
        "apiVersion",
        "conversionProfile",
        "observation",
        "fieldMappings",
        "warningCodes",
        "intentionalLosses",
        "contracts",
    }
    assert mapping["apiVersion"] == API_VERSION
    assert mapping["observation"] == {
        "reportSha256": OBSERVATION_SHA256,
        "sourceRepository": "git@github.com:caglarsubas/data-source-harness.git",
        "sourceCommit": "858281f4b845ffacfe05cdb2c40a402c237d4c54",
        "sourceCount": 29,
        "copyAuthority": "NONE",
    }
    contracts = mapping["contracts"]
    assert isinstance(contracts, list)
    assert [item["contract"] for item in contracts] == sorted(CONTRACTS)
    assert len(contracts) == 29
    assert {item["supportStatus"] for item in contracts} == {"ROUND_TRIP_SUPPORTED"}

    deprecation = deprecation_document()
    assert deprecation["contractFamily"] == "data.harness/v1"
    assert deprecation["status"] == "DEPRECATED"
    assert deprecation["firstSupportedRelease"] == "0.1.0"
    assert deprecation["supportedSeries"] == "0.x"
    assert deprecation["removalNotBeforeRelease"] == "1.0.0"
    assert deprecation["minimumNoticeDays"] == 180
    assert deprecation["warningCodes"] == list(WARNING_CODES)


def test_every_supported_contract_has_one_exact_round_trip_vector() -> None:
    fixture_paths = sorted(FIXTURES.glob("*.json"))
    assert len(fixture_paths) == len(CONTRACTS) == 29
    observed: set[str] = set()
    for path in fixture_paths:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        contract = fixture["contract"]
        evidence = round_trip_evidence(contract, fixture["legacy"])
        assert evidence["legacyRoundTrip"] == "EXACT"
        assert evidence["warningCodes"] == list(WARNING_CODES)
        assert [loss["code"] for loss in evidence["intentionalLosses"]] == list(
            INTENTIONAL_LOSS_CODES
        )
        observed.add(contract)
    assert observed == set(CONTRACTS)


def test_conversion_preserves_document_and_materializes_unambiguous_state_view() -> None:
    fixture = load_fixture("durable-action-record")
    legacy = fixture["legacy"]
    canonical = convert_legacy_document("durable-action-record", legacy)
    assert canonical["metadata"]["observationReportSha256"] == OBSERVATION_SHA256
    assert canonical["spec"]["normalizedStates"] == [
        {
            "legacySchemaPointer": "/properties/state",
            "legacyValue": "prepared",
            "canonicalValue": "PREPARED",
        }
    ]
    restored = restore_legacy_document(canonical)
    assert restored["document"] == legacy
    assert restored["report"]["legacyRoundTrip"] == "EXACT"


@pytest.mark.parametrize(
    ("contract", "mutate", "code"),
    [
        (
            "action-preview",
            lambda value: value.pop("effects"),
            "LEGACY_REQUIRED_FIELD_MISSING",
        ),
        (
            "action-preview",
            lambda value: value.update({"undeclared": True}),
            "LEGACY_UNKNOWN_FIELD",
        ),
        (
            "action-preview",
            lambda value: value.update({"schemaVersion": "data.harness/v2"}),
            "LEGACY_CONST_MISMATCH",
        ),
        (
            "connector-worker-profile",
            lambda value: value.update({"runtimeMode": "remote"}),
            "LEGACY_ENUM_MISMATCH",
        ),
        (
            "action-preview",
            lambda value: value.update({"allowed": "yes"}),
            "LEGACY_TYPE_MISMATCH",
        ),
    ],
)
def test_legacy_root_contract_refuses_observed_shape_violations(
    contract: str,
    mutate: object,
    code: str,
) -> None:
    fixture = load_fixture(contract)
    legacy = copy.deepcopy(fixture["legacy"])
    assert isinstance(legacy, dict)
    assert callable(mutate)
    mutate(legacy)
    with pytest.raises(CompatibilityError, match=code):
        convert_legacy_document(contract, legacy)


def test_unknown_contract_is_refused() -> None:
    legacy = load_fixture("action-preview")["legacy"]
    with pytest.raises(CompatibilityError, match="UNKNOWN_LEGACY_CONTRACT"):
        convert_legacy_document("unobserved-contract", legacy)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda value: value["metadata"].update({"legacySchemaGitObject": "0" * 40}),
            "CANONICAL_PROVENANCE_MISMATCH",
        ),
        (
            lambda value: value["spec"]["fields"].update({"actionId": "tampered"}),
            "CANONICAL_DOCUMENT_DIGEST_MISMATCH",
        ),
        (
            lambda value: value["spec"].update({"normalizedStates": []}),
            "CANONICAL_STATE_VIEW_MISMATCH",
        ),
        (
            lambda value: value.update({"undeclared": True}),
            "CANONICAL_ENVELOPE_INVALID",
        ),
    ],
)
def test_canonical_envelope_refuses_tampering(mutate: object, code: str) -> None:
    fixture = load_fixture("durable-action-record")
    canonical = convert_legacy_document("durable-action-record", fixture["legacy"])
    assert callable(mutate)
    mutate(canonical)
    with pytest.raises(CompatibilityError, match=code):
        restore_legacy_document(canonical)


def test_fixture_checker_reports_complete_digest_only_evidence() -> None:
    report = check_fixtures(FIXTURES)
    assert report["accepted"] is True
    assert report["checked"] == 29
    assert report["supportedContracts"] == 29
    assert report["coverageComplete"] is True
    assert report["observationReportSha256"] == OBSERVATION_SHA256
    serialized = json.dumps(report, sort_keys=True)
    assert "fixture-actionid" not in serialized
    assert "legacyDocumentDigest" in serialized
    assert "canonicalDocumentDigest" in serialized


def test_fixture_checker_refuses_incomplete_duplicate_and_unexpected_entries(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    shutil.copy2(next(FIXTURES.glob("*.json")), incomplete)
    with pytest.raises(CompatibilityError, match="FIXTURE_COVERAGE_INCOMPLETE"):
        check_fixtures(incomplete)

    duplicate = tmp_path / "duplicate"
    shutil.copytree(FIXTURES, duplicate)
    first = next(duplicate.glob("*.json"))
    shutil.copy2(first, duplicate / "duplicate.json")
    with pytest.raises(CompatibilityError, match="DUPLICATE_FIXTURE_CASE"):
        check_fixtures(duplicate)

    unexpected = tmp_path / "unexpected"
    shutil.copytree(FIXTURES, unexpected)
    (unexpected / "README.txt").write_text("not a vector", encoding="utf-8")
    with pytest.raises(CompatibilityError, match="FIXTURE_PATH_INVALID"):
        check_fixtures(unexpected)


def test_fixture_checker_refuses_links_and_non_finite_json(tmp_path: Path) -> None:
    link = tmp_path / "linked.json"
    link.symlink_to(next(FIXTURES.glob("*.json")))
    with pytest.raises(CompatibilityError, match="FIXTURE_PATH_INVALID"):
        check_fixtures(link)

    invalid = tmp_path / "non-finite.json"
    invalid.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(CompatibilityError, match="FIXTURE_JSON_INVALID"):
        check_fixtures(invalid)


def test_command_checks_complete_directory_and_refuses_bad_invocation(capsys: object) -> None:
    assert compatibility_command(("check", str(FIXTURES))) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["accepted"] is True
    assert report["coverageComplete"] is True
    assert compatibility_command(("check", str(FIXTURES / "absent.json"))) == 2
    captured = capsys.readouterr()
    assert "FIXTURE_PATH_INVALID" in captured.err


def test_published_outputs_and_release_manifest_are_digest_bound() -> None:
    mapping_path = ROOT / "compatibility" / "data-harness-v1" / "mappings.json"
    deprecation_path = ROOT / "compatibility" / "data-harness-v1" / "deprecation.json"
    assert json.loads(mapping_path.read_text(encoding="utf-8")) == mapping_document()
    assert json.loads(deprecation_path.read_text(encoding="utf-8")) == deprecation_document()

    release = json.loads((ROOT / "contracts" / "release-manifest.json").read_text(encoding="utf-8"))
    assert release["packetId"] == "CON-006"
    assert release["artifactState"] == "SOURCE_CONTRACT_ONLY"
    assert release["runtimeEvidenceIncluded"] is False
    assert release["tenantAcceptanceIncluded"] is False
    entries = {entry["path"]: entry for entry in release["entries"]}
    for path in (mapping_path, deprecation_path):
        relative = path.relative_to(ROOT).as_posix()
        assert entries[relative]["role"] == "PUBLIC_COMPATIBILITY_CONTRACT"
        assert entries[relative]["sha256"] == (
            f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        )
