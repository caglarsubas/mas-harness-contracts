#!/usr/bin/env python3
"""Validate packet-owned Make descriptors and execute only direct argv arrays."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

SCHEMA_VERSION = "harness.planeon.ai/make-target-descriptor/v1alpha1"
PACKET_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
TARGET_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
VARIABLE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
ALLOWED_VARIABLES = {"BACKEND", "CAMPAIGN", "MODULE", "PACK", "PROVIDERS"}
FORBIDDEN_EXECUTABLES = {"bash", "dash", "env", "sh", "zsh"}


class TargetDescriptorError(ValueError):
    """The closed Make target authority is malformed or has no exact match."""


@dataclass(frozen=True, slots=True)
class TargetRule:
    """One packet-owned target variant and its direct command templates."""

    packet_id: str
    name: str
    accepted_variables: Mapping[str, frozenset[str]]
    commands: tuple[tuple[str | tuple[str, str], ...], ...]

    def matches(self, supplied: Mapping[str, str]) -> bool:
        """Return true only for an exact variable set and admitted values."""

        return set(supplied) == set(self.accepted_variables) and all(
            supplied[name] in values for name, values in self.accepted_variables.items()
        )

    def render(self, supplied: Mapping[str, str]) -> tuple[tuple[str, ...], ...]:
        """Substitute closed variable references without invoking a shell."""

        rendered: list[tuple[str, ...]] = []
        for template in self.commands:
            command: list[str] = []
            for part in template:
                if isinstance(part, tuple):
                    command.append(supplied[part[1]])
                else:
                    command.append(part)
            rendered.append(tuple(command))
        return tuple(rendered)


def _object(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TargetDescriptorError(message)
    return value


def _accepted_variables(value: object, context: str) -> Mapping[str, frozenset[str]]:
    raw = _object(value, f"acceptedVariables must be an object: {context}")
    accepted: dict[str, frozenset[str]] = {}
    for name, rule_value in raw.items():
        if name not in ALLOWED_VARIABLES or VARIABLE_PATTERN.fullmatch(name) is None:
            raise TargetDescriptorError(f"undeclared Make variable: {name}")
        rule = _object(rule_value, f"variable rule must be an object: {context}/{name}")
        if set(rule) == {"const"} and isinstance(rule["const"], str) and rule["const"]:
            values = frozenset({rule["const"]})
        elif set(rule) == {"enum"} and isinstance(rule["enum"], list):
            sequence = rule["enum"]
            if not sequence or not all(isinstance(item, str) and item for item in sequence):
                raise TargetDescriptorError(f"variable enum is invalid: {context}/{name}")
            values = frozenset(sequence)
            if len(values) != len(sequence):
                raise TargetDescriptorError(f"variable enum contains duplicates: {context}/{name}")
        else:
            raise TargetDescriptorError(f"variable rule is not closed: {context}/{name}")
        accepted[name] = values
    return accepted


def _commands(value: object, accepted: Mapping[str, frozenset[str]], context: str) -> tuple[tuple[str | tuple[str, str], ...], ...]:
    if not isinstance(value, list) or not value:
        raise TargetDescriptorError(f"argvTemplate must contain commands: {context}")
    commands: list[tuple[str | tuple[str, str], ...]] = []
    for command_index, raw_command in enumerate(value):
        if not isinstance(raw_command, list) or not raw_command:
            raise TargetDescriptorError(f"argv command is empty: {context}/{command_index}")
        command: list[str | tuple[str, str]] = []
        for argument in raw_command:
            if isinstance(argument, str) and argument and "\x00" not in argument and "\n" not in argument:
                command.append(argument)
                continue
            if isinstance(argument, dict) and set(argument) == {"variable"}:
                name = argument["variable"]
                if not isinstance(name, str) or name not in accepted:
                    raise TargetDescriptorError(f"argv references undeclared variable: {context}")
                command.append(("variable", name))
                continue
            raise TargetDescriptorError(f"argv argument is not a literal or closed variable: {context}")
        executable = command[0]
        if not isinstance(executable, str) or Path(executable).name in FORBIDDEN_EXECUTABLES:
            raise TargetDescriptorError(f"shell transport is forbidden: {context}")
        commands.append(tuple(command))
    return tuple(commands)


def load_rules(directory: Path) -> tuple[TargetRule, ...]:
    """Load all regular descriptor files and validate ownership and ambiguity."""

    if not directory.is_dir() or directory.is_symlink():
        raise TargetDescriptorError("Make target descriptor directory is absent or linked")
    rules: list[TargetRule] = []
    packet_ids: set[str] = set()
    signatures: set[tuple[str, str, tuple[tuple[str, tuple[str, ...]], ...]]] = set()
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
        if path.is_symlink() or not path.is_file():
            raise TargetDescriptorError(f"target descriptor must be a regular file: {path.name}")
        try:
            descriptor = _object(json.loads(path.read_text(encoding="utf-8")), f"descriptor must be an object: {path.name}")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TargetDescriptorError(f"invalid target descriptor: {path.name}") from exc
        if set(descriptor) != {"schemaVersion", "packetId", "targets"}:
            raise TargetDescriptorError(f"target descriptor fields are closed: {path.name}")
        if descriptor["schemaVersion"] != SCHEMA_VERSION:
            raise TargetDescriptorError(f"unknown target descriptor schema: {path.name}")
        packet_id = descriptor["packetId"]
        if not isinstance(packet_id, str) or PACKET_PATTERN.fullmatch(packet_id) is None:
            raise TargetDescriptorError(f"invalid packet owner: {path.name}")
        if path.name != f"{packet_id.lower()}.json":
            raise TargetDescriptorError(f"owner or filename mismatch: {path.name}")
        if packet_id in packet_ids:
            raise TargetDescriptorError(f"duplicate packet descriptor: {packet_id}")
        packet_ids.add(packet_id)
        raw_targets = descriptor["targets"]
        if not isinstance(raw_targets, list) or not raw_targets:
            raise TargetDescriptorError(f"descriptor has no targets: {path.name}")
        for index, raw_target in enumerate(raw_targets):
            target = _object(raw_target, f"target must be an object: {path.name}/{index}")
            if set(target) != {"name", "acceptedVariables", "argvTemplate"}:
                raise TargetDescriptorError(f"target fields are closed: {path.name}/{index}")
            name = target["name"]
            if not isinstance(name, str) or TARGET_PATTERN.fullmatch(name) is None:
                raise TargetDescriptorError(f"invalid target name: {path.name}/{index}")
            accepted = _accepted_variables(target["acceptedVariables"], f"{path.name}/{name}")
            signature = (
                packet_id,
                name,
                tuple(sorted((key, tuple(sorted(values))) for key, values in accepted.items())),
            )
            if signature in signatures:
                raise TargetDescriptorError(f"duplicate target rule: {packet_id}/{name}")
            signatures.add(signature)
            rules.append(
                TargetRule(
                    packet_id=packet_id,
                    name=name,
                    accepted_variables=accepted,
                    commands=_commands(target["argvTemplate"], accepted, f"{path.name}/{name}"),
                )
            )
    if not rules:
        raise TargetDescriptorError("no Make target descriptors were found")
    return tuple(sorted(rules, key=lambda rule: (rule.packet_id, rule.name)))


def parse_supplied_variables(arguments: Sequence[str]) -> dict[str, str]:
    """Parse explicit NAME=value arguments and reject duplicates or unknowns."""

    supplied: dict[str, str] = {}
    for argument in arguments:
        name, separator, value = argument.partition("=")
        if not separator or not value or name not in ALLOWED_VARIABLES:
            raise TargetDescriptorError(f"undeclared or malformed Make variable: {argument}")
        if name in supplied:
            raise TargetDescriptorError(f"duplicate Make variable: {name}")
        supplied[name] = value
    return supplied


def _environment_variables() -> dict[str, str]:
    return {name: os.environ[name] for name in ALLOWED_VARIABLES if os.environ.get(name)}


def dispatch(target: str, supplied: Mapping[str, str], directory: Path) -> int:
    """Select exactly one rule per packet and execute handlers lexically."""

    if TARGET_PATTERN.fullmatch(target) is None:
        raise TargetDescriptorError(f"invalid Make target: {target}")
    candidates = [rule for rule in load_rules(directory) if rule.name == target]
    by_packet: dict[str, list[TargetRule]] = {}
    for rule in candidates:
        by_packet.setdefault(rule.packet_id, []).append(rule)
    applicable: list[TargetRule] = []
    for packet_id in sorted(by_packet):
        matches = [rule for rule in by_packet[packet_id] if rule.matches(supplied)]
        if len(matches) > 1:
            raise TargetDescriptorError(f"ambiguous applicable handlers: {packet_id}/{target}")
        if len(matches) == 1:
            applicable.append(matches[0])
    if not applicable:
        raise TargetDescriptorError(f"zero applicable handlers: {target}")
    for rule in applicable:
        for command in rule.render(supplied):
            print(f"make-handler packet={rule.packet_id} argv={json.dumps(command, separators=(',', ':'))}", flush=True)
            completed = subprocess.run(command, shell=False, check=False)
            if completed.returncode != 0:
                return completed.returncode
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point used by the immutable bootstrap Makefile."""

    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print("Make target is required", file=sys.stderr)
        return 2
    try:
        explicit = parse_supplied_variables(arguments[1:])
        inherited = _environment_variables()
        overlap = set(explicit) & set(inherited)
        if overlap:
            raise TargetDescriptorError(f"duplicate Make variable: {sorted(overlap)[0]}")
        return dispatch(arguments[0], {**inherited, **explicit}, Path(__file__).with_name("targets"))
    except TargetDescriptorError as exc:
        print(f"Make dispatch refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

