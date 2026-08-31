"""Immutable value models shared by questionnaire and guidance evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

MANDATORY_READINESS_GATES = (
    "business.owner",
    "business.outcome",
    "data.owner",
    "data.quality",
    "data.completeness",
    "data.freshness",
    "data.provenance",
    "data.classification",
    "integration.readiness",
    "autonomy.boundary",
)


class QuestionnaireState(StrEnum):
    """Closed lifecycle states; state persistence belongs to the control plane."""

    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    READY_FOR_COMPILATION = "READY_FOR_COMPILATION"
    SUPERSEDED = "SUPERSEDED"


class ReadinessStatus(StrEnum):
    """Stable readiness outcomes without a truthy shortcut."""

    PASS = "PASS"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class RuleProblem:
    """One deterministic rule validation problem."""

    code: str
    message: str
    path: tuple[str | int, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleVectorResult:
    """Stable result for one named evaluator vector."""

    vector_id: str
    matched: bool

    def as_json(self) -> Mapping[str, Any]:
        """Return an immutable JSON-compatible view."""

        return MappingProxyType({"id": self.vector_id, "matched": self.matched})


@dataclass(frozen=True, slots=True)
class GuidanceBundleSummary:
    """Counts emitted by the offline questionnaire validator."""

    definitions: int
    sessions: int
    answer_sets: int
    business_contexts: int
    readiness_assessments: int
    guidance_rules: int

    def as_json(self) -> Mapping[str, int]:
        """Return lexically stable public field names."""

        return MappingProxyType(
            {
                "QuestionnaireAnswerSet": self.answer_sets,
                "BusinessContext": self.business_contexts,
                "DataReadinessAssessment": self.readiness_assessments,
                "QuestionnaireDefinition": self.definitions,
                "GuidanceRule": self.guidance_rules,
                "QuestionnaireSession": self.sessions,
            }
        )
