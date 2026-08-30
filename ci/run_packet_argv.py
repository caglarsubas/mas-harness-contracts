#!/usr/bin/env python3
"""Execute hash-pinned task-packet argv without a shell or YAML construction."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

PACKET_ENVIRONMENT = "HARNESS_TASK_PACKET"
OFFLINE_ENVIRONMENT = {"UV_OFFLINE": "1", "UV_FROZEN": "1", "UV_NO_SYNC": "1"}
EXPECTED_EXECUTION = {
    "wrapperArgv": ["./ci/verify-offline.sh"],
    "packetPathEnvironment": PACKET_ENVIRONMENT,
    "packetPathMode": "HASH_PINNED_READ_ONCE_NO_CHILD_PATH",
    "commandTransport": "ARGV_ARRAY_V1",
    "isolation": "OS_ENFORCED_DENY_ALL_OUTBOUND",
    "sessionScope": "SINGLE_PROCESS_TREE",
    "prefetchOutsideSession": False,
    "offlineEnvironment": OFFLINE_ENVIRONMENT,
}
FORBIDDEN_OFFLINE_TOKENS = {
    "add",
    "curl",
    "download",
    "fetch",
    "install",
    "npx",
    "prefetch",
    "pull",
    "sync",
    "wget",
}
FORBIDDEN_EXECUTABLES = {"bash", "dash", "env", "sh", "zsh"}
CHILD_ENVIRONMENT_ALLOWLIST = {
    "CI",
    "GITHUB_ACTIONS",
    "GITHUB_WORKSPACE",
    "HARNESS_OFFLINE_BACKEND",
    "HARNESS_OFFLINE_ENFORCED",
    "HARNESS_OFFLINE_SESSION_ID",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "SOURCE_DATE_EPOCH",
    "TMPDIR",
    "USER",
    "UV_CACHE_DIR",
    "UV_FROZEN",
    "UV_NO_SYNC",
    "UV_OFFLINE",
    "UV_PROJECT_ENVIRONMENT",
    "UV_PYTHON_DOWNLOADS",
    "VIRTUAL_ENV",
}


class PacketTransportError(ValueError):
    """The hash-pinned packet transport is malformed or unsafe."""


def read_packet_text(path: Path) -> tuple[str, str]:
    """Read a regular, non-followed packet once and return its SHA-256."""

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PacketTransportError("HARNESS_TASK_PACKET must name a regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as stream:
            text = stream.read()
    finally:
        os.close(descriptor)
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_packet_digest(path: Path, expected_digest: str) -> None:
    """Fail if a child replaced or changed the packet authority."""

    _text, actual_digest = read_packet_text(path)
    if actual_digest != expected_digest:
        raise PacketTransportError("packet authority changed during execution")


def load_json_field(packet_text: str, field: str) -> Any:
    """Read one required inline JSON field without constructing YAML."""

    prefix = f"{field}:"
    matches = [line[len(prefix) :].strip() for line in packet_text.splitlines() if line.startswith(prefix)]
    if len(matches) != 1 or not matches[0]:
        raise PacketTransportError(f"packet must contain one inline JSON {field} field")
    try:
        return json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise PacketTransportError(f"packet {field} is not inline JSON") from exc


def load_command_field(packet_text: str, field: str) -> list[list[str]]:
    """Validate one packet field as direct argv arrays."""

    value = load_json_field(packet_text, field)
    if not isinstance(value, list):
        raise PacketTransportError(f"packet {field} must be an array")
    commands: list[list[str]] = []
    for index, command in enumerate(value):
        if not isinstance(command, list) or not command:
            raise PacketTransportError(f"packet {field}[{index}] must be a non-empty argv array")
        if not all(isinstance(argument, str) and argument and "\x00" not in argument for argument in command):
            raise PacketTransportError(f"packet {field}[{index}] has an invalid argv value")
        commands.append(command)
    return commands


def validate_direct_argv(command: list[str]) -> None:
    """Reject shell or environment executable transport."""

    if Path(command[0]).name in FORBIDDEN_EXECUTABLES:
        raise PacketTransportError(f"shell/environment executable is forbidden: {command[0]}")


def validate_offline_argv(command: list[str]) -> None:
    """Apply the closed offline command admission rules."""

    validate_direct_argv(command)
    overlap = sorted({argument.casefold() for argument in command} & FORBIDDEN_OFFLINE_TOKENS)
    if overlap:
        raise PacketTransportError(f"network/prefetch token is forbidden offline: {overlap[0]}")
    if command[:2] == ["make", "verify-offline"]:
        raise PacketTransportError("recursive make verify-offline is forbidden")
    if command[0] == "uv":
        missing = [flag for flag in ("--offline", "--frozen", "--no-sync") if flag not in command]
        if missing:
            raise PacketTransportError(f"offline uv argv is missing {', '.join(missing)}")


def validate_execution_contract(packet_text: str) -> None:
    """Require the exact single-process-tree transport contract."""

    if load_json_field(packet_text, "offlineExecution") != EXPECTED_EXECUTION:
        raise PacketTransportError("packet offlineExecution does not match ARGV_ARRAY_V1 contract")


def scrub_environment(environment: dict[str, str]) -> dict[str, str]:
    """Keep only non-credential values required by the offline toolchain."""

    return {name: value for name, value in environment.items() if name in CHILD_ENVIRONMENT_ALLOWLIST}


def run_commands(
    commands: list[list[str]],
    *,
    environment: dict[str, str],
    packet_path: Path,
    packet_digest: str,
    phase: str,
) -> int:
    """Run ordered argv and recheck authority after every child."""

    for command in commands:
        print(f"{phase} argv:", json.dumps(command, separators=(",", ":")), flush=True)
        completed = subprocess.run(command, env=environment, shell=False, check=False)
        verify_packet_digest(packet_path, packet_digest)
        if completed.returncode != 0:
            return completed.returncode
    return 0


def main() -> int:
    """Execute packet prefetch then acceptance in the established sandbox."""

    argparse.ArgumentParser().parse_args()
    raw_path = os.environ.get(PACKET_ENVIRONMENT)
    if not raw_path:
        raise PacketTransportError(f"{PACKET_ENVIRONMENT} is required")
    packet_path = Path(raw_path)
    packet_text, packet_digest = read_packet_text(packet_path)
    validate_execution_contract(packet_text)
    prefetch_commands = load_command_field(packet_text, "prefetchCommands")
    offline_commands = load_command_field(packet_text, "offlineAcceptanceCommands")
    for command in prefetch_commands + offline_commands:
        validate_direct_argv(command)
    for command in prefetch_commands:
        if command != ["make", "prefetch"]:
            raise PacketTransportError(f"prefetch argv is not the local-cache-only entry point: {command}")
    for command in offline_commands:
        validate_offline_argv(command)

    environment = scrub_environment(os.environ.copy())
    if environment.get("HARNESS_OFFLINE_ENFORCED") != "1":
        raise PacketTransportError("packet execution requires OS egress isolation")
    for name, value in OFFLINE_ENVIRONMENT.items():
        if environment.get(name) != value:
            raise PacketTransportError(f"offline environment requires {name}={value}")
    canary = Path(__file__).with_name("network_canary.py")
    result = subprocess.run([sys.executable, str(canary)], env=environment, shell=False, check=False)
    if result.returncode != 0:
        return result.returncode
    verify_packet_digest(packet_path, packet_digest)
    print(
        f"packet={packet_digest} phases=prefetch,offline "
        f"session={environment.get('HARNESS_OFFLINE_SESSION_ID', 'missing')}",
        flush=True,
    )
    prefetch_result = run_commands(
        prefetch_commands,
        environment=environment,
        packet_path=packet_path,
        packet_digest=packet_digest,
        phase="prefetch-local-cache-only",
    )
    if prefetch_result != 0:
        return prefetch_result
    return run_commands(
        offline_commands,
        environment=environment,
        packet_path=packet_path,
        packet_digest=packet_digest,
        phase="offline-acceptance",
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PacketTransportError as exc:
        print(f"packet transport refused: {exc}", file=sys.stderr)
        raise SystemExit(2)

