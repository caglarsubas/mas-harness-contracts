from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from planeon_harness_contracts import build_backend


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BuildBackendTests(unittest.TestCase):
    def test_two_wheel_and_sdist_builds_are_identical(self) -> None:
        results: list[dict[str, str]] = []
        for _index in range(2):
            with tempfile.TemporaryDirectory(prefix="con-001-build-") as directory:
                root = Path(directory)
                wheel = root / build_backend.build_wheel(str(root))
                sdist = root / build_backend.build_sdist(str(root))
                results.append({wheel.name: digest(wheel), sdist.name: digest(sdist)})
        self.assertEqual(results[0], results[1])

    def test_backend_declares_no_build_dependencies(self) -> None:
        self.assertEqual(build_backend.get_requires_for_build_wheel(), [])
        self.assertEqual(build_backend.get_requires_for_build_sdist(), [])
        self.assertEqual(build_backend.get_requires_for_build_editable(), [])


if __name__ == "__main__":
    unittest.main()

