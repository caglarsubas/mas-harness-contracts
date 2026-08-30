from __future__ import annotations

import unittest

import uv_compat


class UvCompatibilityTests(unittest.TestCase):
    def test_packet_build_flags_normalize_for_pinned_uv(self) -> None:
        self.assertEqual(
            uv_compat.normalized_argv(("build", "--offline", "--frozen", "--no-sync")),
            ("build", "--offline"),
        )

    def test_missing_or_duplicate_build_flags_fail_closed(self) -> None:
        with self.assertRaisesRegex(uv_compat.UvCompatibilityError, "--frozen"):
            uv_compat.normalized_argv(("build", "--offline", "--no-sync"))
        with self.assertRaisesRegex(uv_compat.UvCompatibilityError, "--offline"):
            uv_compat.normalized_argv(
                ("build", "--offline", "--offline", "--frozen", "--no-sync")
            )

    def test_non_build_argv_is_not_reinterpreted(self) -> None:
        command = ("run", "--offline", "--frozen", "--no-sync", "python", "-V")
        self.assertEqual(uv_compat.normalized_argv(command), command)

    def test_offline_environment_is_required(self) -> None:
        with self.assertRaisesRegex(uv_compat.UvCompatibilityError, "UV_FROZEN"):
            uv_compat.execution_environment({"UV_OFFLINE": "1", "UV_NO_SYNC": "1"})


if __name__ == "__main__":
    unittest.main()

