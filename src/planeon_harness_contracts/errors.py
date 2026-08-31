"""Closed exception hierarchy for contract and command registration errors."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping


class HarnessContractError(ValueError):
    """Base class for deterministic, user-correctable contract failures."""


class ContractRegistryError(HarnessContractError):
    """A contract registry operation was malformed or ambiguous."""


class CommandRegistryError(HarnessContractError):
    """A harnessctl command registration violated the closed registry contract."""


class CompilationError(HarnessContractError):
    """A deterministic compilation request failed at a closed admission boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = MappingProxyType(dict(sorted((details or {}).items())))
        super().__init__(f"{code}: {message}")

    def as_json(self) -> Mapping[str, Any]:
        """Return stable error evidence without a traceback or executable content."""

        return MappingProxyType(
            {
                "accepted": False,
                "code": self.code,
                "details": dict(self.details),
                "message": self.message,
            }
        )
