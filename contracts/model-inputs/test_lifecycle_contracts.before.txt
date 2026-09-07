from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from planeon_harness_contracts.state_machine import TRANSITIONS, require_transition
from tests.model.schema_support import ROOT, load_json, validator


def test_all_con005_schemas_are_valid_draft_2020_12() -> None:
    roots = ("lifecycle", "status", "events")
    paths = [
        path
        for root in roots
        for path in sorted((ROOT / "schemas" / "v1alpha1" / root).glob("*.json"))
    ]
    assert len(paths) == 16
    for path in paths:
        Draft202012Validator.check_schema(load_json(path))


@pytest.mark.parametrize(
    ("fixture", "schema"),
    [
        ("tests/fixtures/lifecycle/operation-running.json", "schemas/v1alpha1/lifecycle/operation.schema.json"),
        ("tests/fixtures/lifecycle/approval-approved.json", "schemas/v1alpha1/lifecycle/approval-request.schema.json"),
        ("tests/fixtures/lifecycle/evidence-verified.json", "schemas/v1alpha1/lifecycle/evidence-record.schema.json"),
        ("tests/fixtures/lifecycle/installation-ready.json", "schemas/v1alpha1/lifecycle/harness-installation.schema.json"),
    ],
)
def test_lifecycle_golden_resources_validate(fixture: str, schema: str) -> None:
    validator(schema).validate(load_json(ROOT / fixture))


def test_every_declared_transition_is_allowed_and_every_other_pair_is_rejected() -> None:
    for entity, states in TRANSITIONS.items():
        state_names = tuple(states)
        for from_state in state_names:
            for to_state in state_names:
                if to_state in states[from_state]:
                    require_transition(entity, from_state, to_state)
                else:
                    with pytest.raises(ValueError, match="ILLEGAL_TRANSITION"):
                        require_transition(entity, from_state, to_state)


def test_unknown_entity_and_state_fail_closed() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_LIFECYCLE_ENTITY"):
        require_transition("Unknown", "A", "B")
    with pytest.raises(ValueError, match="UNKNOWN_FROM_STATE"):
        require_transition("Operation", "UNKNOWN", "RUNNING")
    with pytest.raises(ValueError, match="UNKNOWN_TO_STATE"):
        require_transition("Operation", "PENDING", "UNKNOWN")


def test_revocation_is_terminal_for_release_installation_and_policy() -> None:
    for entity in ("BundleRelease", "HarnessInstallation", "PolicyBundle"):
        assert TRANSITIONS[entity]["REVOKED"] == ()


def test_tenant_acceptance_cannot_be_campaign_generated() -> None:
    document = load_json(ROOT / "tests/fixtures/lifecycle/evidence-verified.json")
    document["spec"].update(
        {
            "axis": "TENANT_ACCEPTANCE",
            "producerAuthority": "PLATFORM",
            "campaignGenerated": True,
        }
    )
    errors = tuple(
        validator("schemas/v1alpha1/lifecycle/evidence-record.schema.json").iter_errors(document)
    )
    assert errors
    document["spec"].update({"producerAuthority": "TENANT", "campaignGenerated": False})
    validator("schemas/v1alpha1/lifecycle/evidence-record.schema.json").validate(document)


def _external_refs(value: object) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str) and not child.startswith("#"):
                refs.append(child)
            refs.extend(_external_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_external_refs(child))
    return refs


def test_five_openapi_documents_have_local_resolvable_refs_and_no_servers() -> None:
    paths = sorted((ROOT / "openapi").glob("*.json"))
    assert [path.name for path in paths] == [
        "control-plane.openapi.json",
        "distribution.openapi.json",
        "operator.openapi.json",
        "status.openapi.json",
        "trust.openapi.json",
    ]
    for path in paths:
        document = load_json(path)
        assert document["openapi"] == "3.1.1"
        assert "servers" not in document
        assert document["paths"]
        for reference in _external_refs(document):
            relative = reference.split("#", 1)[0]
            assert not relative.startswith(("http://", "https://"))
            assert (path.parent / relative).resolve().is_file()


def test_asyncapi_is_broker_neutral_and_covers_every_event_type() -> None:
    document = load_json(ROOT / "asyncapi/harness-events.asyncapi.json")
    assert document["asyncapi"] == "3.0.0"
    assert "servers" not in document
    addresses = {channel["address"] for channel in document["channels"].values()}
    from planeon_harness_contracts.events import EVENT_TYPES

    assert addresses == set(EVENT_TYPES)
    assert len(document["operations"]) == len(EVENT_TYPES)


def test_release_manifest_is_json_and_source_contract_only() -> None:
    manifest = json.loads((ROOT / "contracts/release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifactState"] == "SOURCE_CONTRACT_ONLY"
    assert manifest["runtimeEvidenceIncluded"] is False
    assert manifest["tenantAcceptanceIncluded"] is False
