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
            "case_ready_skill_count": 0,
            "needs_execution_boundary_skill_count": 5,
            "needs_case_or_bar_count": 151,
            "case_count": 5,
        })
        self.assertTrue(record["policy"]["source_bound_cases_only"])
        self.assertTrue(record["policy"]["provenance_checked"])
        self.assertFalse(record["policy"]["automatic_rewrite"])
        self.assertTrue(all(
            item["admission_status"] == "needs_execution_boundary" and item["cases"]
            or item["admission_status"] == "needs_golden_case_and_bar" and not item["cases"]
            for item in record["skills"]
        ))
        self.assertTrue(all(
            case["admission_status"] == "needs_execution_boundary"
            and case["bar_status"] == "source_bound"
            and case["execution_boundary"]["status"] == "incomplete"
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


if __name__ == "__main__":
    unittest.main()
