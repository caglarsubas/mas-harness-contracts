"""Closed exception hierarchy for contract and command registration errors."""

from __future__ import annotations


class HarnessContractError(ValueError):
    """Base class for deterministic, user-correctable contract failures."""


class ContractRegistryError(HarnessContractError):
    """A contract registry operation was malformed or ambiguous."""


class CommandRegistryError(HarnessContractError):
    """A harnessctl command registration violated the closed registry contract."""

