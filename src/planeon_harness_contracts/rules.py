"""Pure, closed guidance-rule validation and evaluation."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from planeon_harness_contracts.models import RuleProblem, RuleVectorResult

RULE_OPERATORS = frozenset({"all", "any", "not", "eq", "in", "exists", "gte", "lte"})
PATH_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*$")
MAX_RULE_DEPTH = 16
MAX_RULE_NODES = 128
_MISSING = object()


class RuleValidationError(ValueError):
    """Raised when a rule is outside the closed, non-executable grammar."""

    def __init__(self, problems: Sequence[RuleProblem]) -> None:
        self.problems = tuple(problems)
        first = self.problems[0] if self.problems else RuleProblem("INVALID_RULE", "invalid rule")
        super().__init__(f"{first.code}: {first.message}")


def _problem(code: str, message: str, path: tuple[str | int, ...]) -> RuleProblem:
    return RuleProblem(code=code, message=message, path=path)


def _is_scalar(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    return value is None or isinstance(value, (str, bool, int))


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_rule(rule: Mapping[str, Any]) -> tuple[RuleProblem, ...]:
    """Validate a rule without resolving data, importing code, or performing I/O."""

    problems: list[RuleProblem] = []
    node_count = 0

    def walk(candidate: Any, path: tuple[str | int, ...], depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_RULE_NODES:
            problems.append(_problem("RULE_TOO_LARGE", "rule exceeds the node limit", path))
            return
        if depth > MAX_RULE_DEPTH:
            problems.append(_problem("RULE_TOO_DEEP", "rule exceeds the depth limit", path))
            return
        if not isinstance(candidate, Mapping):
            problems.append(_problem("INVALID_RULE", "every rule node must be an object", path))
            return
        operation = candidate.get("op")
        if not isinstance(operation, str) or operation not in RULE_OPERATORS:
            problems.append(
                _problem(
                    "EXECUTABLE_RULE_FORBIDDEN",
                    f"rule operator is not in the closed grammar: {operation!r}",
                    path + ("op",),
                )
            )
            return
        if operation in {"all", "any"}:
            if set(candidate) != {"op", "rules"}:
                problems.append(_problem("RULE_FIELDS_CLOSED", f"{operation} accepts only op and rules", path))
            children = candidate.get("rules")
            if not isinstance(children, list) or not children:
                problems.append(_problem("RULE_CHILD_REQUIRED", f"{operation} requires a non-empty rules list", path))
                return
            for index, child in enumerate(children):
                walk(child, path + ("rules", index), depth + 1)
            return
        if operation == "not":
            if set(candidate) != {"op", "rule"}:
                problems.append(_problem("RULE_FIELDS_CLOSED", "not accepts only op and rule", path))
            if "rule" not in candidate:
                problems.append(_problem("RULE_CHILD_REQUIRED", "not requires one rule", path))
                return
            walk(candidate["rule"], path + ("rule",), depth + 1)
            return
        expected_fields = {"op", "path"} if operation == "exists" else {"op", "path", "value"}
        if set(candidate) != expected_fields:
            problems.append(
                _problem(
                    "RULE_FIELDS_CLOSED",
                    f"{operation} accepts only {', '.join(sorted(expected_fields))}",
                    path,
                )
            )
        fact_path = candidate.get("path")
        if not isinstance(fact_path, str) or PATH_PATTERN.fullmatch(fact_path) is None:
            problems.append(_problem("INVALID_FACT_PATH", "fact path is not a closed dotted identifier", path))
        if operation == "exists":
            return
        value = candidate.get("value", _MISSING)
        if operation == "in":
            if (
                not isinstance(value, list)
                or not value
                or not all(_is_scalar(item) for item in value)
                or len({json.dumps(item, sort_keys=True) for item in value}) != len(value)
            ):
                problems.append(
                    _problem("INVALID_RULE_VALUE", "in requires a non-empty unique scalar list", path)
                )
        elif operation in {"gte", "lte"}:
            if not _is_finite_number(value):
                problems.append(_problem("INVALID_RULE_VALUE", f"{operation} requires a finite number", path))
        elif not _is_scalar(value) and not (
            isinstance(value, list) and all(_is_scalar(item) for item in value)
        ):
            problems.append(_problem("INVALID_RULE_VALUE", "eq accepts only JSON scalars or scalar lists", path))

    walk(rule, (), 0)
    return tuple(problems)


def _resolve(facts: Mapping[str, Any], path: str) -> Any:
    current: Any = facts
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def evaluate_rule(rule: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    """Evaluate a validated rule through mapping lookups and primitive comparisons only."""

    problems = validate_rule(rule)
    if problems:
        raise RuleValidationError(problems)

    def evaluate(candidate: Mapping[str, Any]) -> bool:
        operation = candidate["op"]
        if operation == "all":
            return all(evaluate(child) for child in candidate["rules"])
        if operation == "any":
            return any(evaluate(child) for child in candidate["rules"])
        if operation == "not":
            return not evaluate(candidate["rule"])
        actual = _resolve(facts, candidate["path"])
        if operation == "exists":
            return actual is not _MISSING and actual is not None
        if actual is _MISSING:
            return False
        expected = candidate["value"]
        if operation == "eq":
            return type(actual) is type(expected) and actual == expected
        if operation == "in":
            return any(type(actual) is type(choice) and actual == choice for choice in expected)
        if operation == "gte":
            return _is_finite_number(actual) and actual >= expected
        if operation == "lte":
            return _is_finite_number(actual) and actual <= expected
        raise AssertionError(f"validated operator was not handled: {operation}")

    return evaluate(rule)


def evaluate_vectors(vectors: Sequence[Mapping[str, Any]]) -> bytes:
    """Evaluate named vectors and return byte-stable, lexically ordered JSON lines."""

    ids = [vector.get("id") for vector in vectors]
    if not all(isinstance(vector_id, str) and vector_id for vector_id in ids):
        raise RuleValidationError((RuleProblem("INVALID_VECTOR_ID", "every vector needs an id"),))
    if len(set(ids)) != len(ids):
        raise RuleValidationError((RuleProblem("DUPLICATE_VECTOR_ID", "vector ids must be unique"),))
    results: list[RuleVectorResult] = []
    for vector in vectors:
        if set(vector) != {"id", "facts", "rule"} or not isinstance(vector.get("facts"), Mapping):
            raise RuleValidationError(
                (RuleProblem("INVALID_VECTOR", "vector fields are exactly id, facts, and rule"),)
            )
        rule = vector.get("rule")
        if not isinstance(rule, Mapping):
            raise RuleValidationError((RuleProblem("INVALID_RULE", "vector rule must be an object"),))
        results.append(
            RuleVectorResult(
                vector_id=vector["id"],
                matched=evaluate_rule(rule, vector["facts"]),
            )
        )
    payload = [dict(result.as_json()) for result in sorted(results, key=lambda item: item.vector_id)]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
