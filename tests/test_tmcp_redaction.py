from __future__ import annotations

import unittest

from scripts.tmcp_redaction import looks_high_entropy


class TmcpRedactionTests(unittest.TestCase):
    def test_code_identifier_assignments_are_not_secret_like(self) -> None:
        self.assertFalse(
            looks_high_entropy("canonical_cli_command=CLI_CANONICAL_COMMANDS")
        )
        self.assertFalse(looks_high_entropy("output_schema_ids=TOOL_OUTPUT_SCHEMA_IDS"))

    def test_lowercase_schema_paths_are_not_secret_like(self) -> None:
        self.assertFalse(
            looks_high_entropy("schemas/tmcp-codex-desktop-bridge-build-v0")
        )
        self.assertFalse(
            looks_high_entropy("tmcp-invocation-admission-overhead-pilot-v0")
        )

    def test_opaque_token_remains_secret_like(self) -> None:
        opaque_token = "A9b8C7d6E5f4G3h2I1j0" + "K9l8M7n6O5p4Q3r2S1t0"

        self.assertTrue(looks_high_entropy(opaque_token))
