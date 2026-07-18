from __future__ import annotations

import json
import unittest
from pathlib import Path


CANDIDATE_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "composition-refactor-clean-candidate-v0-2026-07-18"
)
FIXTURE_PATH = CANDIDATE_DIR / "fixtures" / "refactor-clean-dependency-graph-v0.json"


@unittest.skipUnless(FIXTURE_PATH.is_file(), "source-only composition candidate")
class RefactorCleanCandidateTests(unittest.TestCase):
    def test_candidate_keeps_the_bar_and_hypothesis_blind_to_runners(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        blindness = fixture["blindness_contract"]

        self.assertEqual(fixture["schema"], "tmcp-refactor-clean-fixture-review-v0.1")
        self.assertEqual(fixture["review_status"], "author_draft")
        self.assertEqual(fixture["evaluation_mode"], "judgment")
        runner_prompt = fixture["fixture"]["runner_prompt"]
        self.assertTrue(runner_prompt.strip())
        self.assertTrue(fixture["outcome_bar"]["standard"].strip())
        self.assertGreaterEqual(len(fixture["outcome_bar"]["expected_observables"]), 3)
        self.assertGreaterEqual(len(fixture["outcome_bar"]["failure_smells"]), 3)
        for criterion in fixture["outcome_bar"]["expected_observables"]:
            self.assertNotIn(criterion, runner_prompt)
        for smell in fixture["outcome_bar"]["failure_smells"]:
            self.assertNotIn(smell, runner_prompt)
        self.assertIn("outcome_bar", blindness["runner_must_not_receive"])
        self.assertIn("failure_smells", blindness["runner_must_not_receive"])
        self.assertIn("hypothesis or arm label", blindness["runner_must_not_receive"])
        self.assertIn("runner artifact", blindness["judge_receives"])
        self.assertIn("fixture arm label", blindness["judge_must_not_receive"])

    def test_candidate_review_record_is_scope_limited(self) -> None:
        review = (CANDIDATE_DIR / "fixture-review.md").read_text(encoding="utf-8")
        readme = (CANDIDATE_DIR / "README.md").read_text(encoding="utf-8")

        self.assertIn("Status: **approved for preregistration only.**", review)
        self.assertIn("/root/refactor_fixture_review", review)
        self.assertIn("Non-blocking hardening before preregistration", review)
        self.assertIn("No behavioral effect or guidebook pattern", review)
        self.assertIn("campaign ledger remains `Packet-probed`", review)
        self.assertIn("not independently reviewed", readme)
        self.assertIn("No runner, judge, or external model call", readme)
