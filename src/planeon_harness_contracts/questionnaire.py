"""Closed questionnaire/readiness bundle loading and semantic validation."""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from planeon_harness_contracts.models import (
    GuidanceBundleSummary,
    MANDATORY_READINESS_GATES,
    QuestionnaireState,
    ReadinessStatus,
)
from planeon_harness_contracts.rules import PATH_PATTERN, validate_rule
from planeon_harness_contracts.validation import (
    API_VERSION,
    EXPECTED_HARNESSES,
    ValidationIssue,
    ValidationResult,
)

GUIDANCE_KINDS = frozenset(
    {
        "QuestionnaireDefinition",
        "QuestionnaireSession",
        "QuestionnaireAnswerSet",
        "BusinessContext",
        "DataReadinessAssessment",
        "GuidanceRule",
    }
)
GATE_CATEGORIES = frozenset({"BUSINESS", "DATA", "INTEGRATION", "GOVERNANCE", "AUTONOMY"})
RESPONSE_TYPES = frozenset({"TEXT", "NUMBER", "BOOLEAN", "SINGLE_SELECT", "MULTI_SELECT"})
GUIDANCE_ACTIONS = frozenset(
    {"ASK_QUESTION", "REQUIRE_EVIDENCE", "RECOMMEND_HARNESS", "BLOCK_READINESS"}
)
FORBIDDEN_KEYS = frozenset(
    {
        "apiKey",
        "argv",
        "callable",
        "code",
        "command",
        "endpoint",
        "expression",
        "filePath",
        "filesystemPath",
        "handler",
        "import",
        "llmPrompt",
        "module",
        "network",
        "persistence",
        "script",
        "secret",
        "template",
        "url",
    }
)
STABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")


def _issue(code: str, message: str, *path: str | int) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, path=path)


def _metadata_id(document: Mapping[str, Any]) -> str:
    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping):
        return ""
    value = metadata.get("id")
    return value if isinstance(value, str) else ""


def _spec(document: Mapping[str, Any]) -> Mapping[str, Any]:
    value = document.get("spec")
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _valid_stable_id(value: Any) -> bool:
    return isinstance(value, str) and STABLE_ID_PATTERN.fullmatch(value) is not None


def _valid_string(value: Any, minimum: int = 1) -> bool:
    return isinstance(value, str) and len(value) >= minimum


def _valid_scalar(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, (str, bool, int))


def _validate_stable_id_list(
    value: Any,
    field: str,
    resource_id: str,
    *,
    allow_empty: bool = True,
) -> list[ValidationIssue]:
    if not isinstance(value, list) or (not allow_empty and not value):
        return [_issue("INVALID_ID_LIST", f"{resource_id} requires a valid {field} list")]
    if not all(_valid_stable_id(item) for item in value) or len(value) != len(set(value)):
        return [_issue("INVALID_ID_LIST", f"{resource_id} {field} must contain unique stable ids")]
    return []


def _closed_fields(
    value: Mapping[str, Any],
    required: set[str],
    allowed: set[str],
    resource_id: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    missing = required - set(value)
    extra = set(value) - allowed
    if missing:
        issues.append(_issue("MISSING_REQUIRED_FIELD", f"{resource_id} is missing {sorted(missing)[0]}"))
    if extra:
        issues.append(_issue("FIELDS_CLOSED", f"{resource_id} contains forbidden field {sorted(extra)[0]}"))
    return issues


def _forbidden_key_issues(value: Any, path: tuple[str | int, ...] = ()) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key in FORBIDDEN_KEYS:
                issues.append(
                    _issue(
                        "EXECUTABLE_CONTENT_FORBIDDEN",
                        f"questionnaire data contains forbidden field: {key}",
                        *(path + (key,)),
                    )
                )
            issues.extend(_forbidden_key_issues(child, path + (str(key),)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_forbidden_key_issues(child, path + (index,)))
    return issues


def _validate_definition(document: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _metadata_id(document)
    spec = _spec(document)
    issues = _closed_fields(
        spec,
        {"title", "industry", "sections", "mandatoryGateIds"},
        {"title", "industry", "sections", "mandatoryGateIds"},
        resource_id,
    )
    if not _valid_string(spec.get("title"), 3):
        issues.append(_issue("INVALID_QUESTIONNAIRE_TITLE", f"{resource_id} requires a title"))
    if not _valid_stable_id(spec.get("industry")):
        issues.append(_issue("INVALID_INDUSTRY_ID", f"{resource_id} requires a stable industry id"))
    gates = _string_list(spec.get("mandatoryGateIds"))
    if not isinstance(spec.get("mandatoryGateIds"), list) or tuple(gates) != MANDATORY_READINESS_GATES:
        issues.append(
            _issue(
                "MANDATORY_GATE_SET_MISMATCH",
                "questionnaire must declare the ten mandatory gates in canonical order",
            )
        )
    raw_sections = spec.get("sections")
    sections = _mapping_list(raw_sections)
    if not isinstance(raw_sections, list) or len(sections) != len(raw_sections):
        issues.append(_issue("INVALID_SECTION_LIST", f"{resource_id} sections must contain only objects"))
    if not sections:
        return issues + [_issue("SECTION_REQUIRED", f"{resource_id} has no questionnaire section")]
    section_ids: set[str] = set()
    question_ids: set[str] = set()
    answer_paths: set[str] = set()
    required_gates: set[str] = set()
    orders: list[int] = []
    for section in sections:
        issues.extend(
            _closed_fields(
                section,
                {"id", "title", "order", "gateCategory", "questions"},
                {"id", "title", "order", "gateCategory", "questions"},
                resource_id,
            )
        )
        section_id = section.get("id")
        if not _valid_stable_id(section_id) or section_id in section_ids:
            issues.append(_issue("DUPLICATE_OR_INVALID_SECTION", f"invalid section id: {section_id}"))
        else:
            section_ids.add(section_id)
        if not isinstance(section.get("order"), int) or isinstance(section.get("order"), bool):
            issues.append(_issue("INVALID_SECTION_ORDER", f"section {section_id} has invalid order"))
        else:
            orders.append(section["order"])
        if section.get("gateCategory") not in GATE_CATEGORIES:
            issues.append(_issue("INVALID_GATE_CATEGORY", f"section {section_id} has invalid category"))
        if not _valid_string(section.get("title"), 3):
            issues.append(_issue("INVALID_SECTION_TITLE", f"section {section_id} requires a title"))
        raw_questions = section.get("questions")
        questions = _mapping_list(raw_questions)
        if not isinstance(raw_questions, list) or len(questions) != len(raw_questions):
            issues.append(_issue("INVALID_QUESTION_LIST", f"section {section_id} questions must be objects"))
        if not questions:
            issues.append(_issue("QUESTION_REQUIRED", f"section {section_id} has no question"))
        for question in questions:
            issues.extend(
                _closed_fields(
                    question,
                    {"id", "prompt", "responseType", "required", "answerPath", "gateId"},
                    {"id", "prompt", "responseType", "required", "answerPath", "gateId", "options"},
                    resource_id,
                )
            )
            question_id = question.get("id")
            if not _valid_stable_id(question_id) or question_id in question_ids:
                issues.append(_issue("DUPLICATE_OR_INVALID_QUESTION", f"invalid question id: {question_id}"))
            else:
                question_ids.add(question_id)
            answer_path = question.get("answerPath")
            if (
                not isinstance(answer_path, str)
                or PATH_PATTERN.fullmatch(answer_path) is None
                or answer_path in answer_paths
            ):
                issues.append(_issue("DUPLICATE_OR_INVALID_ANSWER_PATH", f"invalid answer path: {answer_path}"))
            else:
                answer_paths.add(answer_path)
            response_type = question.get("responseType")
            if response_type not in RESPONSE_TYPES:
                issues.append(_issue("INVALID_RESPONSE_TYPE", f"question {question_id} has invalid type"))
            if not _valid_string(question.get("prompt"), 5):
                issues.append(_issue("INVALID_QUESTION_PROMPT", f"question {question_id} requires a prompt"))
            options = question.get("options")
            if response_type in {"SINGLE_SELECT", "MULTI_SELECT"}:
                option_values = _string_list(options)
                if (
                    not isinstance(options, list)
                    or len(option_values) != len(options)
                    or not option_values
                    or any(not option for option in option_values)
                    or len(set(option_values)) != len(option_values)
                ):
                    issues.append(_issue("QUESTION_OPTIONS_REQUIRED", f"question {question_id} needs unique options"))
            elif "options" in question:
                issues.append(_issue("QUESTION_OPTIONS_FORBIDDEN", f"question {question_id} cannot declare options"))
            gate_id = question.get("gateId")
            if gate_id not in MANDATORY_READINESS_GATES:
                issues.append(_issue("UNKNOWN_READINESS_GATE", f"question {question_id} uses unknown gate"))
            if question.get("required") is True and isinstance(gate_id, str):
                required_gates.add(gate_id)
            elif question.get("required") is not False:
                issues.append(_issue("INVALID_REQUIRED_FLAG", f"question {question_id} has invalid required flag"))
    if sorted(orders) != list(range(1, len(sections) + 1)):
        issues.append(_issue("SECTION_ORDER_NOT_CONTIGUOUS", "section order must start at one and be contiguous"))
    if required_gates != set(MANDATORY_READINESS_GATES):
        issues.append(_issue("MANDATORY_GATE_QUESTION_MISSING", "every mandatory gate needs a required question"))
    return issues


def _validate_session(document: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _metadata_id(document)
    spec = _spec(document)
    issues = _closed_fields(
        spec,
        {"questionnaireDefinitionId", "state", "currentSectionId", "completedSectionIds", "revision"},
        {"questionnaireDefinitionId", "state", "currentSectionId", "completedSectionIds", "revision"},
        resource_id,
    )
    if not _valid_stable_id(spec.get("questionnaireDefinitionId")):
        issues.append(_issue("INVALID_DEFINITION_REFERENCE", f"{resource_id} requires a definition id"))
    if spec.get("state") not in set(QuestionnaireState):
        issues.append(_issue("INVALID_SESSION_STATE", f"{resource_id} has an invalid state"))
    revision = spec.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        issues.append(_issue("INVALID_SESSION_REVISION", f"{resource_id} revision must be positive"))
    current = spec.get("currentSectionId")
    if current is not None and not _valid_stable_id(current):
        issues.append(_issue("INVALID_CURRENT_SECTION", f"{resource_id} has an invalid current section"))
    issues.extend(
        _validate_stable_id_list(spec.get("completedSectionIds"), "completedSectionIds", resource_id)
    )
    return issues


def _validate_answer_set(document: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _metadata_id(document)
    spec = _spec(document)
    issues = _closed_fields(
        spec,
        {"questionnaireDefinitionId", "questionnaireSessionId", "status", "answers"},
        {"questionnaireDefinitionId", "questionnaireSessionId", "status", "answers"},
        resource_id,
    )
    for field in ("questionnaireDefinitionId", "questionnaireSessionId"):
        if not _valid_stable_id(spec.get(field)):
            issues.append(_issue("INVALID_REFERENCE", f"{resource_id} requires a stable {field}"))
    if spec.get("status") not in {"DRAFT", "SUBMITTED"}:
        issues.append(_issue("INVALID_ANSWER_STATUS", f"{resource_id} has invalid answer status"))
    raw_answers = spec.get("answers")
    answers = _mapping_list(raw_answers)
    if not isinstance(raw_answers, list) or len(answers) != len(raw_answers):
        issues.append(_issue("INVALID_ANSWER_LIST", f"{resource_id} answers must contain only objects"))
    answer_ids: set[str] = set()
    for answer in answers:
        issues.extend(
            _closed_fields(
                answer,
                {"questionId", "value", "source"},
                {"questionId", "value", "source"},
                resource_id,
            )
        )
        question_id = answer.get("questionId")
        if not _valid_stable_id(question_id) or question_id in answer_ids:
            issues.append(_issue("DUPLICATE_OR_INVALID_ANSWER", f"invalid answer for: {question_id}"))
        else:
            answer_ids.add(question_id)
        if answer.get("source") != "TENANT_DECLARATION":
            issues.append(_issue("INVALID_ANSWER_SOURCE", f"answer {question_id} has an invalid source"))
        value = answer.get("value")
        valid_list = (
            isinstance(value, list)
            and bool(value)
            and all(_valid_scalar(item) for item in value)
        )
        if not _valid_scalar(value) and not valid_list:
            issues.append(_issue("INVALID_ANSWER_VALUE", f"answer {question_id} must be a non-null scalar or list"))
    return issues


def _validate_business_context(document: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _metadata_id(document)
    spec = _spec(document)
    issues = _closed_fields(
        spec,
        {
            "questionnaireSessionId",
            "industry",
            "domain",
            "businessOwner",
            "desiredOutcome",
            "dataOwner",
            "regulatoryContexts",
            "technologyConstraints",
        },
        {
            "questionnaireSessionId",
            "industry",
            "domain",
            "businessOwner",
            "desiredOutcome",
            "dataOwner",
            "regulatoryContexts",
            "technologyConstraints",
        },
        resource_id,
    )
    for field in ("questionnaireSessionId", "industry", "domain"):
        if not _valid_stable_id(spec.get(field)):
            issues.append(_issue("INVALID_CONTEXT_ID", f"{resource_id} requires a stable {field}"))
    owners = (("businessOwner", spec.get("businessOwner")), ("dataOwner", spec.get("dataOwner")))
    for field, owner in owners:
        if not isinstance(owner, Mapping) or set(owner) != {"subjectId", "role"}:
            issues.append(_issue("MANDATORY_OWNER_MISSING", f"{resource_id} requires closed {field}"))
        elif not _valid_stable_id(owner.get("subjectId")) or not _valid_string(owner.get("role"), 2):
            issues.append(_issue("MANDATORY_OWNER_MISSING", f"{resource_id} requires complete {field}"))
    outcome = spec.get("desiredOutcome")
    outcome_fields = {"statement", "metric", "target", "timeHorizon"}
    if not isinstance(outcome, Mapping) or set(outcome) != outcome_fields:
        issues.append(_issue("MANDATORY_OUTCOME_MISSING", f"{resource_id} requires a measurable outcome"))
    elif not _valid_string(outcome.get("statement"), 5) or not all(
        _valid_string(outcome.get(key)) for key in outcome_fields - {"statement"}
    ):
        issues.append(_issue("MANDATORY_OUTCOME_MISSING", f"{resource_id} outcome is incomplete"))
    for field in ("regulatoryContexts", "technologyConstraints"):
        issues.extend(_validate_stable_id_list(spec.get(field), field, resource_id))
    return issues


def _validate_readiness(document: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _metadata_id(document)
    spec = _spec(document)
    issues = _closed_fields(
        spec,
        {"questionnaireSessionId", "overallStatus", "gateResults", "missingGateIds"},
        {"questionnaireSessionId", "overallStatus", "gateResults", "missingGateIds"},
        resource_id,
    )
    if not _valid_stable_id(spec.get("questionnaireSessionId")):
        issues.append(_issue("INVALID_SESSION_REFERENCE", f"{resource_id} requires a session id"))
    raw_gate_results = spec.get("gateResults")
    gate_results = _mapping_list(raw_gate_results)
    if not isinstance(raw_gate_results, list) or len(gate_results) != len(raw_gate_results):
        issues.append(_issue("INVALID_GATE_RESULT_LIST", f"{resource_id} gate results must be objects"))
    gates: dict[str, str] = {}
    for gate in gate_results:
        issues.extend(
            _closed_fields(
                gate,
                {"gateId", "status", "evidenceIds", "reasonCode"},
                {"gateId", "status", "evidenceIds", "reasonCode"},
                resource_id,
            )
        )
        gate_id = gate.get("gateId")
        status = gate.get("status")
        if not isinstance(gate_id, str) or gate_id in gates:
            issues.append(_issue("DUPLICATE_OR_INVALID_GATE", f"invalid readiness gate: {gate_id}"))
            continue
        if gate_id not in MANDATORY_READINESS_GATES:
            issues.append(_issue("UNKNOWN_READINESS_GATE", f"unknown readiness gate: {gate_id}"))
        if status not in set(ReadinessStatus):
            issues.append(_issue("INVALID_GATE_STATUS", f"{gate_id} has invalid readiness status"))
            continue
        gates[gate_id] = status
        evidence = _string_list(gate.get("evidenceIds"))
        issues.extend(
            _validate_stable_id_list(gate.get("evidenceIds"), "evidenceIds", resource_id)
        )
        if status == ReadinessStatus.PASS and not evidence:
            issues.append(_issue("GATE_EVIDENCE_REQUIRED", f"passing gate lacks evidence: {gate_id}"))
        if not _valid_stable_id(gate.get("reasonCode")):
            issues.append(_issue("GATE_REASON_REQUIRED", f"gate lacks a reason code: {gate_id}"))
    if set(gates) != set(MANDATORY_READINESS_GATES):
        issues.append(_issue("MANDATORY_GATE_SET_MISMATCH", "readiness must assess all ten mandatory gates"))
    non_passing = sorted(gate_id for gate_id, status in gates.items() if status != ReadinessStatus.PASS)
    raw_missing = spec.get("missingGateIds")
    missing = sorted(_string_list(raw_missing))
    if (
        not isinstance(raw_missing, list)
        or len(missing) != len(raw_missing)
        or len(missing) != len(set(missing))
        or any(gate_id not in MANDATORY_READINESS_GATES for gate_id in missing)
    ):
        issues.append(_issue("INVALID_MISSING_GATE_LIST", f"{resource_id} has invalid missingGateIds"))
    if missing != non_passing:
        issues.append(_issue("MISSING_GATE_SET_MISMATCH", "missingGateIds must exactly list every non-pass gate"))
    overall = spec.get("overallStatus")
    if overall == "READY" and non_passing:
        issues.append(_issue("FALSE_READINESS_FORBIDDEN", "READY requires all ten gates to pass"))
    elif overall == "BLOCKED" and not non_passing:
        issues.append(_issue("FALSE_BLOCKED_FORBIDDEN", "BLOCKED requires at least one non-pass gate"))
    elif overall not in {"READY", "BLOCKED"}:
        issues.append(_issue("INVALID_OVERALL_READINESS", f"{resource_id} has invalid overall status"))
    return issues


def _validate_guidance_rule(document: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _metadata_id(document)
    spec = _spec(document)
    issues = _closed_fields(
        spec,
        {"questionnaireDefinitionId", "priority", "enabled", "when", "guidance"},
        {"questionnaireDefinitionId", "priority", "enabled", "when", "guidance"},
        resource_id,
    )
    if not _valid_stable_id(spec.get("questionnaireDefinitionId")):
        issues.append(_issue("INVALID_DEFINITION_REFERENCE", f"{resource_id} requires a definition id"))
    priority = spec.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 1000:
        issues.append(_issue("INVALID_RULE_PRIORITY", f"{resource_id} priority must be 0..1000"))
    if spec.get("enabled") is not True:
        issues.append(_issue("DISABLED_RULE_FORBIDDEN", f"{resource_id} catalog rules must be enabled"))
    condition = spec.get("when")
    if not isinstance(condition, Mapping):
        issues.append(_issue("INVALID_RULE", f"{resource_id} requires an object condition"))
    else:
        issues.extend(
            _issue(problem.code, problem.message, *("spec", "when") + problem.path)
            for problem in validate_rule(condition)
        )
    raw_guidance = spec.get("guidance")
    guidance = _mapping_list(raw_guidance)
    if not isinstance(raw_guidance, list) or len(guidance) != len(raw_guidance):
        issues.append(_issue("INVALID_GUIDANCE_LIST", f"{resource_id} guidance must contain only objects"))
    if not guidance:
        issues.append(_issue("GUIDANCE_ACTION_REQUIRED", f"{resource_id} has no guidance action"))
    for action in guidance:
        issues.extend(
            _closed_fields(
                action,
                {"type", "targetId", "reasonCode"},
                {"type", "targetId", "reasonCode"},
                resource_id,
            )
        )
        action_type = action.get("type")
        target = action.get("targetId")
        if action_type not in GUIDANCE_ACTIONS:
            issues.append(_issue("EXECUTABLE_GUIDANCE_FORBIDDEN", f"unknown guidance action: {action_type}"))
        if action_type == "RECOMMEND_HARNESS" and target not in EXPECTED_HARNESSES:
            issues.append(_issue("UNKNOWN_HARNESS_RECOMMENDATION", f"unknown harness target: {target}"))
        elif not _valid_stable_id(target):
            issues.append(_issue("INVALID_GUIDANCE_TARGET", f"{resource_id} action has invalid target"))
        if not _valid_stable_id(action.get("reasonCode")):
            issues.append(_issue("GUIDANCE_REASON_REQUIRED", f"{resource_id} action has no reason code"))
    return issues


def validate_guidance_document(document: Mapping[str, Any]) -> ValidationResult:
    """Validate one closed questionnaire, readiness, or guidance document."""

    issues = _forbidden_key_issues(document)
    kind = document.get("kind")
    if document.get("apiVersion") != API_VERSION:
        issues.append(_issue("API_VERSION_MISMATCH", f"guidance resource must use {API_VERSION}"))
    if kind not in GUIDANCE_KINDS:
        issues.append(_issue("UNKNOWN_GUIDANCE_KIND", f"unknown guidance kind: {kind}"))
    if set(document) != {"apiVersion", "kind", "metadata", "spec"}:
        issues.append(_issue("RESOURCE_FIELDS_CLOSED", "resource fields are exactly apiVersion, kind, metadata, spec"))
    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping) or set(metadata) != {"id", "version"}:
        issues.append(_issue("INVALID_METADATA", "metadata fields are exactly id and version"))
    elif not _valid_stable_id(metadata.get("id")) or not (
        isinstance(metadata.get("version"), str)
        and SEMVER_PATTERN.fullmatch(metadata["version"]) is not None
    ):
        issues.append(_issue("INVALID_METADATA", "metadata requires a stable id and semantic version"))
    if not isinstance(document.get("spec"), Mapping):
        issues.append(_issue("INVALID_SPEC", "spec must be an object"))
    elif kind == "QuestionnaireDefinition":
        issues.extend(_validate_definition(document))
    elif kind == "QuestionnaireSession":
        issues.extend(_validate_session(document))
    elif kind == "QuestionnaireAnswerSet":
        issues.extend(_validate_answer_set(document))
    elif kind == "BusinessContext":
        issues.extend(_validate_business_context(document))
    elif kind == "DataReadinessAssessment":
        issues.extend(_validate_readiness(document))
    elif kind == "GuidanceRule":
        issues.extend(_validate_guidance_rule(document))
    return ValidationResult.rejected(*issues) if issues else ValidationResult.success()


def validate_guidance_bundle(documents: Sequence[Mapping[str, Any]]) -> ValidationResult:
    """Validate resource closure and cross-document references for one questionnaire bundle."""

    issues: list[ValidationIssue] = []
    by_kind: dict[str, list[Mapping[str, Any]]] = {kind: [] for kind in GUIDANCE_KINDS}
    by_id: dict[str, Mapping[str, Any]] = {}
    for document in documents:
        result = validate_guidance_document(document)
        issues.extend(result.issues)
        kind = document.get("kind")
        if isinstance(kind, str) and kind in by_kind:
            by_kind[kind].append(document)
        resource_id = _metadata_id(document)
        if resource_id in by_id:
            issues.append(_issue("DUPLICATE_RESOURCE_ID", f"duplicate guidance resource: {resource_id}"))
        elif resource_id:
            by_id[resource_id] = document
    for kind in GUIDANCE_KINDS - {"GuidanceRule"}:
        if len(by_kind[kind]) != 1:
            issues.append(_issue("BUNDLE_CARDINALITY_MISMATCH", f"bundle requires exactly one {kind}"))
    if not by_kind["GuidanceRule"]:
        issues.append(_issue("BUNDLE_CARDINALITY_MISMATCH", "bundle requires at least one GuidanceRule"))
    if issues:
        return ValidationResult.rejected(*issues)

    definition = by_kind["QuestionnaireDefinition"][0]
    session = by_kind["QuestionnaireSession"][0]
    answers = by_kind["QuestionnaireAnswerSet"][0]
    business = by_kind["BusinessContext"][0]
    readiness = by_kind["DataReadinessAssessment"][0]
    definition_id = _metadata_id(definition)
    session_id = _metadata_id(session)
    reference_checks = (
        (_spec(session).get("questionnaireDefinitionId"), definition_id, "session definition"),
        (_spec(answers).get("questionnaireDefinitionId"), definition_id, "answer definition"),
        (_spec(answers).get("questionnaireSessionId"), session_id, "answer session"),
        (_spec(business).get("questionnaireSessionId"), session_id, "business session"),
        (_spec(readiness).get("questionnaireSessionId"), session_id, "readiness session"),
    )
    for actual, expected, label in reference_checks:
        if actual != expected:
            issues.append(_issue("REFERENCE_MISMATCH", f"{label} reference must equal {expected}"))
    for rule in by_kind["GuidanceRule"]:
        if _spec(rule).get("questionnaireDefinitionId") != definition_id:
            issues.append(_issue("REFERENCE_MISMATCH", f"rule {_metadata_id(rule)} references another definition"))

    sections = _mapping_list(_spec(definition).get("sections"))
    section_ids = {section["id"] for section in sections}
    questions = {
        question["id"]: question
        for section in sections
        for question in _mapping_list(section.get("questions"))
    }
    current_section = _spec(session).get("currentSectionId")
    if current_section is not None and current_section not in section_ids:
        issues.append(_issue("UNKNOWN_CURRENT_SECTION", f"session references unknown section: {current_section}"))
    completed = set(_string_list(_spec(session).get("completedSectionIds")))
    if not completed.issubset(section_ids):
        issues.append(_issue("UNKNOWN_COMPLETED_SECTION", "session completedSectionIds contains unknown section"))
    answer_map = {
        answer["questionId"]: answer.get("value")
        for answer in _mapping_list(_spec(answers).get("answers"))
        if isinstance(answer.get("questionId"), str)
    }
    unknown_answers = set(answer_map) - set(questions)
    if unknown_answers:
        issues.append(_issue("UNKNOWN_QUESTION_ANSWER", f"answer references unknown question: {sorted(unknown_answers)[0]}"))
    if _spec(answers).get("status") == "SUBMITTED":
        required = {question_id for question_id, question in questions.items() if question.get("required") is True}
        missing = required - set(answer_map)
        if missing:
            issues.append(_issue("MANDATORY_ANSWER_MISSING", f"submitted answer set lacks {sorted(missing)[0]}"))
    return ValidationResult.rejected(*issues) if issues else ValidationResult.success()


def load_guidance_path(path: Path) -> tuple[dict[str, Any], ...]:
    """Load only explicit regular JSON files beneath the supplied path."""

    if path.is_symlink():
        raise ValueError("questionnaire path may not be a link")
    if path.is_file():
        files = (path,)
    elif path.is_dir():
        entries = tuple(sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()))
        links = [entry for entry in entries if entry.is_symlink()]
        if links:
            raise ValueError(f"questionnaire bundle contains a link: {links[0].name}")
        unexpected = [entry for entry in entries if entry.is_file() and entry.suffix != ".json"]
        if unexpected:
            raise ValueError(f"questionnaire bundle contains a non-JSON file: {unexpected[0].name}")
        files = tuple(entry for entry in entries if entry.is_file() and entry.suffix == ".json")
    else:
        raise ValueError("questionnaire path must be a regular file or directory")
    if not files:
        raise ValueError("questionnaire path contains no JSON resources")
    documents: list[dict[str, Any]] = []
    for file in files:
        try:
            value = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid questionnaire JSON: {file.name}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"questionnaire resource must be an object: {file.name}")
        documents.append(value)
    return tuple(documents)


def validate_questionnaire_path(path: Path) -> int:
    """Validate one explicit questionnaire path and emit deterministic evidence."""

    try:
        documents = load_guidance_path(path)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"questionnaire validation refused: {exc}", file=sys.stderr)
        return 2
    result = validate_guidance_bundle(documents)
    if not result.accepted:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "issues": [
                        {"code": issue.code, "message": issue.message, "path": issue.path}
                        for issue in result.issues
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    counts = Counter(document["kind"] for document in documents)
    summary = GuidanceBundleSummary(
        definitions=counts["QuestionnaireDefinition"],
        sessions=counts["QuestionnaireSession"],
        answer_sets=counts["QuestionnaireAnswerSet"],
        business_contexts=counts["BusinessContext"],
        readiness_assessments=counts["DataReadinessAssessment"],
        guidance_rules=counts["GuidanceRule"],
    )
    print(
        json.dumps(
            {
                "accepted": True,
                "mandatoryGates": list(MANDATORY_READINESS_GATES),
                "resources": dict(summary.as_json()),
                "ruleOperators": ["all", "any", "not", "eq", "in", "exists", "gte", "lte"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0
