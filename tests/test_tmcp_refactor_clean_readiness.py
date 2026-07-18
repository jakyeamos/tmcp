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
MISSING_PACKET_RECEIPT = CANDIDATE_DIR / "packet-probe-receipt.missing.json"
SOURCE_BUNDLE_PATH = CANDIDATE_DIR / "source-bundle"
PACKET_RECEIPT_PATH = CANDIDATE_DIR / "packet-probe-receipt.json"


@unittest.skipUnless(FIXTURE_PATH.is_file(), "source-only refactor-clean candidate")
class RefactorCleanReadinessTests(unittest.TestCase):
    def test_single_reviewed_fixture_is_not_preregistration_ready(self) -> None:
        report = verify_refactor_clean_candidate(
            CANDIDATE_DIR,
            [FIXTURE_PATH],
            source_path=SOURCE_PATH,
            packet_probe_receipt_path=MISSING_PACKET_RECEIPT,
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
                packet_probe_receipt_path=MISSING_PACKET_RECEIPT,
            )
        finally:
            temp_fixture.unlink(missing_ok=True)

        self.assertIn("judge_blindness_incomplete", report["gaps"])

    def test_expanded_fixture_set_binds_each_review_record(self) -> None:
        fixture_paths = sorted((CANDIDATE_DIR / "fixtures").glob("*.json"))
        report = verify_refactor_clean_candidate(
            CANDIDATE_DIR,
            fixture_paths,
            source_path=SOURCE_PATH,
        )

        self.assertEqual(report["fixture_count"], 6)
        self.assertEqual(report["fixture_family_count"], 6)
        self.assertNotIn("fixture_review_record_missing", report["gaps"])
        self.assertNotIn("fixture_review_not_approved", report["gaps"])
        self.assertEqual(report["next_gate"], "archive_source_bundle_and_packet_receipt")
        self.assertEqual(
            {Path(item["path"]).name for item in report["review_records"]},
            {"fixture-review.md", "fixture-expansion-review.md"},
        )

    def test_bound_source_bundle_and_packet_probe_clear_design_gates(self) -> None:
        fixture_paths = sorted((CANDIDATE_DIR / "fixtures").glob("*.json"))
        report = verify_refactor_clean_candidate(
            CANDIDATE_DIR,
            fixture_paths,
            source_path=SOURCE_PATH,
            source_bundle_path=SOURCE_BUNDLE_PATH,
            packet_probe_receipt_path=PACKET_RECEIPT_PATH,
        )

        self.assertTrue(report["ready"])
        self.assertEqual(report["gaps"], [])
        self.assertEqual(report["next_gate"], "create_preregistered_behavioral_plan")
        self.assertEqual(report["source_bundle"]["bundle_sha256"], report["source_sha256"])
        self.assertEqual(report["packet_probe"]["packet_id"], "packet-56b089006b53")
        self.assertFalse(report["packet_probe"]["model_calls"])
        self.assertFalse(report["packet_probe"]["tool_calls"])


if __name__ == "__main__":
    unittest.main()
