"""Closed JSON descriptor loader for packet-owned harnessctl commands."""

from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Iterable, Mapping, Sequence

from planeon_harness_contracts.errors import CommandRegistryError

SCHEMA_VERSION = "harness.planeon.ai/harnessctl-command/v1alpha1"
COMMAND_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
PACKET_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
HANDLER_PATTERN = re.compile(
    r"^planeon_harness_contracts(?:\.[a-z][a-z0-9_]*)+:[a-z][a-z0-9_]*$"
)
COMMAND_OWNERS: Mapping[str, str] = MappingProxyType(
    {
        "catalog": "CON-002",
        "compatibility": "CON-006",
        "validate": "CON-002",
        "verify-determinism": "CON-004",
    }
)
OWNER_MODULE_PREFIXES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "CON-002": (
            "planeon_harness_contracts.registry:",
            "planeon_harness_contracts.validation:",
        ),
        "CON-004": (
            "planeon_harness_contracts.cli:",
            "planeon_harness_contracts.compiler:",
        ),
        "CON-006": ("planeon_harness_contracts.compatibility_",),
    }
)

CommandHandler = Callable[[Sequence[str]], int]


@dataclass(frozen=True, slots=True)
class CommandRegistration:
    """One validated command name, packet owner, and Python handler reference."""

    command: str
    packet_id: str
    handler: str

    def resolve(self) -> CommandHandler:
        """Import the validated handler and require a callable."""

        module_name, callable_name = self.handler.split(":", maxsplit=1)
        module = importlib.import_module(module_name)
        candidate = getattr(module, callable_name, None)
        if not callable(candidate):
            raise CommandRegistryError(f"command handler is not callable: {self.handler}")
        return candidate


def default_descriptor_directory() -> Path:
    """Return the installed packet-owned descriptor directory."""

    return Path(__file__).with_name("commands")


def _read_descriptor(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CommandRegistryError(f"invalid command descriptor: {path.name}") from exc
    if not isinstance(value, dict):
        raise CommandRegistryError(f"command descriptor must be an object: {path.name}")
    return value


def _validate_descriptor(path: Path, value: dict[str, object]) -> CommandRegistration:
    if set(value) != {"schemaVersion", "packetId", "command", "handler"}:
        raise CommandRegistryError(f"command descriptor fields are closed: {path.name}")
    if value["schemaVersion"] != SCHEMA_VERSION:
        raise CommandRegistryError(f"unknown command descriptor schema: {path.name}")
    packet_id = value["packetId"]
    command = value["command"]
    handler = value["handler"]
    if not isinstance(packet_id, str) or PACKET_PATTERN.fullmatch(packet_id) is None:
        raise CommandRegistryError(f"invalid command packet owner: {path.name}")
    if not isinstance(command, str) or COMMAND_PATTERN.fullmatch(command) is None:
        raise CommandRegistryError(f"invalid command name: {path.name}")
    if path.name != f"{command}.json":
        raise CommandRegistryError(f"command owner/descriptor filename mismatch: {path.name}")
    expected_owner = COMMAND_OWNERS.get(command)
    if expected_owner != packet_id:
        raise CommandRegistryError(f"command owner mismatch: {command}")
    if not isinstance(handler, str) or HANDLER_PATTERN.fullmatch(handler) is None:
        raise CommandRegistryError(f"command handler is not a closed Python reference: {command}")
    prefixes = OWNER_MODULE_PREFIXES.get(packet_id, ())
    if not any(handler.startswith(prefix) for prefix in prefixes):
        raise CommandRegistryError(f"command handler is outside packet authority: {command}")
    return CommandRegistration(command=command, packet_id=packet_id, handler=handler)


def load_command_registry(
    descriptor_directory: Path | None = None,
    *,
    authorized_packets: Iterable[str] | None = None,
) -> Mapping[str, CommandRegistration]:
    """Load exact JSON registrations and reject ambiguity or closure bypass."""

    directory = descriptor_directory or default_descriptor_directory()
    if not directory.is_dir() or directory.is_symlink():
        raise CommandRegistryError("command descriptor directory is absent or linked")
    return build_command_registry(
        sorted(directory.glob("*.json"), key=lambda item: item.name),
        authorized_packets=authorized_packets,
    )


def build_command_registry(
    descriptor_paths: Iterable[Path],
    *,
    authorized_packets: Iterable[str] | None = None,
) -> Mapping[str, CommandRegistration]:
    """Build a registry from explicit paths so duplicate transport is testable."""

    authority = set(authorized_packets) if authorized_packets is not None else None
    registrations: dict[str, CommandRegistration] = {}
    for path in descriptor_paths:
        if path.is_symlink() or not path.is_file():
            raise CommandRegistryError(f"command descriptor must be a regular file: {path.name}")
        registration = _validate_descriptor(path, _read_descriptor(path))
        if authority is not None and registration.packet_id not in authority:
            raise CommandRegistryError(
                f"command owner is outside predecessor closure: {registration.packet_id}"
            )
        if registration.command in registrations:
            raise CommandRegistryError(f"duplicate command registration: {registration.command}")
        registrations[registration.command] = registration
    return MappingProxyType(registrations)
