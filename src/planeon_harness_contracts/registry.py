"""Immutable schema registry shell for future packet-owned contract kinds."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from planeon_harness_contracts.errors import ContractRegistryError
from planeon_harness_contracts.validation import (
    ValidationResult,
    reject_unregistered_kind,
)

Validator = Callable[[str, Mapping[str, Any]], ValidationResult]


@dataclass(frozen=True, slots=True)
class RegisteredContract:
    """A future contract kind and its in-process, side-effect-free validator."""

    kind: str
    api_version: str
    validator: Validator

    def __post_init__(self) -> None:
        if not self.kind or not self.kind.replace("-", "").isalnum():
            raise ContractRegistryError(f"invalid contract kind: {self.kind!r}")
        if not self.api_version.startswith("harness.planeon.ai/"):
            raise ContractRegistryError(
                f"contract api_version must use harness.planeon.ai authority: {self.api_version!r}"
            )
        if not callable(self.validator):
            raise ContractRegistryError("contract validator must be callable")


class ContractRegistry:
    """Read-only registry with duplicate rejection and fail-closed lookup."""

    def __init__(self, contracts: Iterable[RegisteredContract] = ()) -> None:
        by_kind: dict[str, RegisteredContract] = {}
        for contract in contracts:
            if contract.kind in by_kind:
                raise ContractRegistryError(f"duplicate contract kind: {contract.kind}")
            by_kind[contract.kind] = contract
        self._contracts = MappingProxyType(dict(sorted(by_kind.items())))

    @classmethod
    def empty(cls) -> ContractRegistry:
        """Construct the deliberate CON-001 registry with zero public kinds."""

        return cls()

    @property
    def contracts(self) -> Mapping[str, RegisteredContract]:
        """Return an immutable, lexically ordered mapping."""

        return self._contracts

    @property
    def kinds(self) -> tuple[str, ...]:
        """Return registered kind names in deterministic order."""

        return tuple(self._contracts)

    def validate(self, kind: str, document: Mapping[str, Any]) -> ValidationResult:
        """Validate through the registered kind or reject unknown authority."""

        contract = self._contracts.get(kind)
        if contract is None:
            return reject_unregistered_kind(kind, document)
        return contract.validator(kind, document)

