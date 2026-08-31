from __future__ import annotations

import copy
import itertools

import pytest

from planeon_harness_contracts.state_machine import (
    EVIDENCE_AXES,
    EVIDENCE_STATES,
    FRESHNESS_STATES,
    INSTALLATION_STATES,
    SELECTION_STATES,
    aggregate_status,
    classify_freshness,
)
from tests.model.schema_support import ROOT, load_json, validator


def _axis(state: str = "PASS", *, required: bool = True, underlying: str | None = None) -> dict[str, object]:
    return {
        "axis": "SOURCE",
        "required": required,
        "state": state,
        "underlyingState": underlying,
        "applicability": (
            {
                "reasonCode": "AXIS_NOT_REQUIRED",
                "contractRef": {
                    "kind": "resource.contract",
                    "id": "contract.axis-applicability",
                    "digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                },
            }
            if state == "NOT_APPLICABLE"
            else None
        ),
    }


def _harness(
    harness_id: str = "runtime.infrastructure",
    *,
    selection: str = "SELECTED",
    installation: str = "READY",
    axes: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "harnessId": harness_id,
        "selectionState": selection,
        "installationState": installation,
        "axes": axes if axes is not None else [_axis()],
    }


def test_ready_harness_projection_and_empty_overview_validate() -> None:
    validator("schemas/v1alpha1/status/harness-status-projection.schema.json").validate(
        load_json(ROOT / "tests/fixtures/status/harness-ready.json")
    )
    validator("schemas/v1alpha1/status/tenant-harness-overview.schema.json").validate(
        load_json(ROOT / "tests/fixtures/status/tenant-empty.json")
    )


def test_every_immutable_binding_member_is_required() -> None:
    document = load_json(ROOT / "tests/fixtures/status/harness-ready.json")
    status_validator = validator("schemas/v1alpha1/status/harness-status-projection.schema.json")
    for field in (
        "organizationId",
        "profileDigest",
        "bundleDigest",
        "releaseDigest",
        "observedGeneration",
        "projectedAt",
        "freshUntil",
        "sourceCursors",
        "projectionSchemaVersion",
    ):
        candidate = copy.deepcopy(document)
        del candidate["binding"][field]
        assert tuple(status_validator.iter_errors(candidate)), field


def test_golden_aggregation_vectors() -> None:
    vectors = load_json(ROOT / "tests/fixtures/status/aggregation-vectors.json")["vectors"]
    for vector in vectors:
        harnesses = [
            _harness(
                item["harnessId"],
                selection=item["selectionState"],
                installation=item["installationState"],
                axes=[_axis(item["axisState"], required=item["required"], underlying=item["underlyingState"])],
            )
            for item in vector["harnesses"]
        ]
        result = aggregate_status(harnesses, freshness_state=vector["freshnessState"])
        assert result["aggregateState"] == vector["expected"], vector["name"]


def test_aggregation_is_independent_of_snapshot_order() -> None:
    harnesses = [
        _harness("runtime.infrastructure", installation="READY"),
        _harness("knowledge.domain-semantic", installation="DEGRADED"),
        _harness("execution.orchestration", installation="FAILED"),
        _harness("trust.security-safety", selection="NOT_SELECTED", installation="REVOKED"),
    ]
    results = {
        repr(aggregate_status(permutation, freshness_state="CURRENT"))
        for permutation in itertools.permutations(harnesses)
    }
    assert len(results) == 1


@pytest.mark.parametrize("state", INSTALLATION_STATES)
def test_every_installation_state_has_a_closed_aggregate_contribution(state: str) -> None:
    result = aggregate_status([_harness(installation=state)], freshness_state="CURRENT")
    expected = {
        "READY": "READY",
        "DEGRADED": "DEGRADED",
        "FAILED": "FAILED",
        "REVOKED": "REVOKED",
    }.get(state, "BLOCKED")
    assert result["aggregateState"] == expected


@pytest.mark.parametrize("state", EVIDENCE_STATES)
def test_every_evidence_state_has_a_closed_required_axis_contribution(state: str) -> None:
    underlying = "FAIL" if state == "WAIVED" else None
    result = aggregate_status(
        [_harness(axes=[_axis(state, underlying=underlying)])],
        freshness_state="CURRENT",
    )
    expected = {
        "PASS": "READY",
        "NOT_APPLICABLE": "READY",
        "FAIL": "FAILED",
        "WARN": "DEGRADED",
        "WAIVED": "DEGRADED",
    }.get(state, "BLOCKED")
    assert result["aggregateState"] == expected


@pytest.mark.parametrize("state", FRESHNESS_STATES)
def test_freshness_loss_prohibits_healthy_aggregate(state: str) -> None:
    result = aggregate_status([_harness()], freshness_state=state)
    assert result["aggregateState"] == ("READY" if state == "CURRENT" else "BLOCKED")


def test_freshness_is_derived_from_bound_time_and_source_state() -> None:
    binding = load_json(ROOT / "tests/fixtures/status/harness-ready.json")["binding"]
    assert classify_freshness(binding, evaluated_at="2026-08-31T05:04:59Z") == "CURRENT"
    assert classify_freshness(binding, evaluated_at="2026-08-31T05:05:01Z") == "STALE"
    binding["sourceCursors"][0]["state"] = "SOURCE_UNAVAILABLE"
    assert (
        classify_freshness(binding, evaluated_at="2026-08-31T05:04:59Z")
        == "SOURCE_UNAVAILABLE"
    )


def test_duplicate_source_cursor_and_invalid_freshness_window_fail_closed() -> None:
    binding = load_json(ROOT / "tests/fixtures/status/harness-ready.json")["binding"]
    binding["sourceCursors"].append(copy.deepcopy(binding["sourceCursors"][0]))
    with pytest.raises(ValueError, match="duplicate projection source cursor"):
        classify_freshness(binding, evaluated_at="2026-08-31T05:04:00Z")
    binding = load_json(ROOT / "tests/fixtures/status/harness-ready.json")["binding"]
    binding["freshUntil"] = "2026-08-31T04:59:59Z"
    with pytest.raises(ValueError, match="precedes projectedAt"):
        classify_freshness(binding, evaluated_at="2026-08-31T05:04:00Z")


@pytest.mark.parametrize("selection", SELECTION_STATES)
def test_selection_states_are_closed_and_only_selected_or_blocked_contribute(selection: str) -> None:
    result = aggregate_status(
        [_harness(selection=selection, installation="FAILED")], freshness_state="CURRENT"
    )
    expected = "FAILED" if selection in {"SELECTED", "BLOCKED"} else "EMPTY"
    assert result["aggregateState"] == expected


def test_waiver_cannot_hide_pass_or_not_applicable() -> None:
    for underlying in ("PASS", "NOT_APPLICABLE", None):
        with pytest.raises(ValueError, match="WAIVER_STATUS_COERCION"):
            aggregate_status(
                [_harness(axes=[_axis("WAIVED", underlying=underlying)])],
                freshness_state="CURRENT",
            )


def test_not_applicable_requires_an_immutable_contract_reference() -> None:
    axis = _axis("NOT_APPLICABLE")
    axis["applicability"] = None
    with pytest.raises(ValueError, match="NOT_APPLICABLE_REQUIRES_CONTRACT"):
        aggregate_status([_harness(axes=[axis])], freshness_state="CURRENT")


def test_ready_fixture_covers_every_axis_exactly_once() -> None:
    axes = load_json(ROOT / "tests/fixtures/status/harness-ready.json")["spec"]["axes"]
    assert tuple(axis["axis"] for axis in axes) == EVIDENCE_AXES
    assert len({axis["axis"] for axis in axes}) == len(EVIDENCE_AXES)


def test_duplicate_harness_or_axis_fails_closed() -> None:
    with pytest.raises(ValueError, match="duplicate harness"):
        aggregate_status([_harness(), _harness()], freshness_state="CURRENT")
    duplicate_axes = [_axis(), _axis()]
    with pytest.raises(ValueError, match="axes must be unique"):
        aggregate_status([_harness(axes=duplicate_axes)], freshness_state="CURRENT")
