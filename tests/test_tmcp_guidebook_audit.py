from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_skill_guidebook import audit_guidebook


ROOT = Path(__file__).resolve().parents[1]


class GuidebookAuditTests(unittest.TestCase):
    def test_checked_in_guidebook_and_catalog_pass_audit(self) -> None:
        evidence_root = ROOT / "docs/evidence"
        if not evidence_root.is_dir():
            self.skipTest("source-only evidence bundles are not packaged")
        report = audit_guidebook()

        self.assertTrue(report["passed"], report["issues"])
        self.assertEqual(report["entry_count"], 2)
        self.assertEqual(report["projection_count"], 11)
        self.assertEqual(report["controlled_claim_count"], 1)

    def test_audit_rejects_missing_controlled_experiment_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = json.loads(
                (ROOT / "docs/SKILL_PATTERN_CATALOG.json").read_text(encoding="utf-8")
            )
            catalog["guidebook_entries"][0]["experiment"] = "missing-experiment"
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            guidebook_path = root / "guidebook.md"
            guidebook_path.write_text(
                (ROOT / "docs/SKILL_WRITING_GUIDEBOOK.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            report = audit_guidebook(
                catalog_path=catalog_path,
                guidebook_path=guidebook_path,
                evidence_root=ROOT / "docs/evidence",
            )

            self.assertFalse(report["passed"])
            self.assertIn("missing-experiment is absent from evidence", report["issues"][0])

    def test_audit_rejects_projection_that_strengthens_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = json.loads(
                (ROOT / "docs/SKILL_PATTERN_CATALOG.json").read_text(encoding="utf-8")
            )
            catalog["patterns"][2]["evidence_level"] = "production_reinforced"
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            report = audit_guidebook(
                catalog_path=catalog_path,
                guidebook_path=ROOT / "docs/SKILL_WRITING_GUIDEBOOK.md",
                evidence_root=ROOT / "docs/evidence",
            )

            self.assertFalse(report["passed"])
            self.assertIn(
                "projection weakened evidence level for evaluation.staged-workflow-section",
                report["issues"],
            )


if __name__ == "__main__":
    unittest.main()
