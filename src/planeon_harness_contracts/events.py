"""Tenant-safe CloudEvents validation without a broker or network dependency."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from planeon_harness_contracts.state_machine import require_transition

EVENT_SCHEMA_VERSION = "harness.planeon.ai/harness-cloud-event/v1alpha1"
EVENT_DATA_VERSION = "harness.planeon.ai/event-data/v1alpha1"
EVENT_TYPES: Mapping[str, str | None] = {
    "harness.approval.state.changed.v1": "ApprovalRequest",
    "harness.bundle-release.state.changed.v1": "BundleRelease",
    "harness.evidence.state.changed.v1": "EvidenceRecord",
    "harness.installation.state.changed.v1": "HarnessInstallation",
    "harness.operation.state.changed.v1": "Operation",
    "harness.policy-bundle.state.changed.v1": "PolicyBundle",
    "harness.status.projection.updated.v1": None,
}

_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
_EVENT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_REASON = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
_FORBIDDEN_KEYS = frozenset(
    {
        "apikey",
        "authorization",
        "businesspayload",
        "credential",
        "modeloutput",
        "password",
        "prompt",
        "rawpayload",
        "secret",
        "token",
    }
)
_TOP_LEVEL_FIELDS = {
    "specversion",
    "id",
    "source",
    "type",
    "subject",
    "time",
    "datacontenttype",
    "dataschema",
    "organizationid",
    "partitionkey",
    "sequence",
    "data",
}
_DATA_FIELDS = {
    "schemaVersion",
    "aggregateKind",
    "aggregateId",
    "aggregateVersion",
    "actor",
    "correlationId",
    "causationId",
    "reasonCode",
    "transition",
    "resourceRefs",
    "evidenceRefs",
}


def _forbidden_key_path(value: Any, path: tuple[str | int, ...] = ()) -> tuple[str | int, ...] | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                return path
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in _FORBIDDEN_KEYS:
                return path + (key,)
            found = _forbidden_key_path(child, path + (key,))
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _forbidden_key_path(child, path + (index,))
            if found is not None:
                return found
    return None


def validate_event(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate one closed event and return stable rejection reasons."""

    issues: list[str] = []
    if set(document) != _TOP_LEVEL_FIELDS:
        issues.append("EVENT_FIELDS_NOT_CLOSED")
    if document.get("specversion") != "1.0":
        issues.append("CLOUDEVENTS_VERSION_MISMATCH")
    event_id = document.get("id")
    if not isinstance(event_id, str) or _EVENT_ID.fullmatch(event_id) is None:
        issues.append("INVALID_EVENT_ID")
    source = document.get("source")
    if not isinstance(source, str) or not source.startswith("urn:planeon:harness:"):
        issues.append("INVALID_EVENT_SOURCE")
    event_type = document.get("type")
    if event_type not in EVENT_TYPES:
        issues.append("UNKNOWN_EVENT_TYPE")
    subject = document.get("subject")
    organization_id = document.get("organizationid")
    partition_key = document.get("partitionkey")
    for code, value in (
        ("INVALID_EVENT_SUBJECT", subject),
        ("INVALID_ORGANIZATION_ID", organization_id),
        ("INVALID_PARTITION_KEY", partition_key),
    ):
        if not isinstance(value, str) or _ID.fullmatch(value) is None:
            issues.append(code)
    if organization_id != partition_key:
        issues.append("CROSS_TENANT_PARTITION")
    if not isinstance(document.get("sequence"), int) or isinstance(document.get("sequence"), bool) or document.get("sequence", 0) < 1:
        issues.append("INVALID_EVENT_SEQUENCE")
    if not isinstance(document.get("time"), str) or _TIME.fullmatch(document["time"]) is None:
        issues.append("INVALID_EVENT_TIME")
    if document.get("datacontenttype") != "application/json":
        issues.append("INVALID_EVENT_CONTENT_TYPE")
    if document.get("dataschema") != "https://harness.planeon.ai/schemas/v1alpha1/events/harness-cloud-event.schema.json":
        issues.append("INVALID_EVENT_DATA_SCHEMA")

    data = document.get("data")
    if not isinstance(data, Mapping):
        return tuple(dict.fromkeys((*issues, "INVALID_EVENT_DATA")))
    if set(data) != _DATA_FIELDS:
        issues.append("EVENT_DATA_FIELDS_NOT_CLOSED")
    if data.get("schemaVersion") != EVENT_DATA_VERSION:
        issues.append("EVENT_DATA_VERSION_MISMATCH")
    aggregate_kind = data.get("aggregateKind")
    aggregate_id = data.get("aggregateId")
    if not isinstance(aggregate_id, str) or _ID.fullmatch(aggregate_id) is None:
        issues.append("INVALID_AGGREGATE_ID")
    if aggregate_id != subject:
        issues.append("EVENT_SUBJECT_MISMATCH")
    aggregate_version = data.get("aggregateVersion")
    if not isinstance(aggregate_version, int) or isinstance(aggregate_version, bool) or aggregate_version < 1:
        issues.append("INVALID_AGGREGATE_VERSION")
    for field in ("correlationId", "causationId"):
        value = data.get(field)
        if value is not None and (not isinstance(value, str) or _EVENT_ID.fullmatch(value) is None):
            issues.append(f"INVALID_{field.upper()}")
    if not isinstance(data.get("reasonCode"), str) or _REASON.fullmatch(data["reasonCode"]) is None:
        issues.append("INVALID_REASON_CODE")
    actor = data.get("actor")
    if not isinstance(actor, Mapping) or set(actor) != {"type", "id"}:
        issues.append("INVALID_EVENT_ACTOR")
    elif actor.get("type") not in {"HUMAN", "WORKLOAD", "SYSTEM", "TENANT"} or not isinstance(actor.get("id"), str) or _ID.fullmatch(actor["id"]) is None:
        issues.append("INVALID_EVENT_ACTOR")
    for field in ("resourceRefs", "evidenceRefs"):
        refs = data.get(field)
        code_name = "RESOURCE_REFS" if field == "resourceRefs" else "EVIDENCE_REFS"
        if not isinstance(refs, list) or any(
            not isinstance(ref, Mapping)
            or set(ref) != {"kind", "id", "digest"}
            or not isinstance(ref.get("kind"), str)
            or _ID.fullmatch(ref["kind"]) is None
            or not isinstance(ref.get("id"), str)
            or _ID.fullmatch(ref["id"]) is None
            or not isinstance(ref.get("digest"), str)
            or _SHA256.fullmatch(ref["digest"]) is None
            for ref in refs
        ):
            issues.append(f"INVALID_{code_name}")
        elif len({ref["id"] for ref in refs}) != len(refs):
            issues.append(f"DUPLICATE_{code_name}")

    expected_kind = EVENT_TYPES.get(str(event_type))
    transition = data.get("transition")
    if expected_kind is None:
        if event_type == "harness.status.projection.updated.v1":
            if aggregate_kind not in {
                "TenantHarnessOverview",
                "PlaneStatusProjection",
                "HarnessStatusProjection",
            }:
                issues.append("EVENT_AGGREGATE_KIND_MISMATCH")
            if transition is not None:
                issues.append("PROJECTION_EVENT_HAS_TRANSITION")
    else:
        if aggregate_kind != expected_kind:
            issues.append("EVENT_AGGREGATE_KIND_MISMATCH")
        if not isinstance(transition, Mapping) or set(transition) != {"from", "to"}:
            issues.append("INVALID_EVENT_TRANSITION")
        else:
            try:
                require_transition(str(aggregate_kind), str(transition.get("from")), str(transition.get("to")))
            except ValueError:
                issues.append("ILLEGAL_EVENT_TRANSITION")

    forbidden = _forbidden_key_path(document)
    if forbidden is not None:
        issues.append("FORBIDDEN_EVENT_PAYLOAD_FIELD")
    return tuple(dict.fromkeys(issues))


def _event_files(path: Path) -> tuple[Path, ...]:
    if path.is_symlink():
        raise ValueError("event path links are forbidden")
    if path.is_file():
        return (path,)
    if not path.is_dir():
        raise ValueError("event path must be a regular file or directory")
    entries = tuple(sorted(path.iterdir(), key=lambda item: item.name))
    if any(entry.is_symlink() for entry in entries):
        raise ValueError("event directory links are forbidden")
    unexpected = [entry for entry in entries if not entry.is_file() or entry.suffix != ".json"]
    if unexpected:
        raise ValueError(f"event directory contains an invalid entry: {unexpected[0].name}")
    if not entries:
        raise ValueError("event directory is empty")
    return entries


def validate_event_path(path: Path) -> tuple[dict[str, Any], ...]:
    """Validate a deterministic event stream with tenant/sequence isolation."""

    accepted: list[dict[str, Any]] = []
    ids: set[str] = set()
    sequences: dict[tuple[str, str], list[int]] = defaultdict(list)
    for event_path in _event_files(path):
        try:
            document = json.loads(event_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid event JSON: {event_path.name}") from exc
        if not isinstance(document, dict):
            raise ValueError(f"event must be an object: {event_path.name}")
        issues = validate_event(document)
        if issues:
            raise ValueError(f"{event_path.name}: {issues[0]}")
        if document["id"] in ids:
            raise ValueError(f"duplicate event id: {document['id']}")
        ids.add(document["id"])
        key = (document["organizationid"], document["subject"])
        sequences[key].append(document["sequence"])
        accepted.append(document)
    for key, observed in sorted(sequences.items()):
        if observed != sorted(observed) or len(observed) != len(set(observed)):
            raise ValueError(f"event sequence is not strictly increasing: {key[0]}/{key[1]}")
    return tuple(accepted)


def event_command(path: Path) -> int:
    """CLI adapter for the existing CON-002-owned generic validate command."""

    try:
        events = validate_event_path(path)
    except ValueError as exc:
        print(f"event validation refused: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "accepted": True,
                "events": len(events),
                "organizations": len({event["organizationid"] for event in events}),
                "types": dict(
                    sorted(
                        (event_type, sum(event["type"] == event_type for event in events))
                        for event_type in {event["type"] for event in events}
                    )
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0
