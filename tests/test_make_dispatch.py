from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run_make_target


def target(
    name: str = "check",
    variables: dict[str, object] | None = None,
    command: list[object] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "acceptedVariables": variables or {},
        "argvTemplate": [command or ["python3", "-c", "pass"]],
    }


def descriptor(packet: str, targets: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schemaVersion": run_make_target.SCHEMA_VERSION,
        "packetId": packet,
        "targets": targets,
    }


class MakeDispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="con-001-make-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, packet: str, value: object, filename: str | None = None) -> Path:
        path = self.root / (filename or f"{packet.lower()}.json")
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_repository_descriptor_has_common_targets(self) -> None:
        directory = Path(run_make_target.__file__).with_name("targets")
        rules = run_make_target.load_rules(directory)
        self.assertEqual(
            {rule.name for rule in rules},
            {"build", "help", "prefetch", "test", "typecheck", "zero-bill"},
        )

    def test_missing_and_unknown_target_fail_closed(self) -> None:
        self.write("AAA-001", descriptor("AAA-001", [target()]))
        with self.assertRaisesRegex(run_make_target.TargetDescriptorError, "zero applicable"):
            run_make_target.dispatch("unknown", {}, self.root)
        self.assertEqual(run_make_target.main(()), 2)

    def test_owner_filename_and_duplicate_rules_fail_closed(self) -> None:
        self.write("AAA-001", descriptor("AAA-001", [target()]), filename="wrong.json")
        with self.assertRaisesRegex(run_make_target.TargetDescriptorError, "filename mismatch"):
            run_make_target.load_rules(self.root)
        (self.root / "wrong.json").unlink()
        self.write("AAA-001", descriptor("AAA-001", [target(), target()]))
        with self.assertRaisesRegex(run_make_target.TargetDescriptorError, "duplicate target"):
            run_make_target.load_rules(self.root)

    def test_undeclared_duplicate_and_shell_variables_fail_closed(self) -> None:
        with self.assertRaisesRegex(run_make_target.TargetDescriptorError, "undeclared"):
            run_make_target.parse_supplied_variables(("UNKNOWN=value",))
        with self.assertRaisesRegex(run_make_target.TargetDescriptorError, "duplicate"):
            run_make_target.parse_supplied_variables(("BACKEND=one", "BACKEND=two"))
        self.write("AAA-001", descriptor("AAA-001", [target(command=["sh", "-c", "echo unsafe"])]))
        with self.assertRaisesRegex(run_make_target.TargetDescriptorError, "shell transport"):
            run_make_target.load_rules(self.root)

    def test_argv_variable_must_be_declared(self) -> None:
        command = ["python3", "tool.py", {"variable": "BACKEND"}]
        self.write("AAA-001", descriptor("AAA-001", [target(command=command)]))
        with self.assertRaisesRegex(run_make_target.TargetDescriptorError, "undeclared variable"):
            run_make_target.load_rules(self.root)

    def test_zero_and_ambiguous_applicable_handlers_fail_closed(self) -> None:
        rules = [
            target(variables={"BACKEND": {"enum": ["a", "b"]}}),
            target(variables={"BACKEND": {"enum": ["b", "c"]}}),
        ]
        self.write("AAA-001", descriptor("AAA-001", rules))
        with self.assertRaisesRegex(run_make_target.TargetDescriptorError, "zero applicable"):
            run_make_target.dispatch("check", {}, self.root)
        with self.assertRaisesRegex(run_make_target.TargetDescriptorError, "ambiguous"):
            run_make_target.dispatch("check", {"BACKEND": "b"}, self.root)

    def test_handlers_execute_in_lexical_packet_order_without_shell(self) -> None:
        self.write("BBB-001", descriptor("BBB-001", [target(command=["python3", "bbb.py"])]))
        self.write("AAA-001", descriptor("AAA-001", [target(command=["python3", "aaa.py"])]))
        with patch.object(
            run_make_target.subprocess,
            "run",
            side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=0)],
        ) as mocked:
            self.assertEqual(run_make_target.dispatch("check", {}, self.root), 0)
        self.assertEqual(mocked.call_args_list[0].args[0], ("python3", "aaa.py"))
        self.assertEqual(mocked.call_args_list[1].args[0], ("python3", "bbb.py"))
        self.assertTrue(all(call.kwargs["shell"] is False for call in mocked.call_args_list))


if __name__ == "__main__":
    unittest.main()

