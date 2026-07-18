from __future__ import annotations

import unittest

from scripts.tmcp_redaction import looks_high_entropy, redact_sensitive_text
from tmcp_runtime.safety import redact_json_value


class TmcpRedactionTests(unittest.TestCase):
    def test_code_identifier_assignments_are_not_secret_like(self) -> None:
        self.assertFalse(
            looks_high_entropy("canonical_cli_command=CLI_CANONICAL_COMMANDS")
        )
        self.assertFalse(looks_high_entropy("output_schema_ids=TOOL_OUTPUT_SCHEMA_IDS"))
        self.assertFalse(
            looks_high_entropy("test_builds_full_randomized_72_cell_matrix")
        )
        self.assertFalse(
            looks_high_entropy("tmcp-skill-eval-campaign-harness-snapshot-v0")
        )
        self.assertFalse(
            looks_high_entropy("composition-refactor-clean-candidate-v0-2026-07-18")
        )

    def test_opaque_token_remains_secret_like(self) -> None:
        opaque_token = "A9b8C7d6E5f4G3h2I1j0" + "K9l8M7n6O5p4Q3r2S1t0"

        self.assertTrue(looks_high_entropy(opaque_token))

    def test_public_document_path_is_not_secret_like(self) -> None:
        source = "docs/SKILL_EVALUATION_CAMPAIGN_GUIDEBOOK.md"

        self.assertFalse(looks_high_entropy(source.removesuffix(".md")))
        redacted, summary = redact_sensitive_text(source)

        self.assertEqual(redacted, source)
        self.assertEqual(summary, {})

        safe_payload, payload_summary = redact_json_value(
            {"evidence_citations": [{"source": source}]}, enabled=True
        )

        self.assertEqual(safe_payload, {"evidence_citations": [{"source": source}]})
        self.assertEqual(payload_summary, {})

    def test_opaque_basename_within_a_path_remains_secret_like(self) -> None:
        source = "docs/" + ("A9b8C7d6E5f4G3h2I1j0" * 2)

        self.assertTrue(looks_high_entropy(source))
        redacted, summary = redact_sensitive_text(source)

        self.assertEqual(redacted, "[REDACTED:long_high_entropy]")
        self.assertEqual(summary, {"long_high_entropy": 1})
