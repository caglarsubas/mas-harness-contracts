"""Closed lifecycle transitions and deterministic tenant status aggregation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

SELECTION_STATES = ("NOT_SELECTED", "PROPOSED", "SELECTED", "BLOCKED")
INSTALLATION_STATES = (
    "ABSENT",
    "PENDING",
    "PREFLIGHT",
    "VERIFYING",
    "APPLYING",
    "HEALTH_CHECKING",
    "READY",
    "BLOCKED",
    "DEGRADED",
    "FAILED",
    "UPGRADING",
    "ROLLING_BACK",
    "UNINSTALLING",
    "REMOVED",
    "RETIRED",
    "REVOKED",
)
EVIDENCE_STATES = (
    "NOT_APPLICABLE",
    "MISSING",
    "COLLECTING",
    "PASS",
    "WARN",
    "FAIL",
    "STALE",
    "WAIVED",
    "NOT_RUN_ENV_UNAVAILABLE",
)
FRESHNESS_STATES = ("CURRENT", "STALE", "SOURCE_UNAVAILABLE")
AGGREGATE_STATES = ("EMPTY", "READY", "DEGRADED", "BLOCKED", "FAILED", "REVOKED")
EVIDENCE_AXES = (
    "SOURCE",
    "CONTRACT_UNIT",
    "PR_CHECK",
    "MERGE",
    "ARTIFACT_SBOM",
    "SIGNATURE_RELEASE",
    "DEPLOYMENT",
    "RUNTIME",
    "SECURITY",
    "ASSURANCE",
    "TENANT_ACCEPTANCE",
)

_TRANSITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "Operation": {
        "PENDING": ("RUNNING", "CANCELLED"),
        "RUNNING": ("SUCCEEDED", "FAILED", "CANCELLING"),
        "CANCELLING": ("CANCELLED", "FAILED"),
        "SUCCEEDED": (),
        "FAILED": (),
        "CANCELLED": (),
    },
    "ApprovalRequest": {
        "PENDING": ("APPROVED", "REJECTED", "EXPIRED", "CANCELLED"),
        "APPROVED": (),
        "REJECTED": (),
        "EXPIRED": (),
        "CANCELLED": (),
    },
    "BundleRelease": {
        "DRAFT": ("RESOLVED", "FAILED", "SUPERSEDED"),
        "RESOLVED": ("BUILT", "FAILED", "SUPERSEDED"),
        "BUILT": ("SCANNED", "FAILED", "SUPERSEDED"),
        "SCANNED": ("AWAITING_SIGNATURE", "FAILED", "SUPERSEDED"),
        "AWAITING_SIGNATURE": ("SIGNED", "FAILED", "SUPERSEDED"),
        "SIGNED": ("RELEASED", "FAILED", "SUPERSEDED"),
        "RELEASED": ("SUPERSEDED", "REVOKED"),
        "FAILED": (),
        "SUPERSEDED": ("REVOKED",),
        "REVOKED": (),
    },
    "HarnessInstallation": {
        "ABSENT": ("PENDING",),
        "PENDING": ("PREFLIGHT", "BLOCKED", "FAILED"),
        "PREFLIGHT": ("VERIFYING", "BLOCKED", "FAILED"),
        "VERIFYING": ("APPLYING", "BLOCKED", "FAILED"),
        "APPLYING": ("HEALTH_CHECKING", "BLOCKED", "FAILED", "ROLLING_BACK"),
        "HEALTH_CHECKING": ("READY", "DEGRADED", "BLOCKED", "FAILED", "ROLLING_BACK"),
        "READY": ("DEGRADED", "UPGRADING", "UNINSTALLING", "RETIRED", "REVOKED"),
        "BLOCKED": ("PENDING", "ROLLING_BACK", "UNINSTALLING", "REVOKED"),
        "DEGRADED": (
            "READY",
            "BLOCKED",
            "FAILED",
            "UPGRADING",
            "ROLLING_BACK",
            "UNINSTALLING",
            "REVOKED",
        ),
        "FAILED": ("PENDING", "ROLLING_BACK", "UNINSTALLING", "REVOKED"),
        "UPGRADING": (
            "VERIFYING",
            "HEALTH_CHECKING",
            "READY",
            "DEGRADED",
            "FAILED",
            "ROLLING_BACK",
            "REVOKED",
        ),
        "ROLLING_BACK": (
            "VERIFYING",
            "HEALTH_CHECKING",
            "READY",
            "DEGRADED",
            "FAILED",
            "REVOKED",
        ),
        "UNINSTALLING": ("REMOVED", "FAILED", "REVOKED"),
        "REMOVED": ("PENDING", "RETIRED", "REVOKED"),
        "RETIRED": ("REVOKED",),
        "REVOKED": (),
    },
    "EvidenceRecord": {
        "RECEIVED": ("VERIFIED", "REJECTED"),
        "VERIFIED": ("SUPERSEDED", "REVOKED"),
        "REJECTED": (),
        "SUPERSEDED": ("REVOKED",),
        "REVOKED": (),
    },
    "PolicyBundle": {
        "DRAFT": ("VALIDATED", "REJECTED"),
        "VALIDATED": ("SIGNED", "REJECTED"),
        "SIGNED": ("ACTIVE", "REVOKED"),
        "ACTIVE": ("RETIRED", "REVOKED"),
        "REJECTED": (),
        "RETIRED": ("REVOKED",),
        "REVOKED": (),
    },
}

TRANSITIONS: Mapping[str, Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        entity: MappingProxyType({state: tuple(targets) for state, targets in states.items()})
        for entity, states in sorted(_TRANSITIONS.items())
    }
)

_INSTALLATION_PRECEDENCE = {
    "REVOKED": 150,
    "FAILED": 140,
    "BLOCKED": 130,
    "DEGRADED": 120,
    "ROLLING_BACK": 110,
    "UNINSTALLING": 100,
    "UPGRADING": 90,
    "HEALTH_CHECKING": 80,
    "APPLYING": 70,
    "VERIFYING": 60,
    "PREFLIGHT": 50,
    "PENDING": 40,
    "ABSENT": 30,
    "REMOVED": 20,
    "RETIRED": 10,
    "READY": 0,
}


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"projection {field} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"projection {field} must be an RFC3339 UTC timestamp") from exc
    return parsed.replace(tzinfo=timezone.utc)


def classify_freshness(binding: Mapping[str, Any], *, evaluated_at: str) -> str:
    """Derive freshness from immutable times and a unique authenticated cursor set."""

    projected_at = _timestamp(binding.get("projectedAt"), "projectedAt")
    fresh_until = _timestamp(binding.get("freshUntil"), "freshUntil")
    evaluated = _timestamp(evaluated_at, "evaluatedAt")
    if fresh_until < projected_at:
        raise ValueError("projection freshUntil precedes projectedAt")
    if evaluated < projected_at:
        raise ValueError("projection evaluation precedes projectedAt")
    cursors = binding.get("sourceCursors")
    if not isinstance(cursors, list) or not cursors:
        raise ValueError("projection requires at least one source cursor")
    source_ids: set[str] = set()
    source_unavailable = False
    for cursor in cursors:
        if not isinstance(cursor, Mapping):
            raise ValueError("projection cursor must be an object")
        source_id = cursor.get("sourceId")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("projection sourceId is required")
        if source_id in source_ids:
            raise ValueError(f"duplicate projection source cursor: {source_id}")
        source_ids.add(source_id)
        observed_at = _timestamp(cursor.get("observedAt"), "sourceCursor.observedAt")
        if observed_at > projected_at:
            raise ValueError(f"projection cursor is newer than projection: {source_id}")
        state = cursor.get("state")
        if state not in {"CURRENT", "SOURCE_UNAVAILABLE"}:
            raise ValueError(f"unknown source cursor state: {state}")
        source_unavailable = source_unavailable or state == "SOURCE_UNAVAILABLE"
    if source_unavailable:
        return "SOURCE_UNAVAILABLE"
    return "STALE" if evaluated > fresh_until else "CURRENT"


def lifecycle_states(entity_kind: str) -> tuple[str, ...]:
    """Return the closed state set for one canonical entity."""

    states = TRANSITIONS.get(entity_kind)
    if states is None:
        raise ValueError(f"unknown lifecycle entity: {entity_kind}")
    return tuple(states)


def transition_allowed(entity_kind: str, from_state: str, to_state: str) -> bool:
    """Return whether a non-self transition is explicitly authorized."""

    states = TRANSITIONS.get(entity_kind)
    return states is not None and to_state in states.get(from_state, ())


def require_transition(entity_kind: str, from_state: str, to_state: str) -> None:
    """Reject unknown, terminal, self, or skipped lifecycle transitions."""

    states = TRANSITIONS.get(entity_kind)
    if states is None:
        raise ValueError(f"UNKNOWN_LIFECYCLE_ENTITY: {entity_kind}")
    if from_state not in states:
        raise ValueError(f"UNKNOWN_FROM_STATE: {entity_kind}.{from_state}")
    if to_state not in states:
        raise ValueError(f"UNKNOWN_TO_STATE: {entity_kind}.{to_state}")
    if not transition_allowed(entity_kind, from_state, to_state):
        raise ValueError(f"ILLEGAL_TRANSITION: {entity_kind}.{from_state}->{to_state}")


def worst_installation_state(states: Iterable[str]) -> str:
    """Select a stable worst state, rejecting values outside the closed enum."""

    candidates = tuple(states)
    if not candidates:
        raise ValueError("installation aggregation requires at least one state")
    unknown = sorted(set(candidates) - set(INSTALLATION_STATES))
    if unknown:
        raise ValueError(f"unknown installation state: {unknown[0]}")
    return min(candidates, key=lambda value: (-_INSTALLATION_PRECEDENCE[value], value))


def _axis_contribution(axis: Mapping[str, Any]) -> str:
    axis_id = axis.get("axis")
    state = axis.get("state")
    required = axis.get("required")
    if axis_id not in EVIDENCE_AXES:
        raise ValueError(f"unknown evidence axis: {axis_id}")
    if state not in EVIDENCE_STATES:
        raise ValueError(f"unknown evidence state: {state}")
    if not isinstance(required, bool):
        raise ValueError(f"axis required flag must be boolean: {axis_id}")
    underlying = axis.get("underlyingState")
    if state == "WAIVED":
        if underlying not in {
            "MISSING",
            "COLLECTING",
            "WARN",
            "FAIL",
            "STALE",
            "NOT_RUN_ENV_UNAVAILABLE",
        }:
            raise ValueError(f"WAIVER_STATUS_COERCION: {axis_id}")
        return "DEGRADED"
    if underlying is not None:
        raise ValueError(f"underlyingState is allowed only for WAIVED: {axis_id}")
    if state in {"PASS", "NOT_APPLICABLE"}:
        if state == "NOT_APPLICABLE" and not isinstance(axis.get("applicability"), Mapping):
            raise ValueError(f"NOT_APPLICABLE_REQUIRES_CONTRACT: {axis_id}")
        return "READY"
    if not required:
        return "DEGRADED"
    if state == "FAIL":
        return "FAILED"
    if state in {"WARN"}:
        return "DEGRADED"
    return "BLOCKED"


def aggregate_status(
    harnesses: Iterable[Mapping[str, Any]],
    *,
    freshness_state: str,
) -> dict[str, Any]:
    """Aggregate a complete snapshot with closed precedence and no arrival-order input."""

    if freshness_state not in FRESHNESS_STATES:
        raise ValueError(f"unknown freshness state: {freshness_state}")
    by_id: dict[str, Mapping[str, Any]] = {}
    for harness in harnesses:
        harness_id = harness.get("harnessId")
        if not isinstance(harness_id, str) or not harness_id:
            raise ValueError("harnessId is required")
        if harness_id in by_id:
            raise ValueError(f"duplicate harness status: {harness_id}")
        selection = harness.get("selectionState")
        installation = harness.get("installationState")
        if selection not in SELECTION_STATES:
            raise ValueError(f"unknown selection state: {selection}")
        if installation not in INSTALLATION_STATES:
            raise ValueError(f"unknown installation state: {installation}")
        axes = harness.get("axes")
        if not isinstance(axes, list):
            raise ValueError(f"axes must be a list: {harness_id}")
        axis_ids = [axis.get("axis") for axis in axes if isinstance(axis, Mapping)]
        if len(axis_ids) != len(axes) or len(set(axis_ids)) != len(axis_ids):
            raise ValueError(f"axes must be unique objects: {harness_id}")
        by_id[harness_id] = harness

    active = tuple(
        by_id[harness_id]
        for harness_id in sorted(by_id)
        if by_id[harness_id]["selectionState"] in {"SELECTED", "BLOCKED"}
    )
    selection_counts = Counter(str(item["selectionState"]) for item in by_id.values())
    installation_counts = Counter(str(item["installationState"]) for item in active)
    if not active:
        return {
            "aggregateState": "EMPTY",
            "contributingHarnessIds": [],
            "selectedCount": 0,
            "selectionCounts": dict(sorted(selection_counts.items())),
            "installationCounts": {},
            "worstInstallationState": None,
        }

    contributions: dict[str, str] = {}
    for harness in active:
        harness_id = str(harness["harnessId"])
        installation = str(harness["installationState"])
        state = "READY"
        if installation == "REVOKED":
            state = "REVOKED"
        elif installation == "FAILED":
            state = "FAILED"
        elif harness["selectionState"] == "BLOCKED" or installation != "READY":
            state = "DEGRADED" if installation == "DEGRADED" else "BLOCKED"
        for axis in harness["axes"]:
            contribution = _axis_contribution(axis)
            precedence = {"READY": 0, "DEGRADED": 1, "BLOCKED": 2, "FAILED": 3}
            if state != "REVOKED" and precedence[contribution] > precedence[state]:
                state = contribution
        contributions[harness_id] = state

    if "REVOKED" in contributions.values():
        aggregate = "REVOKED"
    elif "FAILED" in contributions.values():
        aggregate = "FAILED"
    elif freshness_state != "CURRENT" or "BLOCKED" in contributions.values():
        aggregate = "BLOCKED"
    elif "DEGRADED" in contributions.values():
        aggregate = "DEGRADED"
    else:
        aggregate = "READY"
    return {
        "aggregateState": aggregate,
        "contributingHarnessIds": [
            harness_id
            for harness_id in sorted(contributions)
            if contributions[harness_id] != "READY"
        ],
        "selectedCount": len(active),
        "selectionCounts": dict(sorted(selection_counts.items())),
        "installationCounts": dict(sorted(installation_counts.items())),
        "worstInstallationState": worst_installation_state(installation_counts),
    }


def generated_lifecycle_contract() -> dict[str, Any]:
    """Return the deterministic transition table consumed by generated artifacts."""

    return {
        "schemaVersion": "harness.planeon.ai/lifecycle-transition-table/v1",
        "entities": {
            entity: {
                "states": list(states),
                "terminalStates": [state for state, targets in states.items() if not targets],
                "transitions": [
                    {"from": state, "to": target}
                    for state, targets in states.items()
                    for target in targets
                ],
            }
            for entity, states in TRANSITIONS.items()
        },
    }


def generated_status_contract() -> dict[str, Any]:
    """Return the closed status enums and precedence as generated evidence."""

    return {
        "schemaVersion": "harness.planeon.ai/status-semantics/v1",
        "aggregatePrecedence": ["REVOKED", "FAILED", "BLOCKED", "DEGRADED", "READY", "EMPTY"],
        "aggregateStates": list(AGGREGATE_STATES),
        "evidenceAxes": list(EVIDENCE_AXES),
        "evidenceStates": list(EVIDENCE_STATES),
        "freshnessStates": list(FRESHNESS_STATES),
        "installationStates": list(INSTALLATION_STATES),
        "selectionStates": list(SELECTION_STATES),
        "waiverContributes": "DEGRADED",
        "unselectedContributes": False,
    }
