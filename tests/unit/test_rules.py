from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from planeon_harness_contracts.rules import (  # noqa: E402
    RuleValidationError,
    evaluate_rule,
    evaluate_vectors,
    validate_rule,
)

VECTORS = ROOT / "tests" / "fixtures" / "guidance" / "vectors"


def test_rule_vectors_are_byte_identical() -> None:
    vectors = json.loads((VECTORS / "rule-vectors.json").read_text(encoding="utf-8"))
    expected = (VECTORS / "expected-results.json").read_bytes()
    assert evaluate_vectors(vectors) == expected
    assert evaluate_vectors(copy.deepcopy(vectors)) == expected


def test_evaluator_does_not_mutate_rule_or_facts() -> None:
    rule = {
        "op": "all",
        "rules": [
            {"op": "exists", "path": "business.owner"},
            {"op": "in", "path": "autonomy.level", "value": ["READ_ONLY", "RECOMMEND"]},
        ],
    }
    facts = {"business": {"owner": "subject.owner"}, "autonomy": {"level": "READ_ONLY"}}
    rule_before = copy.deepcopy(rule)
    facts_before = copy.deepcopy(facts)
    assert evaluate_rule(rule, facts)
    assert rule == rule_before
    assert facts == facts_before


@pytest.mark.parametrize("operator", ["all", "any", "not", "eq", "in", "exists", "gte", "lte"])
def test_all_declared_operators_are_accepted(operator: str) -> None:
    if operator in {"all", "any"}:
        rule = {"op": operator, "rules": [{"op": "exists", "path": "data.owner"}]}
    elif operator == "not":
        rule = {"op": "not", "rule": {"op": "exists", "path": "data.owner"}}
    elif operator == "exists":
        rule = {"op": "exists", "path": "data.owner"}
    elif operator == "in":
        rule = {"op": "in", "path": "data.classification", "value": ["INTERNAL"]}
    elif operator in {"gte", "lte"}:
        rule = {"op": operator, "path": "data.score", "value": 0.9}
    else:
        rule = {"op": "eq", "path": "data.owner", "value": "subject.owner"}
    assert validate_rule(rule) == ()


def test_executable_and_extra_rule_fields_fail_closed() -> None:
    executable = {"op": "exec", "expression": "open('/tmp/file')"}
    problems = validate_rule(executable)
    assert problems[0].code == "EXECUTABLE_RULE_FORBIDDEN"
    with pytest.raises(RuleValidationError, match="EXECUTABLE_RULE_FORBIDDEN"):
        evaluate_rule(executable, {})

    extra = {"op": "eq", "path": "data.owner", "value": "subject.owner", "template": "x"}
    assert {problem.code for problem in validate_rule(extra)} == {"RULE_FIELDS_CLOSED"}


def test_paths_never_traverse_attributes_or_indices() -> None:
    assert validate_rule({"op": "exists", "path": "__class__.__mro__"})[0].code == "INVALID_FACT_PATH"
    assert validate_rule({"op": "exists", "path": "items.0"})[0].code == "INVALID_FACT_PATH"
    assert not evaluate_rule({"op": "exists", "path": "data.owner"}, {"data": object()})


def test_numeric_comparison_rejects_boolean_values() -> None:
    assert validate_rule({"op": "gte", "path": "data.score", "value": True})[0].code == "INVALID_RULE_VALUE"
    assert not evaluate_rule({"op": "gte", "path": "data.score", "value": 1}, {"data": {"score": True}})


def test_non_finite_numbers_are_never_rule_scalars() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        assert validate_rule({"op": "eq", "path": "data.score", "value": value})[0].code == "INVALID_RULE_VALUE"
        assert validate_rule({"op": "gte", "path": "data.score", "value": value})[0].code == "INVALID_RULE_VALUE"


def test_duplicate_vector_ids_fail_closed() -> None:
    vectors = [
        {"id": "same", "facts": {}, "rule": {"op": "exists", "path": "data.owner"}},
        {"id": "same", "facts": {}, "rule": {"op": "exists", "path": "data.owner"}},
    ]
    with pytest.raises(RuleValidationError, match="DUPLICATE_VECTOR_ID"):
        evaluate_vectors(vectors)
