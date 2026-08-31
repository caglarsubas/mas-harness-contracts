"""Dependency-free validation for the closed v1alpha1 harness taxonomy."""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

API_VERSION = "harness.planeon.ai/v1alpha1"
CATALOG_KINDS = frozenset(
    {
        "HarnessClassDefinition",
        "HarnessModuleDefinition",
        "FrameworkProviderDefinition",
        "ModuleRelease",
    }
)
EXPECTED_HARNESSES: Mapping[str, str] = {
    "runtime.infrastructure": "runtime",
    "runtime.model-inference": "runtime",
    "runtime.ai-gateway": "runtime",
    "runtime.experience": "runtime",
    "knowledge.domain-semantic": "knowledge",
    "knowledge.data-integration": "knowledge",
    "knowledge.retrieval-context": "knowledge",
    "knowledge.memory-state": "knowledge",
    "execution.protocol-interoperability": "execution",
    "execution.orchestration": "execution",
    "execution.tool-skill-sandbox": "execution",
    "execution.ml-decision": "execution",
    "trust.security-safety": "trust",
    "trust.governance-agentops": "trust",
    "trust.observability-finops": "trust",
    "trust.evaluation-assurance": "trust",
}
EXPECTED_PROVIDERS = frozenset(
    {
        "provider.runtime.infrastructure.kubernetes-upstream",
        "provider.runtime.infrastructure.k3s",
        "provider.runtime.infrastructure.openshift",
        "provider.planeon.ollama",
        "provider.planeon.llamacpp",
        "provider.planeon.vllm",
        "provider.planeon.mlx",
        "provider.execution.protocol-mcp",
        "provider.execution.protocol-a2a",
        "provider.execution.protocol-openapi",
        "provider.execution.protocol-asyncapi",
        "provider.execution.sandbox-gvisor",
        "provider.execution.sandbox-kata",
        "provider.execution.decision-sklearn",
        "provider.execution.decision-onnx",
        "provider.execution.decision-ortools",
    }
)
EXPECTED_SELECTOR_GROUPS = frozenset(
    {
        "group.infrastructure-provider",
        "group.model-backend",
        "group.protocol-adapter",
        "group.native-sandbox-provider",
        "group.decision-provider",
    }
)


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
    """Fail closed for a kind outside the registered public authority."""

    return ValidationResult.rejected(
        ValidationIssue(
            code="UNKNOWN_CONTRACT_KIND",
            message=f"contract kind is not registered: {kind}",
        )
    )


def _issue(code: str, message: str, *path: str | int) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, path=path)


def _resource_id(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata")
    if not isinstance(metadata, Mapping):
        return ""
    resource_id = metadata.get("id")
    return resource_id if isinstance(resource_id, str) else ""


def _spec(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    spec = resource.get("spec")
    return spec if isinstance(spec, Mapping) else {}


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _string_sequence(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _validate_install_units(resource: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _resource_id(resource)
    install_units = _mapping_sequence(_spec(resource).get("installUnits"))
    issues: list[ValidationIssue] = []
    if not install_units:
        return [_issue("INSTALL_UNIT_REQUIRED", f"{resource_id} has no install unit")]
    seen: set[str] = set()
    for index, unit in enumerate(install_units):
        unit_id = unit.get("id")
        if not isinstance(unit_id, str) or not unit_id:
            issues.append(_issue("INVALID_INSTALL_UNIT", "install unit id is required", resource_id, index))
            continue
        if unit_id in seen:
            issues.append(_issue("DUPLICATE_INSTALL_UNIT", f"duplicate install unit: {unit_id}"))
        seen.add(unit_id)
        expected = {
            "independent": True,
            "digestRequiredAtRelease": True,
            "runtimeDownloadAllowed": False,
        }
        for field, required in expected.items():
            if unit.get(field) is not required:
                issues.append(
                    _issue(
                        "UNSAFE_INSTALL_UNIT",
                        f"{unit_id} must declare {field}={str(required).lower()}",
                    )
                )
        if not isinstance(unit.get("artifactName"), str) or not unit.get("artifactName"):
            issues.append(_issue("INVALID_INSTALL_UNIT", f"{unit_id} requires artifactName"))
    return issues


def _validate_harness(resource: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _resource_id(resource)
    spec = _spec(resource)
    issues: list[ValidationIssue] = []
    if spec.get("plane") not in {"runtime", "knowledge", "execution", "trust"}:
        issues.append(_issue("INVALID_PLANE", f"{resource_id} has an invalid plane"))
    modules = _string_sequence(spec.get("moduleIds"))
    if not modules:
        issues.append(_issue("MODULE_REQUIRED", f"{resource_id} has no independently selectable module"))
    capabilities = spec.get("capabilities")
    if not isinstance(capabilities, list):
        issues.append(_issue("INVALID_CAPABILITY_REGISTRY", f"{resource_id} capabilities must be a list"))
    for capability in _mapping_sequence(capabilities):
        capability_id = capability.get("id")
        role = capability.get("classification")
        if not isinstance(capability_id, str) or not capability_id:
            issues.append(_issue("INVALID_CAPABILITY", f"{resource_id} capability id is required"))
        if role not in {"PUBLIC_DEMAND", "ENVIRONMENT_FACT"}:
            issues.append(_issue("INVALID_CAPABILITY_ROLE", f"{capability_id} has an invalid role"))
        elif role == "ENVIRONMENT_FACT" and capability.get("signedAttestationRequired") is not True:
            issues.append(
                _issue(
                    "UNSIGNED_ENVIRONMENT_FACT",
                    f"{capability_id} must require a signed environment attestation",
                )
            )
        elif role == "PUBLIC_DEMAND" and capability.get("signedAttestationRequired") is not False:
            issues.append(_issue("INVALID_CAPABILITY_ROLE", f"{capability_id} cannot require attestation"))
    for dependency in _mapping_sequence(spec.get("dependencies")):
        if dependency.get("type") not in {
            "ALWAYS",
            "WHEN_CAPABILITY",
            "PRODUCTION_GATE",
            "SUBJECT_UNDER_EVALUATION",
        }:
            issues.append(_issue("INVALID_DEPENDENCY", f"{resource_id} has an invalid dependency type"))
    if not isinstance(spec.get("conflicts"), list):
        issues.append(_issue("INVALID_CONFLICT_REGISTRY", f"{resource_id} conflicts must be a list"))
    return issues


def _validate_module(resource: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _resource_id(resource)
    spec = _spec(resource)
    issues = _validate_install_units(resource)
    if not isinstance(spec.get("harnessId"), str):
        issues.append(_issue("INVALID_HARNESS_REFERENCE", f"{resource_id} requires harnessId"))
    if not _string_sequence(spec.get("providesCapabilities")):
        issues.append(_issue("CAPABILITY_REQUIRED", f"{resource_id} provides no capability"))
    if spec.get("externalEgressAllowed") is not False:
        issues.append(_issue("ZERO_BILL_VIOLATION", f"{resource_id} permits external egress"))
    if spec.get("runtimeDownloadsAllowed") is not False:
        issues.append(_issue("RUNTIME_DOWNLOAD_FORBIDDEN", f"{resource_id} permits runtime downloads"))
    license_contract = spec.get("license")
    if not isinstance(license_contract, Mapping) or license_contract.get("sourceAvailable") is not True:
        issues.append(_issue("LICENSE_EVIDENCE_REQUIRED", f"{resource_id} has no source-available license"))
    lifecycle = spec.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        issues.append(_issue("LIFECYCLE_REQUIRED", f"{resource_id} has no lifecycle contract"))
    else:
        for field in ("healthCheckRequired", "rollbackRequired", "uninstallSupported"):
            if lifecycle.get(field) is not True:
                issues.append(_issue("LIFECYCLE_REQUIRED", f"{resource_id} must declare {field}"))
    return issues


def _validate_provider(resource: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _resource_id(resource)
    spec = _spec(resource)
    issues = _validate_install_units(resource)
    for field in ("harnessId", "selectorGroup", "selectorCapability"):
        if not isinstance(spec.get(field), str) or not spec.get(field):
            issues.append(_issue("INVALID_PROVIDER", f"{resource_id} requires {field}"))
    if not _string_sequence(spec.get("activatedByCapabilities")):
        issues.append(_issue("INVALID_PROVIDER", f"{resource_id} requires activation capabilities"))
    required_values = {
        "providerCredentialsRequired": False,
        "externalTelemetry": False,
        "runtimeDownloadsAllowed": False,
        "releaseStatus": "PLANNED",
    }
    for field, required in required_values.items():
        if spec.get(field) != required:
            issues.append(_issue("ZERO_BILL_VIOLATION", f"{resource_id} must declare {field}={required}"))
    license_contract = spec.get("license")
    if not isinstance(license_contract, Mapping):
        issues.append(_issue("LICENSE_EVIDENCE_REQUIRED", f"{resource_id} has no license contract"))
    elif license_contract.get("releaseAdmission") != "BLOCKED_PENDING_UPSTREAM_LICENSE_EVIDENCE":
        issues.append(
            _issue(
                "PREMATURE_PROVIDER_RELEASE",
                f"{resource_id} must remain blocked until upstream license evidence is locked",
            )
        )
    return issues


def _validate_release(resource: Mapping[str, Any]) -> list[ValidationIssue]:
    resource_id = _resource_id(resource)
    spec = _spec(resource)
    state = spec.get("state")
    issues: list[ValidationIssue] = []
    if state not in {"PLANNED", "RELEASED"}:
        return [_issue("INVALID_RELEASE_STATE", f"{resource_id} has an invalid release state")]
    units = _mapping_sequence(spec.get("installUnits"))
    if not units:
        issues.append(_issue("INSTALL_UNIT_REQUIRED", f"{resource_id} has no release install unit"))
    digest_fields = ("digest", "sbomDigest", "licenseDigest", "signatureDigest")
    for unit in units:
        if state == "PLANNED":
            if unit.get("digestStatus") != "MISSING_PLANNED" or any(
                unit.get(field) is not None for field in digest_fields
            ):
                issues.append(_issue("PLANNED_DIGEST_MUST_BE_EMPTY", f"{resource_id} has a planned digest"))
        else:
            digests = tuple(unit.get(field) for field in digest_fields)
            if unit.get("digestStatus") != "LOCKED" or any(
                not isinstance(value, str)
                or not value.startswith("sha256:")
                or len(value) != 71
                for value in digests
            ):
                issues.append(_issue("RELEASE_DIGEST_REQUIRED", f"{resource_id} lacks locked evidence digests"))
    upgrade = spec.get("upgrade")
    rollback = spec.get("rollback")
    if not isinstance(upgrade, Mapping) or upgrade.get("preflightRequired") is not True:
        issues.append(_issue("UPGRADE_PREFLIGHT_REQUIRED", f"{resource_id} lacks upgrade preflight"))
    if (
        not isinstance(rollback, Mapping)
        or rollback.get("supported") is not True
        or rollback.get("previousDigestRequired") is not True
    ):
        issues.append(_issue("ROLLBACK_REQUIRED", f"{resource_id} lacks digest-bound rollback"))
    return issues


def validate_taxonomy_resource(kind: str, document: Mapping[str, Any]) -> ValidationResult:
    """Validate the closed envelope and safety-critical semantics for one resource."""

    issues: list[ValidationIssue] = []
    if kind not in CATALOG_KINDS or document.get("kind") != kind:
        issues.append(_issue("KIND_MISMATCH", f"resource does not match registered kind: {kind}"))
    if document.get("apiVersion") != API_VERSION:
        issues.append(_issue("API_VERSION_MISMATCH", f"{kind} must use {API_VERSION}"))
    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping) or set(metadata) != {"id", "version"}:
        issues.append(_issue("INVALID_METADATA", f"{kind} metadata fields are closed"))
    elif not all(isinstance(metadata.get(field), str) and metadata.get(field) for field in metadata):
        issues.append(_issue("INVALID_METADATA", f"{kind} metadata values must be non-empty strings"))
    if not isinstance(document.get("spec"), Mapping):
        issues.append(_issue("INVALID_SPEC", f"{kind} spec must be an object"))
    elif kind == "HarnessClassDefinition":
        issues.extend(_validate_harness(document))
    elif kind == "HarnessModuleDefinition":
        issues.extend(_validate_module(document))
    elif kind == "FrameworkProviderDefinition":
        issues.extend(_validate_provider(document))
    elif kind == "ModuleRelease":
        issues.extend(_validate_release(document))
    return ValidationResult.rejected(*issues) if issues else ValidationResult.success()


def _cycle_nodes(edges: Mapping[str, set[str]]) -> tuple[str, ...]:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def walk(node: str) -> tuple[str, ...]:
        if node in visiting:
            offset = stack.index(node)
            return tuple(stack[offset:] + [node])
        if node in visited:
            return ()
        visiting.add(node)
        stack.append(node)
        for target in sorted(edges.get(node, set())):
            cycle = walk(target)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return ()

    for candidate in sorted(edges):
        cycle = walk(candidate)
        if cycle:
            return cycle
    return ()


def capability_roles(
    resources: Iterable[Mapping[str, Any]],
) -> tuple[frozenset[str], frozenset[str], Mapping[str, tuple[Mapping[str, Any], ...]]]:
    """Return public demand, signed facts, and provider selector groups."""

    public: set[str] = set()
    environment: set[str] = set()
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for resource in resources:
        kind = resource.get("kind")
        spec = _spec(resource)
        if kind == "HarnessClassDefinition":
            for capability in _mapping_sequence(spec.get("capabilities")):
                capability_id = capability.get("id")
                if not isinstance(capability_id, str):
                    continue
                if capability.get("classification") == "PUBLIC_DEMAND":
                    public.add(capability_id)
                elif capability.get("classification") == "ENVIRONMENT_FACT":
                    environment.add(capability_id)
        elif kind == "FrameworkProviderDefinition" and isinstance(spec.get("selectorGroup"), str):
            groups[spec["selectorGroup"]].append(resource)
    return (
        frozenset(public),
        frozenset(environment),
        {group: tuple(entries) for group, entries in sorted(groups.items())},
    )


def validate_catalog(resources: Sequence[Mapping[str, Any]]) -> ValidationResult:
    """Validate the entire catalog as one closed, deterministic authority."""

    issues: list[ValidationIssue] = []
    by_kind: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_id: dict[str, Mapping[str, Any]] = {}
    for index, resource in enumerate(resources):
        kind = resource.get("kind")
        if not isinstance(kind, str):
            issues.append(_issue("INVALID_RESOURCE", "catalog resource has no kind", index))
            continue
        result = validate_taxonomy_resource(kind, resource)
        issues.extend(result.issues)
        by_kind[kind].append(resource)
        resource_id = _resource_id(resource)
        if not resource_id:
            continue
        if resource_id in by_id:
            issues.append(_issue("DUPLICATE_RESOURCE_ID", f"duplicate resource id: {resource_id}"))
        by_id[resource_id] = resource

    harnesses = by_kind["HarnessClassDefinition"]
    modules = by_kind["HarnessModuleDefinition"]
    providers = by_kind["FrameworkProviderDefinition"]
    harness_ids = {_resource_id(item) for item in harnesses}
    module_ids = {_resource_id(item) for item in modules}
    provider_ids = {_resource_id(item) for item in providers}
    if harness_ids != set(EXPECTED_HARNESSES):
        issues.append(
            _issue(
                "HARNESS_SET_MISMATCH",
                f"catalog must contain exactly the sixteen canonical harnesses; found {len(harness_ids)}",
            )
        )
    plane_counts = Counter(_spec(item).get("plane") for item in harnesses)
    if plane_counts != Counter({"runtime": 4, "knowledge": 4, "execution": 4, "trust": 4}):
        issues.append(_issue("PLANE_CARDINALITY_MISMATCH", "each plane must contain exactly four harnesses"))
    for harness in harnesses:
        harness_id = _resource_id(harness)
        if EXPECTED_HARNESSES.get(harness_id) != _spec(harness).get("plane"):
            issues.append(_issue("HARNESS_PLANE_MISMATCH", f"{harness_id} is assigned to the wrong plane"))
        for module_id in _string_sequence(_spec(harness).get("moduleIds")):
            if module_id not in module_ids:
                issues.append(_issue("MISSING_MODULE_REFERENCE", f"{harness_id} references absent {module_id}"))
    expected_modules = {f"module.{harness_id}.core" for harness_id in EXPECTED_HARNESSES}
    if module_ids != expected_modules:
        issues.append(_issue("MODULE_SET_MISMATCH", "catalog must contain one core module per harness"))
    if provider_ids != set(EXPECTED_PROVIDERS):
        issues.append(_issue("PROVIDER_SET_MISMATCH", "catalog must contain the sixteen canonical providers"))

    harness_edges: dict[str, set[str]] = defaultdict(set)
    harness_conflicts: dict[str, set[str]] = defaultdict(set)
    for harness in harnesses:
        harness_id = _resource_id(harness)
        for dependency in _mapping_sequence(_spec(harness).get("dependencies")):
            target = dependency.get("harnessId")
            if not isinstance(target, str) or target not in harness_ids:
                issues.append(_issue("DANGLING_DEPENDENCY", f"{harness_id} has an unknown dependency"))
            elif target == harness_id:
                issues.append(_issue("SELF_DEPENDENCY", f"{harness_id} depends on itself"))
            elif dependency.get("type") in {"ALWAYS", "WHEN_CAPABILITY"}:
                harness_edges[harness_id].add(target)
        for conflict in _mapping_sequence(_spec(harness).get("conflicts")):
            target = conflict.get("resourceId")
            if not isinstance(target, str) or target not in harness_ids:
                issues.append(_issue("DANGLING_CONFLICT", f"{harness_id} has an unknown conflict"))
            elif target == harness_id:
                issues.append(_issue("SELF_CONFLICT", f"{harness_id} conflicts with itself"))
            else:
                harness_conflicts[harness_id].add(target)
    cycle = _cycle_nodes(harness_edges)
    if cycle:
        issues.append(_issue("DEPENDENCY_CYCLE", f"harness dependency cycle: {' -> '.join(cycle)}"))
    for source, targets in harness_conflicts.items():
        for target in targets:
            if source not in harness_conflicts.get(target, set()):
                issues.append(_issue("ASYMMETRIC_CONFLICT", f"{source} conflict with {target} is not symmetric"))

    module_edges: dict[str, set[str]] = defaultdict(set)
    for module in modules:
        module_id = _resource_id(module)
        harness_id = _spec(module).get("harnessId")
        if harness_id not in harness_ids:
            issues.append(_issue("INVALID_HARNESS_REFERENCE", f"{module_id} references unknown harness"))
        elif module_id not in _string_sequence(_spec(by_id[harness_id]).get("moduleIds")):
            issues.append(_issue("UNOWNED_MODULE", f"{module_id} is not declared by {harness_id}"))
        for required in _string_sequence(_spec(module).get("requiresModules")):
            if required not in module_ids:
                issues.append(_issue("DANGLING_MODULE_DEPENDENCY", f"{module_id} requires absent {required}"))
            elif required == module_id:
                issues.append(_issue("SELF_DEPENDENCY", f"{module_id} requires itself"))
            else:
                module_edges[module_id].add(required)
    module_cycle = _cycle_nodes(module_edges)
    if module_cycle:
        issues.append(_issue("DEPENDENCY_CYCLE", f"module dependency cycle: {' -> '.join(module_cycle)}"))

    public, environment, groups = capability_roles(resources)
    selectors: set[str] = set()
    for group, entries in groups.items():
        if len(entries) < 2:
            issues.append(_issue("INVALID_SELECTOR_GROUP", f"{group} must offer at least two choices"))
        for provider in entries:
            spec = _spec(provider)
            selector = spec.get("selectorCapability")
            if not isinstance(selector, str) or selector in selectors:
                issues.append(_issue("DUPLICATE_SELECTOR", f"selector must be unique: {selector}"))
            elif selector in public or selector in environment:
                issues.append(_issue("CAPABILITY_ROLE_OVERLAP", f"selector role overlaps: {selector}"))
            else:
                selectors.add(selector)
            if spec.get("harnessId") not in harness_ids:
                issues.append(_issue("INVALID_HARNESS_REFERENCE", "provider references unknown harness"))
            for activation in _string_sequence(spec.get("activatedByCapabilities")):
                if activation not in public:
                    issues.append(_issue("INVALID_PROVIDER_ACTIVATION", f"{activation} is not public demand"))
    if set(groups) != set(EXPECTED_SELECTOR_GROUPS):
        issues.append(_issue("SELECTOR_GROUP_SET_MISMATCH", "provider selector groups are not canonical"))
    if public & environment:
        issues.append(_issue("CAPABILITY_ROLE_OVERLAP", "public demand and environment fact roles overlap"))

    for release in by_kind["ModuleRelease"]:
        if _spec(release).get("moduleId") not in module_ids:
            issues.append(_issue("DANGLING_RELEASE", f"{_resource_id(release)} references an absent module"))
    return ValidationResult.rejected(*issues) if issues else ValidationResult.success()


def admit_requested_capabilities(
    resources: Sequence[Mapping[str, Any]], requested: Iterable[str]
) -> ValidationResult:
    """Admit only public demand plus one explicit selector for each active group."""

    demand = tuple(requested)
    if len(set(demand)) != len(demand):
        return ValidationResult.rejected(_issue("INVALID_COMBINATION", "capabilities must be unique"))
    public, environment, groups = capability_roles(resources)
    selector_to_provider: dict[str, Mapping[str, Any]] = {}
    for entries in groups.values():
        for provider in entries:
            selector = _spec(provider).get("selectorCapability")
            if isinstance(selector, str):
                selector_to_provider[selector] = provider
    unknown = set(demand) - public - environment - set(selector_to_provider)
    if unknown:
        return ValidationResult.rejected(
            _issue(
                "INVALID_CAPABILITY_ROLE",
                f"capability is INTERNAL_ONLY unless registered: {sorted(unknown)[0]}",
            )
        )
    facts = set(demand) & environment
    if facts:
        return ValidationResult.rejected(
            _issue("INVALID_CAPABILITY_ROLE", f"environment facts cannot be public demand: {sorted(facts)[0]}")
        )
    selected = set(demand) & set(selector_to_provider)
    for selector in sorted(selected):
        provider = selector_to_provider[selector]
        activations = set(_string_sequence(_spec(provider).get("activatedByCapabilities")))
        if not activations.intersection(demand):
            return ValidationResult.rejected(
                _issue("INVALID_COMBINATION", f"selector is inactive for the declared demand: {selector}")
            )
    for group, entries in groups.items():
        activations = {
            activation
            for provider in entries
            for activation in _string_sequence(_spec(provider).get("activatedByCapabilities"))
        }
        group_selectors = {
            selector
            for provider in entries
            if isinstance((selector := _spec(provider).get("selectorCapability")), str)
        }
        choices = selected & group_selectors
        if activations.intersection(demand) and not choices:
            return ValidationResult.rejected(
                _issue("NEEDS_INPUT", f"active provider group requires one selector: {group}")
            )
        if len(choices) > 1:
            return ValidationResult.rejected(
                _issue("AMBIGUOUS_PROVIDER", f"provider group has multiple selectors: {group}")
            )
    return ValidationResult.success()


def validate_harness_selection(
    resources: Sequence[Mapping[str, Any]], selected_harnesses: Iterable[str]
) -> ValidationResult:
    """Reject a selected harness set containing a declared symmetric conflict."""

    selected = set(selected_harnesses)
    for resource in resources:
        if resource.get("kind") != "HarnessClassDefinition":
            continue
        source = _resource_id(resource)
        if source not in selected:
            continue
        for conflict in _mapping_sequence(_spec(resource).get("conflicts")):
            target = conflict.get("resourceId")
            if isinstance(target, str) and target in selected:
                return ValidationResult.rejected(
                    _issue("HARNESS_CONFLICT", f"selected harnesses conflict: {source}, {target}")
                )
    return ValidationResult.success()


def semantic_negative_vectors(
    resources: Sequence[Mapping[str, Any]],
) -> Mapping[str, str]:
    """Execute stable negative vectors required by the packet evidence contract."""

    vectors: dict[str, str] = {}

    def record(name: str, result: ValidationResult) -> None:
        vectors[name] = result.issues[0].code if result.issues else "UNEXPECTED_ACCEPT"

    record(
        "environment-fact-as-demand",
        admit_requested_capabilities(resources, ("connectivity.airgap",)),
    )
    record(
        "inactive-selector",
        admit_requested_capabilities(resources, ("provider.planeon.ollama",)),
    )
    record("active-group-without-selector", admit_requested_capabilities(resources, ("model.local-cpu",)))
    record(
        "ambiguous-provider",
        admit_requested_capabilities(
            resources,
            ("model.local-cpu", "provider.planeon.ollama", "provider.planeon.llamacpp"),
        ),
    )
    cyclic = copy.deepcopy(list(resources))
    for resource in cyclic:
        if _resource_id(resource) == "runtime.infrastructure":
            dependencies = resource["spec"]["dependencies"]
            dependencies.append({"harnessId": "runtime.experience", "type": "ALWAYS"})
            break
    record("dependency-cycle", validate_catalog(cyclic))
    conflicting = copy.deepcopy(list(resources))
    reason = "The two harnesses are mutually exclusive in this fixture."
    for resource in conflicting:
        if _resource_id(resource) == "runtime.infrastructure":
            resource["spec"]["conflicts"].append(
                {"resourceId": "runtime.experience", "reason": reason}
            )
        elif _resource_id(resource) == "runtime.experience":
            resource["spec"]["conflicts"].append(
                {"resourceId": "runtime.infrastructure", "reason": reason}
            )
    record(
        "harness-conflict",
        validate_harness_selection(
            conflicting,
            ("runtime.infrastructure", "runtime.experience"),
        ),
    )
    return dict(sorted(vectors.items()))


def validate_command(argv: Sequence[str]) -> int:
    """Validate a closed catalog or questionnaire path without network access."""

    if len(argv) != 3 or argv[0] != "--kind" or argv[1] not in {"catalog", "questionnaire"}:
        print("usage: harnessctl validate --kind {catalog,questionnaire} PATH", file=sys.stderr)
        return 2
    if argv[1] == "questionnaire":
        from planeon_harness_contracts.questionnaire import validate_questionnaire_path

        return validate_questionnaire_path(Path(argv[2]))
    from planeon_harness_contracts.registry import load_catalog

    try:
        resources = load_catalog(Path(argv[2]))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"catalog validation refused: {exc}", file=sys.stderr)
        return 2
    result = validate_catalog(resources)
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
    vectors = semantic_negative_vectors(resources)
    expected = {
        "active-group-without-selector": "NEEDS_INPUT",
        "ambiguous-provider": "AMBIGUOUS_PROVIDER",
        "dependency-cycle": "DEPENDENCY_CYCLE",
        "environment-fact-as-demand": "INVALID_CAPABILITY_ROLE",
        "harness-conflict": "HARNESS_CONFLICT",
        "inactive-selector": "INVALID_COMBINATION",
    }
    if vectors != expected:
        print(f"semantic negative vectors failed: {vectors}", file=sys.stderr)
        return 1
    public, environment, groups = capability_roles(resources)
    counts = Counter(resource["kind"] for resource in resources)
    print(
        json.dumps(
            {
                "accepted": True,
                "capabilityRoles": {
                    "environmentFact": len(environment),
                    "internalDefault": True,
                    "publicDemand": len(public),
                    "selector": sum(len(entries) for entries in groups.values()),
                },
                "negativeVectors": vectors,
                "resources": dict(sorted(counts.items())),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0
