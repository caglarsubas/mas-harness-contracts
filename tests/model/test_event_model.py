from __future__ import annotations

import copy
import json

from planeon_harness_contracts.events import validate_event, validate_event_path
from tests.model.schema_support import ROOT, load_json, validator


def _event() -> dict[str, object]:
    return load_json(ROOT / "tests/fixtures/lifecycle/events/01-operation-running.json")


def test_golden_event_stream_validates_semantically_and_structurally() -> None:
    events = validate_event_path(ROOT / "tests/fixtures/lifecycle/events")
    assert len(events) == 4
    schema = validator("schemas/v1alpha1/events/harness-cloud-event.schema.json")
    for event in events:
        schema.validate(event)


def test_event_rejects_cross_tenant_partition() -> None:
    event = _event()
    event["partitionkey"] = "org.other"
    assert "CROSS_TENANT_PARTITION" in validate_event(event)


def test_event_rejects_illegal_transition() -> None:
    event = _event()
    event["data"]["transition"] = {"from": "PENDING", "to": "SUCCEEDED"}
    assert "ILLEGAL_EVENT_TRANSITION" in validate_event(event)


def test_event_rejects_secret_or_business_payload_fields() -> None:
    for field in ("secret", "apiKey", "token", "rawPayload", "prompt", "modelOutput", "businessPayload"):
        event = _event()
        event["data"][field] = "redacted"
        issues = validate_event(event)
        assert "FORBIDDEN_EVENT_PAYLOAD_FIELD" in issues
        assert "EVENT_DATA_FIELDS_NOT_CLOSED" in issues


def test_event_rejects_subject_and_aggregate_mismatch() -> None:
    event = _event()
    event["subject"] = "operation.other-001"
    assert "EVENT_SUBJECT_MISMATCH" in validate_event(event)


def test_projection_event_cannot_claim_a_state_transition() -> None:
    event = load_json(ROOT / "tests/fixtures/lifecycle/events/04-projection-updated.json")
    event["data"]["transition"] = {"from": "READY", "to": "FAILED"}
    assert "PROJECTION_EVENT_HAS_TRANSITION" in validate_event(event)


def test_event_path_rejects_duplicate_ids_and_non_monotonic_sequences(tmp_path) -> None:
    first = _event()
    second = copy.deepcopy(first)
    second["id"] = "55555555-5555-4555-8555-555555555555"
    second["sequence"] = 1
    (tmp_path / "01.json").write_text(json.dumps(first), encoding="utf-8")
    (tmp_path / "02.json").write_text(json.dumps(second), encoding="utf-8")
    try:
        validate_event_path(tmp_path)
    except ValueError as exc:
        assert "strictly increasing" in str(exc)
    else:
        raise AssertionError("non-monotonic sequence was accepted")
