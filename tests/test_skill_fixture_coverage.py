from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.audit_skill_fixture_coverage import audit_manifest


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_skill_fixture_coverage.py"


class SkillFixtureCoverageTests(unittest.TestCase):
    def test_audit_reports_ready_and_unready_skill_counts(self) -> None:
        report = audit_manifest(
            {
                "schema": "tmcp-skill-fixture-manifest-v0.1",
                "fixture_set_id": "synthetic",
                "skills": [
                    {
                        "skill_id": "ready",
                        "readiness": "ready",
                        "cases": [{"case_id": "case-1"}],
                    },
                    {
                        "skill_id": "unready",
                        "readiness": "needs_golden_case_and_bar",
                        "cases": [],
                    },
                ],
            },
            manifest_bytes=b"synthetic",
        )
        self.assertTrue(report["manifest_integrity_pass"])
        self.assertFalse(report["corpus_promotion_ready"])
        self.assertEqual(report["skill_count"], 2)
        self.assertEqual(report["ready_skill_count"], 1)
        self.assertEqual(report["case_count"], 1)
        self.assertEqual(report["needs_case_or_bar_count"], 1)
        self.assertEqual(len(report["manifest_sha256"]), 64)

    def test_audit_rejects_duplicate_case_ids(self) -> None:
        report = audit_manifest(
            {
                "skills": [
                    {
                        "skill_id": "one",
                        "readiness": "ready",
                        "cases": [{"case_id": "duplicate"}],
                    },
                    {
                        "skill_id": "two",
                        "readiness": "ready",
                        "cases": [{"case_id": "duplicate"}],
                    },
                ]
            }
        )
        self.assertFalse(report["manifest_integrity_pass"])
        self.assertIn("duplicate", report["duplicate_case_ids"])

    def test_cli_emits_coverage_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"skills": []}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(AUDIT), str(manifest)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0)
            report = json.loads(completed.stdout)
            self.assertEqual(report["skill_count"], 0)
            self.assertTrue(report["manifest_integrity_pass"])


if __name__ == "__main__":
    unittest.main()
