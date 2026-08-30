from __future__ import annotations

import unittest

import run_packet_argv


class OfflineRunnerTests(unittest.TestCase):
    def test_shell_transport_is_rejected(self) -> None:
        with self.assertRaisesRegex(run_packet_argv.PacketTransportError, "shell"):
            run_packet_argv.validate_direct_argv(["sh", "-c", "true"])

    def test_uv_without_all_offline_flags_is_rejected(self) -> None:
        with self.assertRaisesRegex(run_packet_argv.PacketTransportError, "--frozen"):
            run_packet_argv.validate_offline_argv(["uv", "build", "--offline", "--no-sync"])

    def test_prefetch_token_is_rejected_in_acceptance(self) -> None:
        with self.assertRaisesRegex(run_packet_argv.PacketTransportError, "prefetch"):
            run_packet_argv.validate_offline_argv(["python", "tool.py", "prefetch"])

    def test_environment_scrubs_packet_and_credentials(self) -> None:
        clean = run_packet_argv.scrub_environment(
            {
                "PATH": "/bin",
                "HARNESS_TASK_PACKET": "/secret/packet.yaml",
                "GITHUB_TOKEN": "secret",
                "AWS_ACCESS_KEY_ID": "secret",
            }
        )
        self.assertEqual(clean, {"PATH": "/bin"})


if __name__ == "__main__":
    unittest.main()

