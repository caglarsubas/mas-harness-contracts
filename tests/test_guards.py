from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import validate_porting
import zero_bill_scan


class GuardTests(unittest.TestCase):
    def test_repository_porting_ledger_is_inert(self) -> None:
        root = Path(__file__).resolve().parents[1]
        validate_porting.validate_inert_ledger(root / "PORTING.yaml")

    def test_porting_copy_claim_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="con-001-porting-") as directory:
            path = Path(directory) / "PORTING.yaml"
            path.write_text(
                "schemaVersion: harness.planeon.ai/porting-record/v1alpha1\n"
                "destinationRepository: mas-harness-contracts\n"
                "records: [COPY_AUTHORIZED]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "NO_AUTHORIZATION"):
                validate_porting.validate_inert_ledger(path)

    def test_zero_bill_negative_workflow_fixture_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="con-001-zero-bill-") as directory:
            root = Path(directory)
            workflow = root / ".github/workflows/verify.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "permissions:\n  contents: read\n"
                "jobs:\n  verify:\n    runs-on: ubuntu-latest\n"
                "    steps:\n      - uses: actions/cache@v4\n",
                encoding="utf-8",
            )
            violations = zero_bill_scan.scan(root)
            self.assertTrue(any("ubuntu-latest" in item for item in violations))
            self.assertTrue(any("actions/cache" in item for item in violations))


if __name__ == "__main__":
    unittest.main()

