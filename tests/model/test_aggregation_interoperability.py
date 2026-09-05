"""Independent, reviewable status vectors; never derive expected states from code."""

from __future__ import annotations

import copy
import hashlib
import itertools

import pytest

from planeon_harness_contracts.state_machine import aggregate_status
from tests.model.schema_support import ROOT, load_json, validator

VECTOR_PATH = ROOT / "tests/fixtures/status/aggregation-interoperability.json"
VECTORS = load_json(VECTOR_PATH)
SCENARIOS = {case["id"]: case for case in VECTORS["scenarios"]}
DIGEST = "sha256:" + "a" * 64


def _axis(axis_id: str, *, state: str = "PASS", required: bool = True,
          underlyingState: str | None = None) -> dict:
    return {
        "axis": axis_id, "required": required, "state": state,
        "underlyingState": underlyingState, "observedAt": "2030-01-01T00:00:00Z",
        "evidenceRefs": [],
        "waiver": ({"waiverId": "waiver.regression", "waiverDigest": DIGEST,
                    "approvedBy": "operator.regression", "expiresAt": "2030-02-01T00:00:00Z",
                    "basisCode": "APPROVED_EXCEPTION"} if state == "WAIVED" else None),
        "applicability": ({"reasonCode": "AXIS_NOT_REQUIRED", "contractRef": {
            "kind": "resource.contract", "id": "contract.axis-applicability", "digest": DIGEST,
        }} if state == "NOT_APPLICABLE" else None),
    }


def _harness(*, harnessId: str = "runtime.infrastructure", selectionState: str = "SELECTED",
             installationState: str = "READY", axisOverrides: dict | None = None) -> dict:
    overrides = axisOverrides or {}
    assert set(overrides) <= set(VECTORS["axisIds"])
    return {
        "harnessId": harnessId, "selectionState": selectionState,
        "installationState": installationState,
        "axes": [_axis(axis, **overrides.get(axis, {})) for axis in VECTORS["axisIds"]],
    }


def _assert_case(case: dict) -> None:
    harnesses = [_harness(**spec) for spec in case["harnesses"]]
    original = copy.deepcopy(harnesses)
    result = aggregate_status(harnesses, freshness_state=case["freshnessState"])
    assert {key: result[key] for key in case["expected"]} == case["expected"], case["id"]
    assert harnesses == original, "aggregation mutated caller snapshot"


def test_blocked_selection_precedes_degraded_installation_independent_vector() -> None:
    # Establish this failure under the signed runner BEFORE editing aggregate_status.
    _assert_case(SCENARIOS["blocked-selection-degraded-installation"])


def test_vector_authority_and_closed_dimensions_match_published_contract() -> None:
    assert VECTORS["evidenceClassification"] == "INDEPENDENT_CONTRACT_VECTOR"
    authority = VECTORS["authority"]
    for field in ("document", "semantics"):
        assert hashlib.sha256((ROOT / authority[field]).read_bytes()).hexdigest() == authority[field + "Sha256"]
    assert authority["baselineCommit"] == "2146278a95344cd2a8e22596b2f315b46edffc88"
    schema = load_json(ROOT / "schemas/v1alpha1/status/common.schema.json")["$defs"]
    assert VECTORS["axisIds"] == schema["evidenceAxis"]["enum"]
    assert VECTORS["installationColumns"] == schema["installationState"]["enum"]
    assert list(VECTORS["selectionInstallationExpected"]) == schema["selectionState"]["enum"]
    assert list(VECTORS["freshnessExpected"]) == schema["freshnessState"]["enum"]
    assert [row["state"] for row in VECTORS["evidenceExpected"]] == schema["evidenceState"]["enum"]
    assert VECTORS["waiverUnderlyingStates"] == (
        schema["statusAxis"]["allOf"][0]["then"]["properties"]["underlyingState"]["enum"]
    )
    for row in VECTORS["freshnessExpected"].values():
        assert set(row) == set(schema["aggregateState"]["enum"])
        assert set(row.values()) <= set(schema["aggregateState"]["enum"])
    assert len(SCENARIOS) == len(VECTORS["scenarios"])
    for expected in VECTORS["selectionInstallationExpected"].values():
        assert len(expected) == len(VECTORS["installationColumns"])
        assert set(expected) <= set(schema["aggregateState"]["enum"])
    status = load_json(ROOT / authority["semantics"])
    assert status["aggregatePrecedence"] == ["REVOKED", "FAILED", "BLOCKED", "DEGRADED", "READY", "EMPTY"]
    assert VECTORS["waiverExpected"] == status["waiverContributes"] == "DEGRADED"


@pytest.mark.parametrize("freshness", list(VECTORS["freshnessExpected"]))
@pytest.mark.parametrize("selection,installation,expected", [
    (selection, installation, expected)
    for selection, row in VECTORS["selectionInstallationExpected"].items()
    for installation, expected in zip(VECTORS["installationColumns"], row, strict=True)
])
def test_complete_selection_installation_freshness_matrix(selection, installation, expected, freshness) -> None:
    result = aggregate_status(
        [_harness(selectionState=selection, installationState=installation)], freshness_state=freshness,
    )
    assert result["aggregateState"] == VECTORS["freshnessExpected"][freshness][expected]


@pytest.mark.parametrize("axis_id", VECTORS["axisIds"])
@pytest.mark.parametrize("required", [True, False])
@pytest.mark.parametrize("row", VECTORS["evidenceExpected"], ids=lambda row: row["state"])
def test_every_evidence_state_required_and_optional_on_every_axis(axis_id, required, row) -> None:
    override = {"state": row["state"], "required": required,
                "underlyingState": "FAIL" if row["state"] == "WAIVED" else None}
    result = aggregate_status([_harness(axisOverrides={axis_id: override})], freshness_state="CURRENT")
    assert result["aggregateState"] == row["required" if required else "optional"]


@pytest.mark.parametrize("axis_id", VECTORS["axisIds"])
@pytest.mark.parametrize("required", [True, False])
@pytest.mark.parametrize("underlying", VECTORS["waiverUnderlyingStates"])
def test_every_permitted_waiver_retains_non_pass_underlying_state(axis_id, required, underlying) -> None:
    harness = _harness(axisOverrides={axis_id: {
        "state": "WAIVED", "required": required, "underlyingState": underlying,
    }})
    result = aggregate_status([harness], freshness_state="CURRENT")
    assert result["aggregateState"] == "DEGRADED"
    assert next(axis for axis in harness["axes"] if axis["axis"] == axis_id)["underlyingState"] == underlying


@pytest.mark.parametrize("case", VECTORS["scenarios"], ids=lambda case: case["id"])
def test_cross_language_scenarios_have_hand_authored_expectations(case) -> None:
    _assert_case(case)


def test_order_and_replay_do_not_change_multi_harness_result() -> None:
    case = SCENARIOS["multi-harness-precedence-and-lexical-contributors"]
    for permutation in itertools.permutations(case["harnesses"]):
        _assert_case({**case, "harnesses": list(permutation)})
        _assert_case({**case, "harnesses": list(permutation)})


@pytest.mark.parametrize("selection", ["NOT_SELECTED", "PROPOSED"])
@pytest.mark.parametrize("freshness", ["CURRENT", "STALE", "SOURCE_UNAVAILABLE"])
def test_non_contributing_failure_cannot_override_empty_snapshot(selection, freshness) -> None:
    result = aggregate_status([_harness(
        selectionState=selection, installationState="REVOKED",
        axisOverrides={"SOURCE": {"state": "FAIL", "required": True}},
    )], freshness_state=freshness)
    assert result == {"aggregateState": "EMPTY", "selectedCount": 0,
                      "contributingHarnessIds": [], "selectionCounts": {selection: 1},
                      "installationCounts": {}, "worstInstallationState": None}


@pytest.mark.parametrize("underlying", ["PASS", "NOT_APPLICABLE", None, "UNKNOWN"])
def test_invalid_waiver_underlying_state_is_not_coerced(underlying) -> None:
    with pytest.raises(ValueError, match="WAIVER_STATUS_COERCION"):
        aggregate_status([_harness(axisOverrides={"SOURCE": {
            "state": "WAIVED", "underlyingState": underlying,
        }})], freshness_state="CURRENT")


def test_materialized_fixture_axes_are_schema_valid_and_complete() -> None:
    axis_validator = validator("schemas/v1alpha1/status/common.schema.json").evolve(
        schema={"$ref": "https://harness.planeon.ai/schemas/v1alpha1/status/common.schema.json#/$defs/statusAxis"},
    )
    for case in VECTORS["scenarios"]:
        for specification in case["harnesses"]:
            harness = _harness(**specification)
            assert [axis["axis"] for axis in harness["axes"]] == VECTORS["axisIds"]
            for axis in harness["axes"]:
                axis_validator.validate(axis)
