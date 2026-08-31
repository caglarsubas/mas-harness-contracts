"""Deterministic, recommendation-safe tenant harness profile compiler."""

from __future__ import annotations

import json
import re
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from planeon_harness_contracts.canonical import bytes_sha256, canonical_json_bytes
from planeon_harness_contracts.errors import CompilationError
from planeon_harness_contracts.graph import topological_waves, transitive_closure
from planeon_harness_contracts.questionnaire import validate_guidance_document
from planeon_harness_contracts.registry import expected_catalog_lock, load_catalog
from planeon_harness_contracts.validation import (
    API_VERSION,
    capability_roles,
    validate_catalog,
    validate_harness_selection,
)

COMPILE_REQUEST_VERSION = "harness.planeon.ai/compile-request/v1alpha1"
COMPILED_PROFILE_VERSION = "harness.planeon.ai/compiled-profile-document/v1alpha1"
OUTPUT_NAMES = (
    "profile.json",
    "bom.json",
    "install-plan.json",
    "evidence-plan.json",
    "explanation.md",
    "profile.sha256",
)
STABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
BUDGET_BOUNDS: Mapping[str, tuple[int, int]] = {
    "maxConcurrentTasks": (1, 1024),
    "maxTaskSeconds": (1, 86400),
    "maxRetries": (0, 100),
    "maxToolCalls": (0, 10000),
    "maxModelTokens": (0, 10000000),
}
ENVIRONMENT_VALUES: Mapping[str, frozenset[str]] = {
    "deploymentMode": frozenset(
        {"operator-hosted-saas", "tenant-public-cloud", "self-managed", "air-gapped"}
    ),
    "architecture": frozenset({"amd64", "arm64", "platform-supplied"}),
    "operatingSystem": frozenset({"linux", "macos", "platform-supplied"}),
    "kubernetesDistribution": frozenset(
        {"upstream", "k3s", "openshift", "none", "platform-supplied"}
    ),
}


def _resource_id(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata")
    if not isinstance(metadata, Mapping):
        return ""
    value = metadata.get("id")
    return value if isinstance(value, str) else ""


def _spec(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    value = resource.get("spec")
    return value if isinstance(value, Mapping) else {}


def _mapping_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        return ()
    return tuple(value)


def _stable_id(value: Any) -> bool:
    return isinstance(value, str) and STABLE_ID_PATTERN.fullmatch(value) is not None


def _closed_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CompilationError(
            "INVALID_COMBINATION",
            f"{label} fields are closed",
            {"expectedFields": sorted(fields)},
        )
    return value


def _stable_id_list(value: Any, label: str, *, non_empty: bool = False) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (non_empty and not value)
        or not all(_stable_id(item) for item in value)
        or len(value) != len(set(value))
    ):
        raise CompilationError(
            "INVALID_COMBINATION",
            f"{label} must contain unique stable ids",
        )
    return tuple(sorted(value))


def _validate_budget(value: Any) -> dict[str, int]:
    budget = _closed_mapping(value, set(BUDGET_BOUNDS), "execution budget")
    normalized: dict[str, int] = {}
    for field, (minimum, maximum) in BUDGET_BOUNDS.items():
        amount = budget.get(field)
        if (
            not isinstance(amount, int)
            or isinstance(amount, bool)
            or not minimum <= amount <= maximum
        ):
            raise CompilationError(
                "EXECUTION_BUDGET_INVALID",
                f"{field} must be an integer from {minimum} through {maximum}",
                {"field": field, "maximum": maximum, "minimum": minimum},
            )
        normalized[field] = amount
    return dict(sorted(normalized.items()))


def _validate_request(request: Mapping[str, Any]) -> dict[str, Any]:
    _closed_mapping(
        request,
        {"schemaVersion", "metadata", "questionnaireAnswerSet", "readinessAssessment", "demand"},
        "compile request",
    )
    if request.get("schemaVersion") != COMPILE_REQUEST_VERSION:
        raise CompilationError("INVALID_COMBINATION", "compile request version is not supported")
    metadata = _closed_mapping(
        request.get("metadata"),
        {"tenantId", "demandId", "profileId", "version"},
        "compile request metadata",
    )
    for field in ("tenantId", "demandId", "profileId"):
        if not _stable_id(metadata.get(field)):
            raise CompilationError("INVALID_COMBINATION", f"metadata {field} is not a stable id")
    version = metadata.get("version")
    if not isinstance(version, str) or SEMVER_PATTERN.fullmatch(version) is None:
        raise CompilationError("INVALID_COMBINATION", "metadata version must be semantic")

    answers = request.get("questionnaireAnswerSet")
    readiness = request.get("readinessAssessment")
    if not isinstance(answers, Mapping) or answers.get("kind") != "QuestionnaireAnswerSet":
        raise CompilationError("INVALID_COMBINATION", "request requires QuestionnaireAnswerSet")
    if not isinstance(readiness, Mapping) or readiness.get("kind") != "DataReadinessAssessment":
        raise CompilationError("INVALID_COMBINATION", "request requires DataReadinessAssessment")
    for resource in (answers, readiness):
        result = validate_guidance_document(resource)
        if not result.accepted:
            issue = result.issues[0]
            raise CompilationError(issue.code, issue.message, {"path": list(issue.path)})
    if _spec(answers).get("status") != "SUBMITTED":
        raise CompilationError("NEEDS_INPUT", "questionnaire answer set must be submitted")
    if _spec(readiness).get("overallStatus") != "READY" or _spec(readiness).get("missingGateIds"):
        raise CompilationError(
            "READINESS_BLOCKED",
            "all mandatory readiness gates must pass before compilation",
            {"readinessAssessmentId": _resource_id(readiness)},
        )
    if _spec(answers).get("questionnaireSessionId") != _spec(readiness).get(
        "questionnaireSessionId"
    ):
        raise CompilationError(
            "INVALID_COMBINATION",
            "answer and readiness resources must reference one questionnaire session",
        )

    demand = _closed_mapping(
        request.get("demand"),
        {
            "requestedCapabilities",
            "acceptedPrerequisiteHarnessIds",
            "environment",
            "assuranceSubjects",
            "executionBudget",
        },
        "demand declaration",
    )
    requested = _stable_id_list(demand.get("requestedCapabilities"), "requestedCapabilities", non_empty=True)
    prerequisites = _stable_id_list(
        demand.get("acceptedPrerequisiteHarnessIds"),
        "acceptedPrerequisiteHarnessIds",
    )
    environment = _closed_mapping(
        demand.get("environment"),
        {
            "tenantId",
            "deploymentMode",
            "architecture",
            "operatingSystem",
            "kubernetesDistribution",
            "capabilities",
            "attestationDigest",
            "signatureStatus",
        },
        "environment",
    )
    if environment.get("tenantId") != metadata.get("tenantId"):
        raise CompilationError(
            "TENANT_BOUNDARY_MISMATCH",
            "environment attestation tenant must match the compile request tenant",
        )
    for field, allowed in ENVIRONMENT_VALUES.items():
        if environment.get(field) not in allowed:
            raise CompilationError("INVALID_COMBINATION", f"environment {field} is invalid")
    environment_capabilities = _stable_id_list(
        environment.get("capabilities"),
        "environment capabilities",
        non_empty=True,
    )
    digest = environment.get("attestationDigest")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        raise CompilationError(
            "ENVIRONMENT_ATTESTATION_REQUIRED",
            "environment facts require a locked SHA-256 attestation",
        )
    if environment.get("signatureStatus") != "VERIFIED":
        raise CompilationError(
            "ENVIRONMENT_ATTESTATION_REQUIRED",
            "environment facts require a verified signature",
        )
    required_fact = {
        "amd64": "architecture.amd64-available",
        "arm64": "architecture.arm64-available",
    }.get(environment["architecture"])
    if required_fact and required_fact not in environment_capabilities:
        raise CompilationError(
            "PLATFORM_CAPABILITY_MISSING",
            "architecture fact is missing from the signed environment",
            {"capability": required_fact},
        )
    connectivity_fact = (
        "connectivity.airgap"
        if environment["deploymentMode"] == "air-gapped"
        else "connectivity.connected"
    )
    if connectivity_fact not in environment_capabilities:
        raise CompilationError(
            "PLATFORM_CAPABILITY_MISSING",
            "connectivity fact is missing from the signed environment",
            {"capability": connectivity_fact},
        )

    assurance = _closed_mapping(
        demand.get("assuranceSubjects"),
        {"harnessIds", "capabilityIds"},
        "assurance subjects",
    )
    return {
        "metadata": dict(metadata),
        "answers": answers,
        "readiness": readiness,
        "requested": requested,
        "prerequisites": prerequisites,
        "environment": {
            **dict(environment),
            "capabilities": list(environment_capabilities),
        },
        "subjectHarnesses": _stable_id_list(
            assurance.get("harnessIds"), "assurance subject harnesses"
        ),
        "subjectCapabilities": _stable_id_list(
            assurance.get("capabilityIds"), "assurance subject capabilities"
        ),
        "budget": _validate_budget(demand.get("executionBudget")),
    }


def _compatible(spec: Mapping[str, Any], environment: Mapping[str, Any]) -> bool:
    compatibility = spec.get("compatibility")
    if not isinstance(compatibility, Mapping):
        return False
    checks = (
        ("deploymentModes", environment["deploymentMode"], False),
        ("architectures", environment["architecture"], True),
        ("operatingSystems", environment["operatingSystem"], True),
        ("kubernetesDistributions", environment["kubernetesDistribution"], True),
    )
    for field, value, platform_wildcard in checks:
        choices = compatibility.get(field)
        if not isinstance(choices, list):
            return False
        if value not in choices and not (platform_wildcard and "platform-supplied" in choices):
            return False
    return True


def _provider_resolution(
    resources: Sequence[Mapping[str, Any]],
    requested: tuple[str, ...],
    environment: Mapping[str, Any],
) -> tuple[tuple[dict[str, str], ...], tuple[dict[str, Any], ...]]:
    public, environment_roles, groups = capability_roles(resources)
    selectors: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for group_id, providers in groups.items():
        for provider in providers:
            selector = _spec(provider).get("selectorCapability")
            if isinstance(selector, str):
                selectors[selector] = (group_id, provider)
    unknown = set(requested) - set(public) - set(environment_roles) - set(selectors)
    if unknown:
        raise CompilationError(
            "INVALID_CAPABILITY_ROLE",
            "capability is INTERNAL_ONLY unless registered",
            {"capability": sorted(unknown)[0]},
        )
    invalid_facts = set(requested) & set(environment_roles)
    if invalid_facts:
        raise CompilationError(
            "INVALID_CAPABILITY_ROLE",
            "environment facts cannot be requested as tenant demand",
            {"capability": sorted(invalid_facts)[0]},
        )
    environment_capabilities = set(environment["capabilities"])
    invalid_environment = environment_capabilities - set(environment_roles)
    if invalid_environment:
        raise CompilationError(
            "INVALID_CAPABILITY_ROLE",
            "signed environment input accepts only ENVIRONMENT_FACT capabilities",
            {"capability": sorted(invalid_environment)[0]},
        )

    requested_set = set(requested)
    selected_selectors = requested_set & set(selectors)
    for selector in sorted(selected_selectors):
        _, provider = selectors[selector]
        activations = set(_spec(provider).get("activatedByCapabilities", []))
        if not activations.intersection(requested_set):
            raise CompilationError(
                "INVALID_COMBINATION",
                "selector is inactive for the accepted tenant demand",
                {"selectorCapability": selector},
            )

    selections: list[dict[str, str]] = []
    proposals: list[dict[str, Any]] = []
    for group_id, providers in groups.items():
        activations = {
            capability
            for provider in providers
            for capability in _spec(provider).get("activatedByCapabilities", [])
            if isinstance(capability, str)
        }
        if not activations.intersection(requested_set):
            continue
        compatible = sorted(
            (
                provider
                for provider in providers
                if set(_spec(provider).get("activatedByCapabilities", [])).intersection(requested_set)
                and _compatible(_spec(provider), environment)
            ),
            key=_resource_id,
        )
        proposal_selectors = sorted(
            selector
            for provider in compatible
            if isinstance((selector := _spec(provider).get("selectorCapability")), str)
        )
        proposals.append(
            {
                "groupId": group_id,
                "selectorCapabilities": proposal_selectors,
                "disposition": "PROPOSED_SELECTOR_ONLY",
            }
        )
        group_selectors = {
            selector
            for provider in providers
            if isinstance((selector := _spec(provider).get("selectorCapability")), str)
        }
        choices = sorted(selected_selectors & group_selectors)
        if not choices:
            if not proposal_selectors:
                raise CompilationError(
                    "PROVIDER_UNAVAILABLE",
                    "active provider group has no compatible member",
                    {"groupId": group_id},
                )
            raise CompilationError(
                "NEEDS_INPUT",
                "active provider group requires one explicitly accepted selector",
                {"groupId": group_id, "proposedSelectors": proposal_selectors},
            )
        if len(choices) > 1:
            raise CompilationError(
                "AMBIGUOUS_PROVIDER",
                "active provider group has multiple accepted selectors",
                {"groupId": group_id, "selectorCapabilities": choices},
            )
        selector = choices[0]
        provider = selectors[selector][1]
        if not _compatible(_spec(provider), environment):
            raise CompilationError(
                "PROVIDER_UNAVAILABLE",
                "accepted provider selector is incompatible with signed environment facts",
                {"groupId": group_id, "selectorCapability": selector},
            )
        selections.append(
            {
                "groupId": group_id,
                "selectorCapability": selector,
                "providerId": _resource_id(provider),
            }
        )
    return tuple(sorted(selections, key=lambda item: item["groupId"])), tuple(
        sorted(proposals, key=lambda item: item["groupId"])
    )


def _install_units(resource: Mapping[str, Any]) -> list[dict[str, Any]]:
    units = _mapping_items(_spec(resource).get("installUnits"))
    if not units:
        raise CompilationError(
            "CLOSURE_INCOMPLETE",
            "selected catalog resource has no install units",
            {"resourceId": _resource_id(resource)},
        )
    return [
        {
            "id": unit["id"],
            "type": unit["type"],
            "artifactName": unit["artifactName"],
            "digestStatus": "MISSING_PLANNED",
            "digest": None,
        }
        for unit in sorted(units, key=lambda item: str(item.get("id")))
    ]


def compile_profile(
    request: Mapping[str, Any],
    resources: Sequence[Mapping[str, Any]],
    catalog_digest: str,
) -> Mapping[str, bytes]:
    """Compile six deterministic outputs without selecting, fetching, or installing implicitly."""

    normalized = _validate_request(request)
    if not isinstance(catalog_digest, str) or SHA256_PATTERN.fullmatch(catalog_digest) is None:
        raise CompilationError("CATALOG_INVALID", "catalog digest must be a locked SHA-256")
    catalog_validation = validate_catalog(resources)
    if not catalog_validation.accepted:
        issue = catalog_validation.issues[0]
        raise CompilationError("CATALOG_INVALID", issue.message, {"catalogCode": issue.code})

    by_id = {_resource_id(resource): resource for resource in resources}
    harnesses = {
        resource_id: resource
        for resource_id, resource in by_id.items()
        if resource.get("kind") == "HarnessClassDefinition"
    }
    modules = {
        resource_id: resource
        for resource_id, resource in by_id.items()
        if resource.get("kind") == "HarnessModuleDefinition"
    }
    public, _, _ = capability_roles(resources)
    requested = normalized["requested"]
    requested_public = set(requested) & set(public)
    subject_harnesses = set(normalized["subjectHarnesses"])
    subject_capabilities = set(normalized["subjectCapabilities"])
    unknown_subjects = subject_harnesses - set(harnesses)
    if unknown_subjects:
        raise CompilationError(
            "INVALID_COMBINATION",
            "assurance subject harness is not registered",
            {"harnessId": sorted(unknown_subjects)[0]},
        )
    if not subject_capabilities.issubset(requested_public):
        raise CompilationError(
            "INVALID_CAPABILITY_ROLE",
            "assurance subject capabilities must be accepted public demand",
            {"capabilityIds": sorted(subject_capabilities - requested_public)},
        )
    if (subject_harnesses or subject_capabilities) and not {
        "assurance.required",
        "assurance.local-model-judge",
    }.intersection(requested_public):
        raise CompilationError(
            "INVALID_COMBINATION",
            "assurance subjects require an explicitly requested assurance capability",
        )
    if "assurance.local-model-judge" in requested_public and not {
        "model.local-cpu",
        "model.local-gpu",
    }.intersection(requested_public):
        raise CompilationError(
            "NEEDS_INPUT",
            "local model judging requires an explicitly accepted local model class",
            {"requiredAnyCapabilities": ["model.local-cpu", "model.local-gpu"]},
        )

    selections, proposals = _provider_resolution(
        resources,
        requested,
        normalized["environment"],
    )
    capability_owners: dict[str, str] = {}
    for harness_id, harness in harnesses.items():
        for capability in _mapping_items(_spec(harness).get("capabilities")):
            if capability.get("classification") == "PUBLIC_DEMAND":
                capability_id = str(capability["id"])
                existing_owner = capability_owners.get(capability_id)
                if existing_owner is not None and existing_owner != harness_id:
                    raise CompilationError(
                        "CATALOG_INVALID",
                        "public capability has more than one harness owner",
                        {"capability": capability_id},
                    )
                capability_owners[capability_id] = harness_id
    direct_harnesses = {
        capability_owners[capability]
        for capability in requested_public
        if capability in capability_owners
    }
    direct_harnesses.update(_spec(by_id[item["providerId"]])["harnessId"] for item in selections)

    harness_dependencies: dict[str, set[str]] = {harness_id: set() for harness_id in harnesses}
    production_gates: list[dict[str, str]] = []
    for harness_id, harness in harnesses.items():
        for dependency in _mapping_items(_spec(harness).get("dependencies")):
            target = dependency.get("harnessId")
            dependency_type = dependency.get("type")
            conditions = set(dependency.get("whenCapabilities", []))
            if dependency_type == "ALWAYS":
                harness_dependencies[harness_id].add(str(target))
            elif dependency_type == "WHEN_CAPABILITY" and conditions.intersection(requested_public):
                harness_dependencies[harness_id].add(str(target))
            elif dependency_type == "SUBJECT_UNDER_EVALUATION" and (
                target in subject_harnesses or conditions.intersection(subject_capabilities)
            ):
                harness_dependencies[harness_id].add(str(target))
            elif dependency_type == "PRODUCTION_GATE":
                production_gates.append(
                    {"harnessId": harness_id, "gateId": str(dependency.get("gateId"))}
                )
    selected_harnesses = set(transitive_closure(direct_harnesses, harness_dependencies))
    conflict_result = validate_harness_selection(resources, selected_harnesses)
    if not conflict_result.accepted:
        issue = conflict_result.issues[0]
        raise CompilationError(issue.code, issue.message)
    accepted_prerequisites = set(normalized["prerequisites"])
    required_prerequisites = selected_harnesses - direct_harnesses
    missing_prerequisites = required_prerequisites - accepted_prerequisites
    if missing_prerequisites:
        raise CompilationError(
            "PREREQUISITE_NOT_ACCEPTED",
            "required prerequisite harnesses need explicit tenant acceptance",
            {"harnessIds": sorted(missing_prerequisites)},
        )
    surplus_prerequisites = accepted_prerequisites - required_prerequisites
    if surplus_prerequisites:
        raise CompilationError(
            "INVALID_COMBINATION",
            "accepted prerequisite list contains a harness outside derived closure",
            {"harnessIds": sorted(surplus_prerequisites)},
        )

    module_dependencies = {
        module_id: set(_spec(module).get("requiresModules", []))
        for module_id, module in modules.items()
    }
    module_seeds = {
        module_id
        for harness_id in selected_harnesses
        for module_id in _spec(harnesses[harness_id]).get("moduleIds", [])
    }
    selected_modules = set(transitive_closure(module_seeds, module_dependencies))
    module_harnesses = {_spec(modules[module_id]).get("harnessId") for module_id in selected_modules}
    if not module_harnesses.issubset(selected_harnesses):
        raise CompilationError(
            "CLOSURE_INCOMPLETE",
            "module closure introduces a harness outside accepted prerequisite closure",
            {"harnessIds": sorted(module_harnesses - selected_harnesses)},
        )
    for module_id in sorted(selected_modules):
        module = modules[module_id]
        if not _compatible(_spec(module), normalized["environment"]):
            raise CompilationError(
                "PLATFORM_CAPABILITY_MISSING",
                "selected module is incompatible with signed environment facts",
                {"moduleId": module_id},
            )
        license_contract = _spec(module).get("license")
        if not isinstance(license_contract, Mapping) or license_contract.get("releaseAdmission") != "ALLOWED":
            raise CompilationError(
                "PROVIDER_UNAVAILABLE",
                "selected module lacks an allowed open-source release disposition",
                {"moduleId": module_id},
            )

    selected_provider_ids = {item["providerId"] for item in selections}
    install_dependencies: dict[str, set[str]] = {
        module_id: set(module_dependencies[module_id]).intersection(selected_modules)
        for module_id in selected_modules
    }
    install_dependencies.update({provider_id: set() for provider_id in selected_provider_ids})
    for selection in selections:
        provider_id = selection["providerId"]
        harness_id = _spec(by_id[provider_id])["harnessId"]
        for module_id in _spec(harnesses[harness_id]).get("moduleIds", []):
            if module_id in install_dependencies:
                install_dependencies[module_id].add(provider_id)
    waves = topological_waves(install_dependencies, install_dependencies)

    metadata = normalized["metadata"]
    version = metadata["version"]
    suffix = metadata["profileId"].split(".", maxsplit=1)[-1]
    budget_id = f"budget.{suffix}"
    demand_resource = {
        "apiVersion": API_VERSION,
        "kind": "TenantDemand",
        "metadata": {"id": metadata["demandId"], "version": version},
        "spec": {
            "tenantId": metadata["tenantId"],
            "questionnaireAnswerSetId": _resource_id(normalized["answers"]),
            "readinessAssessmentId": _resource_id(normalized["readiness"]),
            "requestedCapabilities": list(requested),
            "acceptedPrerequisiteHarnessIds": sorted(accepted_prerequisites),
            "environment": normalized["environment"],
            "assuranceSubjects": {
                "harnessIds": sorted(subject_harnesses),
                "capabilityIds": sorted(subject_capabilities),
            },
            "executionBudget": normalized["budget"],
        },
    }
    budget_resource = {
        "apiVersion": API_VERSION,
        "kind": "ExecutionBudget",
        "metadata": {"id": budget_id, "version": version},
        "spec": {
            **normalized["budget"],
            "enforcement": "REQUIRED",
            "overflowDisposition": "BLOCK",
        },
    }
    profile_resource = {
        "apiVersion": API_VERSION,
        "kind": "HarnessProfile",
        "metadata": {"id": metadata["profileId"], "version": version},
        "spec": {
            "state": "PLANNED",
            "tenantId": metadata["tenantId"],
            "catalogDigest": catalog_digest,
            "tenantDemandId": metadata["demandId"],
            "readinessAssessmentId": _resource_id(normalized["readiness"]),
            "readinessStatus": "READY",
            "requestedCapabilities": list(requested),
            "directHarnessIds": sorted(direct_harnesses),
            "selectedHarnessIds": sorted(selected_harnesses),
            "acceptedPrerequisiteHarnessIds": sorted(accepted_prerequisites),
            "selectedModuleIds": sorted(selected_modules),
            "selectedProviderIds": sorted(selected_provider_ids),
            "providerSelections": list(selections),
            "proposedSelectors": list(proposals),
            "assuranceSubjects": {
                "harnessIds": sorted(subject_harnesses),
                "capabilityIds": sorted(subject_capabilities),
            },
            "executionBudgetId": budget_id,
            "environmentAttestationDigest": normalized["environment"]["attestationDigest"],
        },
    }
    profile_document = {
        "schemaVersion": COMPILED_PROFILE_VERSION,
        "tenantDemand": demand_resource,
        "profile": profile_resource,
        "executionBudget": budget_resource,
    }

    bom_entries: list[dict[str, Any]] = []
    for resource_id, resource_kind in [
        *((module_id, "MODULE") for module_id in selected_modules),
        *((provider_id, "PROVIDER") for provider_id in selected_provider_ids),
    ]:
        resource = by_id[resource_id]
        bom_entries.append(
            {
                "resourceId": resource_id,
                "resourceKind": resource_kind,
                "harnessId": _spec(resource)["harnessId"],
                "sourceVersion": resource["metadata"]["version"],
                "installUnits": _install_units(resource),
            }
        )
    bom_resource = {
        "apiVersion": API_VERSION,
        "kind": "BillOfMaterials",
        "metadata": {"id": f"bom.{suffix}", "version": version},
        "spec": {
            "state": "PLANNED",
            "profileId": metadata["profileId"],
            "catalogDigest": catalog_digest,
            "entries": sorted(bom_entries, key=lambda item: item["resourceId"]),
        },
    }
    install_plan = {
        "apiVersion": API_VERSION,
        "kind": "InstallPlan",
        "metadata": {"id": f"install-plan.{suffix}", "version": version},
        "spec": {
            "state": "PLANNED",
            "profileId": metadata["profileId"],
            "waves": [
                {"index": index, "resourceIds": list(wave)}
                for index, wave in enumerate(waves)
            ],
            "healthCheckRequired": True,
            "rollbackRequired": True,
            "uninstallSupported": True,
            "tenantDataRetention": "RETAIN_BY_DEFAULT",
        },
    }
    evidence_plan = {
        "apiVersion": API_VERSION,
        "kind": "EvidencePlan",
        "metadata": {"id": f"evidence-plan.{suffix}", "version": version},
        "spec": {
            "state": "PLANNED",
            "profileId": metadata["profileId"],
            "harnessRequirements": [
                {
                    "harnessId": harness_id,
                    "evidenceTypes": sorted(_spec(harnesses[harness_id])["evidenceRequirements"]),
                }
                for harness_id in sorted(selected_harnesses)
            ],
            "productionGates": sorted(
                (
                    gate
                    for gate in production_gates
                    if gate["harnessId"] in selected_harnesses
                ),
                key=lambda item: (item["harnessId"], item["gateId"]),
            ),
            "assuranceSubjects": {
                "harnessIds": sorted(subject_harnesses),
                "capabilityIds": sorted(subject_capabilities),
            },
            "evidenceState": "MISSING_PLANNED",
            "tenantAcceptanceIncluded": False,
        },
    }

    explanation_lines = [
        "# Harness profile explanation",
        "",
        f"- Tenant demand: `{metadata['demandId']}`",
        f"- Readiness: `READY` from `{_resource_id(normalized['readiness'])}`",
        f"- Catalog: `{catalog_digest}`",
        f"- Direct harnesses: {', '.join(sorted(direct_harnesses))}",
        f"- Accepted prerequisites: {', '.join(sorted(accepted_prerequisites))}",
        f"- Selected harnesses: {', '.join(sorted(selected_harnesses))}",
        "",
        "## Explicit provider choices",
        "",
        *(
            f"- `{item['groupId']}`: `{item['selectorCapability']}` -> `{item['providerId']}`"
            for item in selections
        ),
        "",
        "## Recommendation-only candidates",
        "",
        *(
            f"- `{item['groupId']}`: "
            f"{', '.join(f'`{value}`' for value in item['selectorCapabilities'])} "
            "(`PROPOSED_SELECTOR_ONLY`)"
            for item in proposals
        ),
        "",
        "## Evidence boundary",
        "",
        "All resources and install units remain `PLANNED` or `MISSING_PLANNED`.",
        "Compilation proves no artifact, deployment, runtime, assurance, or tenant acceptance.",
        "",
    ]
    profile_bytes = canonical_json_bytes(profile_document)
    outputs: dict[str, bytes] = {
        "profile.json": profile_bytes,
        "bom.json": canonical_json_bytes(bom_resource),
        "install-plan.json": canonical_json_bytes(install_plan),
        "evidence-plan.json": canonical_json_bytes(evidence_plan),
        "explanation.md": "\n".join(explanation_lines).encode("utf-8"),
        "profile.sha256": f"{bytes_sha256(profile_bytes)}\n".encode("ascii"),
    }
    if tuple(outputs) != OUTPUT_NAMES:
        raise AssertionError("compiler output registry drifted")
    return outputs


def write_compilation_outputs(directory: Path, outputs: Mapping[str, bytes]) -> None:
    """Write the exact six outputs only into a clean, non-linked directory."""

    if directory.is_symlink() or not directory.is_dir():
        raise CompilationError("OUTPUT_PATH_INVALID", "output path must be a regular directory")
    if any(directory.iterdir()):
        raise CompilationError("OUTPUT_PATH_INVALID", "output path must be empty")
    if tuple(outputs) != OUTPUT_NAMES:
        raise CompilationError("OUTPUT_SET_INVALID", "compiler output set is not closed")
    for name in OUTPUT_NAMES:
        (directory / name).write_bytes(outputs[name])


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CompilationError("INPUT_PATH_INVALID", f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompilationError("INPUT_PATH_INVALID", f"{label} must be valid JSON") from exc
    if not isinstance(value, Mapping):
        raise CompilationError("INPUT_PATH_INVALID", f"{label} must be a JSON object")
    return value


def verify_determinism_command(argv: Sequence[str]) -> int:
    """Compile a fixture twice in clean directories and compare all output bytes."""

    if len(argv) != 1:
        print("usage: harnessctl verify-determinism FIXTURE_DIRECTORY", file=sys.stderr)
        return 2
    fixture = Path(argv[0])
    try:
        if fixture.is_symlink() or not fixture.is_dir():
            raise CompilationError("INPUT_PATH_INVALID", "fixture path must be a regular directory")
        request = _read_json(fixture / "compile-request.json", "compile request")
        expected_digests = _read_json(fixture / "expected-digests.json", "expected digests")
        catalog_root = Path("catalog")
        lock_path = Path("contracts/catalog.lock.json")
        resources = load_catalog(catalog_root)
        actual_lock = _read_json(lock_path, "catalog lock")
        expected_lock = expected_catalog_lock(catalog_root)
        if actual_lock != expected_lock:
            raise CompilationError("CATALOG_INVALID", "catalog lock is stale")
        catalog_digest = actual_lock.get("catalogDigest")
        first = compile_profile(request, resources, str(catalog_digest))
        second = compile_profile(request, tuple(reversed(resources)), str(catalog_digest))
        with tempfile.TemporaryDirectory(prefix="compiler-a.") as first_directory_name:
            with tempfile.TemporaryDirectory(prefix="compiler-b.") as second_directory_name:
                first_directory = Path(first_directory_name)
                second_directory = Path(second_directory_name)
                write_compilation_outputs(first_directory, first)
                write_compilation_outputs(second_directory, second)
                for name in OUTPUT_NAMES:
                    if (first_directory / name).read_bytes() != (second_directory / name).read_bytes():
                        raise CompilationError(
                            "NON_DETERMINISTIC_OUTPUT",
                            "clean-directory compiler outputs differ",
                            {"output": name},
                        )
        actual_digests = {name: bytes_sha256(first[name]) for name in OUTPUT_NAMES}
        if dict(expected_digests) != actual_digests:
            raise CompilationError(
                "GOLDEN_DIGEST_MISMATCH",
                "compiler output digest differs from the fixture authority",
                {"actualDigests": actual_digests},
            )
        profile = json.loads(first["profile.json"])
        print(
            json.dumps(
                {
                    "accepted": True,
                    "catalogDigest": catalog_digest,
                    "outputs": actual_digests,
                    "selected": {
                        "harnesses": len(profile["profile"]["spec"]["selectedHarnessIds"]),
                        "modules": len(profile["profile"]["spec"]["selectedModuleIds"]),
                        "providers": len(profile["profile"]["spec"]["selectedProviderIds"]),
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except CompilationError as exc:
        print(json.dumps(dict(exc.as_json()), sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 1
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"determinism verification refused: {exc}", file=sys.stderr)
        return 2
