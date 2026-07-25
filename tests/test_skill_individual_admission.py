from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.build_individual_skill_admission import sha256, validate_case


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "skill-fixtures"


class IndividualSkillAdmissionTests(unittest.TestCase):
    def test_record_is_source_bound_and_keeps_unadmitted_skills_blocked(self) -> None:
        record = json.loads((FIXTURES / "individual-skill-admission-v0.1.json").read_text())
        self.assertEqual(record["schema"], "tmcp-individual-skill-admission-v0.1")
        self.assertEqual(record["summary"], {
            "skill_count": 156,
            "case_ready_skill_count": 1,
            "needs_execution_boundary_skill_count": 5,
            "needs_case_or_bar_count": 150,
            "case_count": 6,
        })
        self.assertTrue(record["policy"]["source_bound_cases_only"])
        self.assertTrue(record["policy"]["provenance_checked"])
        self.assertFalse(record["policy"]["automatic_rewrite"])
        self.assertEqual(
            sum(item["admission_status"] == "case_ready" for item in record["skills"]),
            1,
        )
        self.assertTrue(all(
            item["admission_status"] == "case_ready" and item["cases"]
            or item["admission_status"] == "needs_execution_boundary" and item["cases"]
            or item["admission_status"] == "needs_golden_case_and_bar" and not item["cases"]
            for item in record["skills"]
        ))
        self.assertTrue(all(
            case["admission_status"] in {"needs_execution_boundary", "case_ready"}
            and case["bar_status"] == "source_bound"
            and case["execution_boundary"]["status"] in {"incomplete", "complete"}
            and case["provenance"]
            for item in record["skills"]
            for case in item["cases"]
        ))

    def test_case_validation_rejects_unprovenanceable_excerpt(self) -> None:
        source = "/Users/jakyeamos/.agents/skills/find-skills/SKILL.md"
        with self.assertRaisesRegex(ValueError, "invalid provenance"):
            validate_case(
                {
                    "source_path": source,
                    "case_id": "bad",
                    "mode": "judgment",
                    "prompt": "find a skill",
                    "bar": "show a relevant result",
                    "smells": [],
                    "execution_boundary": {"status": "incomplete", "evidence": "fixture lacks source"},
                    "provenance": [{"line": 1, "excerpt": "not in source"}],
                },
                {source: {"source_sha256": sha256(Path(source))}},
            )

    def test_behavior_dispositions_keep_campaign_failures_separate_from_skill_failures(self) -> None:
        record = json.loads(
            (FIXTURES / "individual-skill-behavior-dispositions-v0.1.json").read_text()
        )
        self.assertEqual(record["schema"], "tmcp-individual-skill-behavior-dispositions-v0.1")
        self.assertEqual(record["summary"], {
            "case_count": 6,
            "campaign_ready_case_count": 6,
            "observed_skill_failure_count": 0,
            "rewrite_hold_count": 5,
            "no_candidate_delta_count": 1,
            "behaviorally_passed_case_count": 1,
            "case_or_runner_boundary_count": 5,
        })
        self.assertFalse(record["policy"]["automatic_rewrite"])
        self.assertTrue(record["policy"]["case_quality_and_runner_boundaries_are_separate"])
        self.assertTrue(all(case["observed_skill_failure"] is False for case in record["cases"]))
        self.assertEqual(
            sum(case["rewrite_status"] == "hold" for case in record["cases"]),
            5,
        )
        ownership = next(
            case for case in record["cases"]
            if case["case_id"] == "check-thread-ownership-read-only-current-repo"
        )
        self.assertEqual(ownership["disposition"], "behavioral_baseline_pass")
        self.assertEqual(ownership["rewrite_status"], "no_candidate_delta")
        self.assertEqual(ownership["versions"]["original"]["pass_count"], 3)
        self.assertEqual(ownership["versions"]["candidate"]["pass_count"], 3)


if __name__ == "__main__":
    unittest.main()
