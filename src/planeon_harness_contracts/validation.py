"""Typed validation results used before concrete schemas are introduced."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One stable validation issue without tenant data or executable content."""

    code: str
    message: str
    path: tuple[str | int, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Immutable result returned by every registry validation request."""

    accepted: bool
    issues: tuple[ValidationIssue, ...] = ()

    @classmethod
    def success(cls) -> ValidationResult:
        """Return a result with no findings."""

        return cls(accepted=True)

    @classmethod
    def rejected(cls, *issues: ValidationIssue) -> ValidationResult:
        """Return a rejected result and require at least one precise issue."""

        if not issues:
            raise ValueError("a rejected validation result requires an issue")
        return cls(accepted=False, issues=tuple(issues))


def reject_unregistered_kind(kind: str, _document: Mapping[str, Any]) -> ValidationResult:
    """Fail closed while the bootstrap registry deliberately contains no kinds."""

    return ValidationResult.rejected(
        ValidationIssue(
            code="UNKNOWN_CONTRACT_KIND",
            message=f"contract kind is not registered: {kind}",
        )
    )

