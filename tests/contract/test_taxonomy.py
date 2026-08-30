from __future__ import annotations

import copy
import json
import unittest
from collections import Counter
from pathlib import Path

from planeon_harness_contracts.command_registry import load_command_registry
from planeon_harness_contracts.registry import (
    ContractRegistry,
    expected_catalog_lock,
    load_catalog,
)
from planeon_harness_contracts.validation import (
    EXPECTED_HARNESSES,
    EXPECTED_PROVIDERS,
    admit_requested_capabilities,
    capability_roles,
    semantic_negative_vectors,
    validate_catalog,
    validate_harness_selection,
    validate_taxonomy_resource,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "catalog"
FIXTURES = ROOT / "tests" / "fixtures" / "taxonomy"


def fixture(relative: str) -> dict[str, object]:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


class TaxonomyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resources = load_catalog(CATALOG)

    def test_catalog_has_exactly_sixteen_harnesses_and_four_per_plane(self) -> None:
        result = validate_catalog(self.resources)
        self.assertTrue(result.accepted, result.issues)
        harnesses = [item for item in self.resources if item["kind"] == "HarnessClassDefinition"]
        self.assertEqual({item["metadata"]["id"] for item in harnesses}, set(EXPECTED_HARNESSES))
        self.assertEqual(
            Counter(item["spec"]["plane"] for item in harnesses),
            Counter({"runtime": 4, "knowledge": 4, "execution": 4, "trust": 4}),
        )

    def test_module_and_provider_sets_are_closed(self) -> None:
        modules = [item for item in self.resources if item["kind"] == "HarnessModuleDefinition"]
        providers = [item for item in self.resources if item["kind"] == "FrameworkProviderDefinition"]
        self.assertEqual(len(modules), 16)
        self.assertEqual({item["metadata"]["id"] for item in providers}, set(EXPECTED_PROVIDERS))
        for resource in (*modules, *providers):
            for install_unit in resource["spec"]["installUnits"]:
                self.assertTrue(install_unit["independent"])
                self.assertTrue(install_unit["digestRequiredAtRelease"])
                self.assertFalse(install_unit["runtimeDownloadAllowed"])

    def test_capability_roles_are_disjoint_and_facts_require_signatures(self) -> None:
        public, environment, groups = capability_roles(self.resources)
        selectors = {
            entry["spec"]["selectorCapability"]
            for entries in groups.values()
            for entry in entries
        }
        self.assertFalse(public & environment)
        self.assertFalse(public & selectors)
        self.assertFalse(environment & selectors)
        for resource in self.resources:
            if resource["kind"] != "HarnessClassDefinition":
                continue
            for capability in resource["spec"]["capabilities"]:
                if capability["classification"] == "ENVIRONMENT_FACT":
                    self.assertTrue(capability["signedAttestationRequired"])

    def test_capability_admission_negative_vectors_are_stable(self) -> None:
        self.assertEqual(
            semantic_negative_vectors(self.resources),
            {
                "active-group-without-selector": "NEEDS_INPUT",
                "ambiguous-provider": "AMBIGUOUS_PROVIDER",
                "dependency-cycle": "DEPENDENCY_CYCLE",
                "environment-fact-as-demand": "INVALID_CAPABILITY_ROLE",
                "harness-conflict": "HARNESS_CONFLICT",
                "inactive-selector": "INVALID_COMBINATION",
            },
        )
        accepted = admit_requested_capabilities(
            self.resources,
            ("model.local-cpu", "provider.planeon.llamacpp"),
        )
        self.assertTrue(accepted.accepted, accepted.issues)

    def test_dangling_dependency_and_asymmetric_conflict_fail_closed(self) -> None:
        dangling = copy.deepcopy(self.resources)
        dangling[0]["spec"]["dependencies"].append(
            {"harnessId": "runtime.absent", "type": "ALWAYS"}
        )
        result = validate_catalog(dangling)
        self.assertIn("DANGLING_DEPENDENCY", {issue.code for issue in result.issues})

        conflict = copy.deepcopy(self.resources)
        conflict[0]["spec"]["conflicts"].append(
            {
                "resourceId": "runtime.experience",
                "reason": "The fixture intentionally declares one side only.",
            }
        )
        result = validate_catalog(conflict)
        self.assertIn("ASYMMETRIC_CONFLICT", {issue.code for issue in result.issues})
        selected = validate_harness_selection(
            conflict,
            ("runtime.infrastructure", "runtime.experience"),
        )
        self.assertEqual(selected.issues[0].code, "HARNESS_CONFLICT")

    def test_planned_and_released_digest_contracts(self) -> None:
        for name in (
            "valid/planned-module-release.json",
            "valid/released-module-release.json",
        ):
            resource = fixture(name)
            result = validate_taxonomy_resource("ModuleRelease", resource)
            self.assertTrue(result.accepted, result.issues)
        invalid = fixture("invalid/released-module-release-missing-digests.json")
        result = validate_taxonomy_resource("ModuleRelease", invalid)
        self.assertIn("RELEASE_DIGEST_REQUIRED", {issue.code for issue in result.issues})

    def test_registry_and_commands_have_closed_con002_authority(self) -> None:
        self.assertEqual(
            ContractRegistry.taxonomy().kinds,
            (
                "FrameworkProviderDefinition",
                "HarnessClassDefinition",
                "HarnessModuleDefinition",
                "ModuleRelease",
            ),
        )
        commands = load_command_registry(authorized_packets={"CON-002"})
        self.assertEqual(tuple(commands), ("catalog", "validate"))

    def test_catalog_lock_is_current_and_repeatable(self) -> None:
        first = expected_catalog_lock(CATALOG)
        second = expected_catalog_lock(CATALOG)
        actual = json.loads((ROOT / "contracts" / "catalog.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(first, second)
        self.assertEqual(actual, first)


if __name__ == "__main__":
    unittest.main()
