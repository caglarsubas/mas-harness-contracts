from __future__ import annotations

import copy
import itertools
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from planeon_harness_contracts.compiler import compile_profile  # noqa: E402
from planeon_harness_contracts.errors import CompilationError  # noqa: E402
from planeon_harness_contracts.graph import topological_waves, transitive_closure  # noqa: E402
from planeon_harness_contracts.registry import load_catalog  # noqa: E402

VALID = ROOT / "tests" / "fixtures" / "compiler" / "valid" / "compile-request.json"
CATALOG_DIGEST = json.loads(
    (ROOT / "contracts" / "catalog.lock.json").read_text(encoding="utf-8")
)["catalogDigest"]


def request() -> dict[str, object]:
    return json.loads(VALID.read_text(encoding="utf-8"))


def resources() -> tuple[dict[str, object], ...]:
    return load_catalog(ROOT / "catalog")


def test_input_and_catalog_order_never_change_output_bytes() -> None:
    baseline_request = request()
    baseline_resources = resources()
    expected = compile_profile(baseline_request, baseline_resources, CATALOG_DIGEST)
    for reverse_requested, reverse_prerequisites, reverse_facts, reverse_catalog in itertools.product(
        (False, True), repeat=4
    ):
        candidate = copy.deepcopy(baseline_request)
        if reverse_requested:
            candidate["demand"]["requestedCapabilities"].reverse()
        if reverse_prerequisites:
            candidate["demand"]["acceptedPrerequisiteHarnessIds"].reverse()
        if reverse_facts:
            candidate["demand"]["environment"]["capabilities"].reverse()
        candidate_resources = tuple(reversed(baseline_resources)) if reverse_catalog else baseline_resources
        assert compile_profile(candidate, candidate_resources, CATALOG_DIGEST) == expected


def test_arbitrary_dag_closure_and_waves_are_lexically_stable() -> None:
    dependencies = {
        "module.a": {"module.b", "module.c"},
        "module.b": {"module.d"},
        "module.c": {"module.d"},
        "module.d": set(),
        "module.unselected": set(),
    }
    assert transitive_closure(("module.a",), dependencies) == (
        "module.a",
        "module.b",
        "module.c",
        "module.d",
    )
    selected = {"module.a", "module.b", "module.c", "module.d"}
    assert topological_waves(selected, dependencies) == (
        ("module.d",),
        ("module.b", "module.c"),
        ("module.a",),
    )


def test_cycles_fail_with_stable_error() -> None:
    graph = {"module.a": {"module.b"}, "module.b": {"module.a"}}
    with pytest.raises(CompilationError) as captured:
        transitive_closure(("module.a",), graph)
    assert captured.value.code == "DEPENDENCY_CYCLE"
    assert captured.value.details["resourceIds"] == ["module.a", "module.b"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maxConcurrentTasks", 0),
        ("maxTaskSeconds", 86401),
        ("maxRetries", -1),
        ("maxToolCalls", 10001),
        ("maxModelTokens", 10000001),
    ],
)
def test_every_execution_budget_dimension_is_bounded(field: str, value: int) -> None:
    candidate = request()
    candidate["demand"]["executionBudget"][field] = value
    with pytest.raises(CompilationError, match="EXECUTION_BUDGET_INVALID"):
        compile_profile(candidate, resources(), CATALOG_DIGEST)


def test_symmetric_selected_conflict_is_never_order_dependent() -> None:
    catalog = list(copy.deepcopy(resources()))
    reason = "The property vector intentionally declares a selected conflict."
    for resource in catalog:
        if resource["metadata"]["id"] == "runtime.infrastructure":
            resource["spec"]["conflicts"].append(
                {"resourceId": "runtime.model-inference", "reason": reason}
            )
        elif resource["metadata"]["id"] == "runtime.model-inference":
            resource["spec"]["conflicts"].append(
                {"resourceId": "runtime.infrastructure", "reason": reason}
            )
    for ordered in (tuple(catalog), tuple(reversed(catalog))):
        with pytest.raises(CompilationError) as captured:
            compile_profile(request(), ordered, CATALOG_DIGEST)
        assert captured.value.code == "HARNESS_CONFLICT"


def test_duplicate_public_capability_ownership_fails_closed() -> None:
    catalog = list(copy.deepcopy(resources()))
    for resource in catalog:
        if resource["metadata"]["id"] == "runtime.infrastructure":
            resource["spec"]["capabilities"].append(
                {
                    "id": "model.local-cpu",
                    "classification": "PUBLIC_DEMAND",
                    "signedAttestationRequired": False,
                }
            )
            break
    with pytest.raises(CompilationError) as captured:
        compile_profile(request(), tuple(catalog), CATALOG_DIGEST)
    assert captured.value.code == "CATALOG_INVALID"
