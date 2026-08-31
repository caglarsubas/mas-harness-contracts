from __future__ import annotations

import base64
import copy
import hashlib
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from tests.model.schema_support import ROOT, load_json, validator

FIXTURES = ROOT / "tests" / "fixtures" / "runtime"
SCHEMAS = ROOT / "schemas" / "v1alpha1" / "runtime"

SCHEMA_BY_FIXTURE = {
    "valid-trust-bundle.json": "runtime-trust-bundle.schema.json",
    "valid-admission-envelope.json": "signed-admission-envelope.schema.json",
    "valid-admission-receipt.json": "runtime-admission-receipt.schema.json",
    "valid-replay-record.json": "replay-record.schema.json",
    "valid-budget-consumption.json": "budget-consumption.schema.json",
}

EXPECTED_DENIALS = {
    "malformed-unknown-member": "MALFORMED",
    "digest-mismatch": "DIGEST_MISMATCH",
    "forged-signature": "SIGNATURE_INVALID",
    "unknown-signer": "SIGNER_UNKNOWN",
    "pending-signer": "SIGNER_NOT_ACTIVE",
    "revoked-signer": "SIGNER_REVOKED",
    "wrong-key-purpose": "KEY_PURPOSE_MISMATCH",
    "not-yet-valid": "ENVELOPE_NOT_YET_VALID",
    "expired-envelope": "ENVELOPE_EXPIRED",
    "wrong-tenant": "TENANT_MISMATCH",
    "replayed-nonce": "REPLAY_DETECTED",
    "idempotency-conflict": "IDEMPOTENCY_CONFLICT",
    "over-budget": "BUDGET_EXCEEDED",
}


def _urlsafe_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _require_jcs_subset(value: Any) -> None:
    if value is None or isinstance(value, bool | int):
        if isinstance(value, int) and not isinstance(value, bool):
            assert -(2**53) + 1 <= value <= (2**53) - 1
        return
    if isinstance(value, str):
        value.encode("ascii")
        return
    if isinstance(value, list):
        for item in value:
            _require_jcs_subset(item)
        return
    assert isinstance(value, dict)
    for key, child in value.items():
        key.encode("ascii")
        _require_jcs_subset(child)


def _jcs_subset_bytes(value: dict[str, Any]) -> bytes:
    _require_jcs_subset(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _errors(schema: str, document: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(validator(f"schemas/v1alpha1/runtime/{schema}").iter_errors(document))


def test_all_runtime_schemas_are_valid_draft_2020_12() -> None:
    paths = sorted(SCHEMAS.glob("*.json"))
    assert [path.name for path in paths] == [
        "budget-consumption.schema.json",
        "common.schema.json",
        "replay-record.schema.json",
        "runtime-admission-receipt.schema.json",
        "runtime-trust-bundle.schema.json",
        "signed-admission-envelope.schema.json",
    ]
    for path in paths:
        Draft202012Validator.check_schema(load_json(path))


@pytest.mark.parametrize(("fixture", "schema"), sorted(SCHEMA_BY_FIXTURE.items()))
def test_positive_runtime_resources_validate(fixture: str, schema: str) -> None:
    validator(f"schemas/v1alpha1/runtime/{schema}").validate(load_json(FIXTURES / fixture))


def test_signed_document_vectors_have_exact_jcs_bytes_and_digests() -> None:
    vectors = load_json(FIXTURES / "interoperability-vectors.json")
    assert vectors["testOnly"] is True
    assert len(_urlsafe_decode(vectors["publicKey"])) == 32
    for vector in vectors["signedDocuments"]:
        document = load_json(FIXTURES / vector["fixture"])
        payload = _jcs_subset_bytes(document["payload"])
        assert _urlsafe_decode(vector["canonicalPayloadBase64url"]) == payload
        message = vector["domain"].encode("ascii") + b"\x00" + payload
        digest = f"sha256:{hashlib.sha256(message).hexdigest()}"
        assert vector["signedMessageDigest"] == digest
        assert document["signature"]["signedMessageDigest"] == digest
        assert document["signature"]["value"] == vector["signature"]
        assert len(_urlsafe_decode(vector["signature"])) == 64


def test_interoperability_vectors_are_public_only_and_cover_closed_denials() -> None:
    vectors = load_json(FIXTURES / "interoperability-vectors.json")
    serialized = json.dumps(vectors, sort_keys=True).casefold()
    assert "privatekey" not in serialized
    assert "private_key" not in serialized
    assert "secretkey" not in serialized
    assert "seed" not in serialized
    decisions = {item["name"]: item for item in vectors["decisionVectors"]}
    assert decisions["valid-admission"] == {
        "name": "valid-admission",
        "expectedDecision": "ADMIT",
        "expectedReason": None,
        "condition": "valid fixture, active tenant key, fresh replay state, and limits at equality",
    }
    assert {
        name: item["expectedReason"]
        for name, item in decisions.items()
        if item["expectedDecision"] == "DENY"
    } == EXPECTED_DENIALS


def test_algorithms_digests_unknown_members_and_raw_replay_material_fail_closed() -> None:
    envelope = load_json(FIXTURES / "valid-admission-envelope.json")
    envelope["signature"]["algorithm"] = "RSA"
    assert _errors("signed-admission-envelope.schema.json", envelope)

    envelope = load_json(FIXTURES / "valid-admission-envelope.json")
    envelope["payload"]["requestDigest"] = "sha256:UPPER"
    assert _errors("signed-admission-envelope.schema.json", envelope)

    envelope = load_json(FIXTURES / "valid-admission-envelope.json")
    envelope["payload"]["nonce"] = "AAAAAAAAAAAAAAAAAAAAAB"
    assert _errors("signed-admission-envelope.schema.json", envelope)

    envelope = load_json(FIXTURES / "valid-admission-envelope.json")
    envelope["payload"]["undeclared"] = True
    assert _errors("signed-admission-envelope.schema.json", envelope)

    replay = load_json(FIXTURES / "valid-replay-record.json")
    replay["spec"]["idempotencyKey"] = "raw-value"
    replay["spec"]["nonce"] = "raw-value"
    assert _errors("replay-record.schema.json", replay)


def test_trust_key_revocation_fields_are_state_bound() -> None:
    trust = load_json(FIXTURES / "valid-trust-bundle.json")
    key = trust["payload"]["keys"][0]
    key["state"] = "REVOKED"
    assert _errors("runtime-trust-bundle.schema.json", trust)
    key["revokedAt"] = "2030-03-01T00:00:00Z"
    key["revocationReason"] = "KEY_COMPROMISE"
    validator("schemas/v1alpha1/runtime/runtime-trust-bundle.schema.json").validate(trust)

    active_with_revocation = load_json(FIXTURES / "valid-trust-bundle.json")
    active_with_revocation["payload"]["keys"][0]["revokedAt"] = "2030-03-01T00:00:00Z"
    active_with_revocation["payload"]["keys"][0]["revocationReason"] = "SUPERSEDED"
    assert _errors("runtime-trust-bundle.schema.json", active_with_revocation)


def test_receipt_decision_fields_are_fail_closed() -> None:
    admitted = load_json(FIXTURES / "valid-admission-receipt.json")
    admitted["payload"]["reasonCode"] = "SIGNATURE_INVALID"
    assert _errors("runtime-admission-receipt.schema.json", admitted)

    denied = load_json(FIXTURES / "valid-admission-receipt.json")
    denied["payload"].update(
        {
            "decision": "DENY",
            "reasonCode": "BUDGET_EXCEEDED",
            "budgetConsumptionDigest": None,
            "replayRecordDigest": None,
        }
    )
    validator("schemas/v1alpha1/runtime/runtime-admission-receipt.schema.json").validate(denied)
    denied["payload"]["reasonCode"] = None
    assert _errors("runtime-admission-receipt.schema.json", denied)


def test_replay_and_budget_state_combinations_fail_closed() -> None:
    committed = load_json(FIXTURES / "valid-replay-record.json")
    committed["spec"]["receiptDigest"] = None
    assert _errors("replay-record.schema.json", committed)

    reserved = load_json(FIXTURES / "valid-replay-record.json")
    reserved["spec"]["state"] = "RESERVED"
    assert _errors("replay-record.schema.json", reserved)
    reserved["spec"]["receiptDigest"] = None
    validator("schemas/v1alpha1/runtime/replay-record.schema.json").validate(reserved)

    within = load_json(FIXTURES / "valid-budget-consumption.json")
    within["spec"]["exceededDimensions"] = ["MODEL_TOKENS"]
    assert _errors("budget-consumption.schema.json", within)

    over = copy.deepcopy(within)
    over["spec"]["decision"] = "OVER_BUDGET"
    over["spec"]["observed"]["modelTokens"] = 4097
    validator("schemas/v1alpha1/runtime/budget-consumption.schema.json").validate(over)
    over["spec"]["exceededDimensions"] = []
    assert _errors("budget-consumption.schema.json", over)


def test_key_ids_are_unique_in_golden_bundle() -> None:
    trust = load_json(FIXTURES / "valid-trust-bundle.json")
    key_ids = [key["keyId"] for key in trust["payload"]["keys"]]
    assert len(key_ids) == len(set(key_ids))


def test_release_manifest_carries_con007_as_an_additive_contract_extension() -> None:
    manifest = load_json(ROOT / "contracts" / "release-manifest.json")
    assert manifest["packetId"] == "CON-006"
    assert manifest["extensionPacketIds"] == ["CON-007"]
    entries = {entry["path"]: entry["role"] for entry in manifest["entries"]}
    assert entries["docs/runtime-admission.md"] == "DOCUMENTATION"
    assert (
        entries["tests/fixtures/runtime/interoperability-vectors.json"]
        == "INTEROPERABILITY_VECTOR"
    )
    runtime_schemas = {
        path for path in entries if path.startswith("schemas/v1alpha1/runtime/")
    }
    assert len(runtime_schemas) == 6
