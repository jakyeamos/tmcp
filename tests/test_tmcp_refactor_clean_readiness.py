from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.verify_refactor_clean_candidate import verify_refactor_clean_candidate


CANDIDATE_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "composition-refactor-clean-candidate-v0-2026-07-18"
)
FIXTURE_PATH = CANDIDATE_DIR / "fixtures" / "refactor-clean-dependency-graph-v0.json"
SOURCE_PATH = Path("/Users/jakyeamos/skills/engineering/refactor-clean/SKILL.md")


@unittest.skipUnless(FIXTURE_PATH.is_file(), "source-only refactor-clean candidate")
class RefactorCleanReadinessTests(unittest.TestCase):
    def test_single_reviewed_fixture_is_not_preregistration_ready(self) -> None:
        report = verify_refactor_clean_candidate(
            CANDIDATE_DIR,
            [FIXTURE_PATH],
            source_path=SOURCE_PATH,
        )

        self.assertFalse(report["ready"])
        self.assertIn("fixture_count_below_minimum", report["gaps"])
        self.assertIn("fixture_family_count_below_minimum", report["gaps"])
        self.assertIn("source_bundle_not_archived", report["gaps"])
        self.assertIn("packet_probe_receipt_missing", report["gaps"])
        self.assertEqual(report["candidate_state"], "approved_for_preregistration")
        self.assertFalse(report["model_calls_authorized"])
        self.assertEqual(report["next_gate"], "extend_reviewed_fixture_set")
        self.assertNotIn("fixture_review_not_approved", report["gaps"])

    def test_fixture_identity_and_blindness_are_checked(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        fixture["blindness_contract"]["judge_must_not_receive"] = []
        temp_fixture = CANDIDATE_DIR / "fixtures" / ".tmp-refactor-clean-invalid.json"
        try:
            temp_fixture.write_text(json.dumps(fixture), encoding="utf-8")
            report = verify_refactor_clean_candidate(
                CANDIDATE_DIR,
                [temp_fixture],
                source_path=SOURCE_PATH,
            )
        finally:
            temp_fixture.unlink(missing_ok=True)

        self.assertIn("judge_blindness_incomplete", report["gaps"])


if __name__ == "__main__":
    unittest.main()
