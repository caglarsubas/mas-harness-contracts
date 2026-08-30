from __future__ import annotations

import unittest
from types import MappingProxyType

from planeon_harness_contracts import (
    ContractRegistry,
    ContractRegistryError,
    RegisteredContract,
    ValidationResult,
)


def accept(_kind: str, _document: MappingProxyType[str, object]) -> ValidationResult:
    return ValidationResult.success()


class ContractRegistryTests(unittest.TestCase):
    def test_bootstrap_registry_is_empty_and_immutable(self) -> None:
        registry = ContractRegistry.empty()
        self.assertEqual(registry.kinds, ())
        self.assertEqual(dict(registry.contracts), {})
        result = registry.validate("ExampleKind", {})
        self.assertFalse(result.accepted)
        self.assertEqual(result.issues[0].code, "UNKNOWN_CONTRACT_KIND")
        with self.assertRaises(TypeError):
            registry.contracts["ExampleKind"] = object()  # type: ignore[index]

    def test_registered_validator_can_return_success(self) -> None:
        contract = RegisteredContract(
            kind="ExampleKind",
            api_version="harness.planeon.ai/v1alpha1",
            validator=accept,
        )
        registry = ContractRegistry((contract,))
        self.assertTrue(registry.validate("ExampleKind", {}).accepted)

    def test_duplicate_kind_fails_closed(self) -> None:
        contract = RegisteredContract(
            kind="ExampleKind",
            api_version="harness.planeon.ai/v1alpha1",
            validator=accept,
        )
        with self.assertRaisesRegex(ContractRegistryError, "duplicate"):
            ContractRegistry((contract, contract))

    def test_rejected_result_requires_an_issue(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires an issue"):
            ValidationResult.rejected()


if __name__ == "__main__":
    unittest.main()

