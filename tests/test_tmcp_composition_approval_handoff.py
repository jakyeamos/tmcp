from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.build_composition_approval_handoff import build_handoff


STUDY_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "composition-refactor-clean-v1-2026-07-18"
)


@unittest.skipUnless(STUDY_DIR.is_dir(), "source-only composition study")
class CompositionApprovalHandoffTests(unittest.TestCase):
    def test_handoff_counts_calls_and_keeps_execution_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "approval-handoff.json"
            report = build_handoff(STUDY_DIR, output)
            output_text = output.read_text(encoding="utf-8")

        self.assertEqual(report["status"], "approval_required")
        self.assertFalse(report["model_calls_authorized"])
        self.assertFalse(report["execution_started"])
        self.assertEqual(report["baseline"]["cell_count"], 36)
        self.assertEqual(report["baseline"]["runner_calls"], 36)
        self.assertEqual(report["baseline"]["primary_judge_calls"], 36)
        self.assertEqual(report["baseline"]["cost_rejudge_calls"], 36)
        self.assertEqual(report["causal"]["cell_count"], 72)
        self.assertEqual(report["causal"]["runner_calls"], 72)
        self.assertEqual(report["causal"]["primary_judge_calls"], 72)
        self.assertEqual(report["causal"]["cost_rejudge_calls"], 72)
        self.assertTrue(report["baseline"]["receipt_required_before_causal"])
        self.assertIsNone(report["baseline"]["receipt_sha256"])
        self.assertIsNone(report["baseline"]["verification_sha256"])
        self.assertEqual(output_text.count("approval_required"), 1)


if __name__ == "__main__":
    unittest.main()
