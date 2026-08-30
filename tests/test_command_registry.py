from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from planeon_harness_contracts.cli import main as cli_main
from planeon_harness_contracts.command_registry import (
    SCHEMA_VERSION,
    build_command_registry,
    load_command_registry,
)
from planeon_harness_contracts.errors import CommandRegistryError


def descriptor(packet: str = "CON-002", command: str = "validate", handler: str = "planeon_harness_contracts.validation:reject_unregistered_kind") -> dict[str, str]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "packetId": packet,
        "command": command,
        "handler": handler,
    }


class CommandRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="con-001-command-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, value: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_bootstrap_cli_has_no_registered_commands(self) -> None:
        self.assertEqual(dict(load_command_registry()), {})
        self.assertEqual(cli_main(("--self-check",)), 0)

    def test_valid_future_descriptor_requires_authorized_owner(self) -> None:
        path = self.write("validate.json", descriptor())
        registry = build_command_registry((path,), authorized_packets={"CON-002"})
        self.assertEqual(tuple(registry), ("validate",))
        with self.assertRaisesRegex(CommandRegistryError, "predecessor closure"):
            build_command_registry((path,), authorized_packets={"CON-001"})

    def test_unknown_command_is_rejected(self) -> None:
        path = self.write("mystery.json", descriptor(command="mystery"))
        with self.assertRaisesRegex(CommandRegistryError, "owner mismatch"):
            build_command_registry((path,))

    def test_duplicate_command_transport_is_rejected(self) -> None:
        path = self.write("validate.json", descriptor())
        with self.assertRaisesRegex(CommandRegistryError, "duplicate"):
            build_command_registry((path, path))

    def test_owner_and_filename_mismatch_is_rejected(self) -> None:
        wrong_owner = self.write("validate.json", descriptor(packet="CON-004"))
        with self.assertRaisesRegex(CommandRegistryError, "owner mismatch"):
            build_command_registry((wrong_owner,))
        wrong_name = self.write("catalog.json", descriptor())
        with self.assertRaisesRegex(CommandRegistryError, "filename mismatch"):
            build_command_registry((wrong_name,))

    def test_handler_outside_packet_authority_is_rejected(self) -> None:
        path = self.write(
            "validate.json",
            descriptor(handler="planeon_harness_contracts.compiler:main"),
        )
        with self.assertRaisesRegex(CommandRegistryError, "outside packet authority"):
            build_command_registry((path,))

    def test_shell_or_extra_fields_are_rejected(self) -> None:
        shell = self.write("validate.json", descriptor(handler="sh:main"))
        with self.assertRaisesRegex(CommandRegistryError, "closed Python reference"):
            build_command_registry((shell,))
        extra = descriptor()
        extra["argv"] = "echo unsafe"
        self.write("validate.json", extra)
        with self.assertRaisesRegex(CommandRegistryError, "fields are closed"):
            build_command_registry((self.root / "validate.json",))


if __name__ == "__main__":
    unittest.main()

