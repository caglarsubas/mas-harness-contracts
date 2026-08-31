from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from planeon_harness_contracts.compiler import OUTPUT_NAMES, compile_profile  # noqa: E402
from planeon_harness_contracts.errors import CompilationError  # noqa: E402
from planeon_harness_contracts.registry import load_catalog  # noqa: E402

FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "compiler"
VALID = FIXTURE_ROOT / "valid"
CATALOG = ROOT / "catalog"
CATALOG_DIGEST = json.loads(
    (ROOT / "contracts" / "catalog.lock.json").read_text(encoding="utf-8")
)["catalogDigest"]


def request() -> dict[str, object]:
    return json.loads((VALID / "compile-request.json").read_text(encoding="utf-8"))


def resources() -> tuple[dict[str, object], ...]:
    return load_catalog(CATALOG)


def compile_valid(value: dict[str, object] | None = None) -> dict[str, bytes]:
    return dict(compile_profile(value or request(), resources(), CATALOG_DIGEST))


def error_code(value: dict[str, object]) -> str:
    with pytest.raises(CompilationError) as captured:
        compile_profile(value, resources(), CATALOG_DIGEST)
    return captured.value.code


def test_valid_profile_is_closed_planned_and_explicit() -> None:
    outputs = compile_valid()
    assert tuple(outputs) == OUTPUT_NAMES
    profile_document = json.loads(outputs["profile.json"])
    profile = profile_document["profile"]
    assert profile["spec"]["state"] == "PLANNED"
    assert profile["spec"]["selectedHarnessIds"] == [
        "runtime.infrastructure",
        "runtime.model-inference",
        "trust.observability-finops",
        "trust.security-safety",
    ]
    assert profile["spec"]["selectedProviderIds"] == [
        "provider.planeon.llamacpp",
        "provider.runtime.infrastructure.kubernetes-upstream",
    ]
    assert profile_document["executionBudget"]["spec"]["overflowDisposition"] == "BLOCK"
    bom = json.loads(outputs["bom.json"])
    assert all(entry["installUnits"] for entry in bom["spec"]["entries"])
    assert {
        unit["digestStatus"]
        for entry in bom["spec"]["entries"]
        for unit in entry["installUnits"]
    } == {"MISSING_PLANNED"}
    assert json.loads(outputs["evidence-plan.json"])["spec"]["tenantAcceptanceIncluded"] is False


def test_recommendations_never_mutate_explicit_provider_selection() -> None:
    profile = json.loads(compile_valid()["profile.json"])["profile"]["spec"]
    model_proposal = next(
        item for item in profile["proposedSelectors"] if item["groupId"] == "group.model-backend"
    )
    assert model_proposal == {
        "groupId": "group.model-backend",
        "selectorCapabilities": ["provider.planeon.llamacpp", "provider.planeon.ollama"],
        "disposition": "PROPOSED_SELECTOR_ONLY",
    }
    assert profile["selectedProviderIds"] == [
        "provider.planeon.llamacpp",
        "provider.runtime.infrastructure.kubernetes-upstream",
    ]


def test_install_waves_are_dependency_first() -> None:
    plan = json.loads(compile_valid()["install-plan.json"])["spec"]
    position = {
        resource_id: wave["index"]
        for wave in plan["waves"]
        for resource_id in wave["resourceIds"]
    }
    assert position["provider.planeon.llamacpp"] < position["module.runtime.model-inference.core"]
    assert position["module.runtime.infrastructure.core"] < position["module.trust.security-safety.core"]
    assert position["module.trust.security-safety.core"] < position["module.runtime.model-inference.core"]


def test_closed_negative_vectors() -> None:
    expected = json.loads(
        (FIXTURE_ROOT / "invalid" / "expected-errors.json").read_text(encoding="utf-8")
    )
    vectors: dict[str, dict[str, object]] = {}

    missing = request()
    missing["demand"]["requestedCapabilities"].remove("provider.planeon.llamacpp")
    vectors["missing-selector"] = missing

    ambiguous = request()
    ambiguous["demand"]["requestedCapabilities"].append("provider.planeon.ollama")
    vectors["ambiguous-provider"] = ambiguous

    inactive = request()
    inactive["demand"]["requestedCapabilities"].append("protocol.provider.mcp")
    vectors["inactive-selector"] = inactive

    role = request()
    role["demand"]["requestedCapabilities"].append("connectivity.airgap")
    vectors["environment-fact-as-demand"] = role

    prerequisites = request()
    prerequisites["demand"]["acceptedPrerequisiteHarnessIds"].remove("trust.security-safety")
    vectors["incomplete-prerequisites"] = prerequisites

    unavailable = request()
    unavailable["demand"]["requestedCapabilities"].remove("provider.planeon.llamacpp")
    unavailable["demand"]["requestedCapabilities"].append("provider.planeon.mlx")
    vectors["provider-incompatible"] = unavailable

    judge = request()
    judge["demand"]["requestedCapabilities"].remove("model.local-cpu")
    judge["demand"]["requestedCapabilities"].remove("provider.planeon.llamacpp")
    judge["demand"]["requestedCapabilities"].append("assurance.local-model-judge")
    vectors["local-judge-without-model-class"] = judge

    assert {name: error_code(value) for name, value in sorted(vectors.items())} == expected


def test_subject_harness_adds_only_subject_applicable_closure() -> None:
    value = request()
    value["demand"]["requestedCapabilities"].append("assurance.required")
    value["demand"]["assuranceSubjects"]["harnessIds"] = ["knowledge.data-integration"]
    value["demand"]["acceptedPrerequisiteHarnessIds"] = [
        "knowledge.data-integration",
        "knowledge.domain-semantic",
        "trust.governance-agentops",
        "trust.observability-finops",
        "trust.security-safety",
    ]
    profile = json.loads(compile_valid(value)["profile.json"])["profile"]["spec"]
    assert "knowledge.data-integration" in profile["selectedHarnessIds"]
    assert "knowledge.domain-semantic" in profile["selectedHarnessIds"]
    assert profile["assuranceSubjects"]["harnessIds"] == ["knowledge.data-integration"]


def test_blocked_readiness_and_unbounded_budget_fail_before_output() -> None:
    blocked = request()
    blocked["readinessAssessment"]["spec"]["overallStatus"] = "BLOCKED"
    blocked["readinessAssessment"]["spec"]["gateResults"][0]["status"] = "BLOCKED"
    blocked["readinessAssessment"]["spec"]["gateResults"][0]["evidenceIds"] = []
    blocked["readinessAssessment"]["spec"]["missingGateIds"] = ["business.owner"]
    assert error_code(blocked) == "READINESS_BLOCKED"

    unbounded = request()
    unbounded["demand"]["executionBudget"]["maxRetries"] = 101
    assert error_code(unbounded) == "EXECUTION_BUDGET_INVALID"


def test_composition_schemas_and_compiled_outputs_validate_without_retrieval() -> None:
    schema_paths = sorted((ROOT / "schemas" / "v1alpha1" / "composition").glob("*.json"))
    schema_paths += sorted((ROOT / "schemas" / "v1alpha1" / "guidance").glob("*.json"))
    schema_paths += sorted((ROOT / "schemas" / "v1alpha1" / "readiness").glob("*.json"))
    schemas = [json.loads(path.read_text(encoding="utf-8")) for path in schema_paths]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    by_title = {schema.get("title"): schema for schema in schemas if schema.get("title")}
    Draft202012Validator(by_title["CompileRequest"], registry=registry).validate(request())
    outputs = compile_valid()
    documents = {
        "CompiledProfileDocument": json.loads(outputs["profile.json"]),
        "BillOfMaterials": json.loads(outputs["bom.json"]),
        "InstallPlan": json.loads(outputs["install-plan.json"]),
        "EvidencePlan": json.loads(outputs["evidence-plan.json"]),
    }
    for title, document in documents.items():
        Draft202012Validator(by_title[title], registry=registry).validate(document)
