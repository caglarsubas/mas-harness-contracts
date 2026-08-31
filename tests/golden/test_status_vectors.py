from __future__ import annotations

from planeon_harness_contracts.state_machine import (
    AGGREGATE_STATES,
    EVIDENCE_AXES,
    EVIDENCE_STATES,
    FRESHNESS_STATES,
    INSTALLATION_STATES,
    SELECTION_STATES,
)
from tests.model.schema_support import ROOT, load_json


def test_generated_status_semantics_mirror_runtime_constants() -> None:
    contract = load_json(ROOT / "generated/status-semantics.json")
    assert tuple(contract["aggregateStates"]) == AGGREGATE_STATES
    assert tuple(contract["evidenceAxes"]) == EVIDENCE_AXES
    assert tuple(contract["evidenceStates"]) == EVIDENCE_STATES
    assert tuple(contract["freshnessStates"]) == FRESHNESS_STATES
    assert tuple(contract["installationStates"]) == INSTALLATION_STATES
    assert tuple(contract["selectionStates"]) == SELECTION_STATES
    assert contract["waiverContributes"] == "DEGRADED"
    assert contract["unselectedContributes"] is False


def test_golden_vector_names_are_unique_and_cover_required_boundaries() -> None:
    vectors = load_json(ROOT / "tests/fixtures/status/aggregation-vectors.json")["vectors"]
    names = {vector["name"] for vector in vectors}
    assert len(names) == len(vectors)
    assert {
        "ready",
        "required-fail",
        "required-missing",
        "waiver-retains-fail",
        "stale-projection",
        "unselected-revoked-excluded",
        "selected-revoked",
        "no-selection",
    } == names
