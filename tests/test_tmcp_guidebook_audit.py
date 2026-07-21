from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_skill_guidebook import audit_guidebook


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "docs" / "SKILL_PATTERN_CATALOG.json"
GUIDEBOOK_PATH = ROOT / "docs" / "SKILL_WRITING_GUIDEBOOK.md"


class GuidebookAuditTests(unittest.TestCase):
    def test_checked_in_guidebook_and_catalog_pass_audit(self) -> None:
        report = audit_guidebook()

        self.assertTrue(report["passed"], report["issues"])
        self.assertEqual(report["entry_count"], 4)
        self.assertEqual(report["projection_count"], 4)
        self.assertEqual(report["controlled_claim_count"], 0)

    def test_audit_rejects_controlled_claim_without_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            entry = catalog["guidebook_entries"][0]
            entry["evidence_level"] = "controlled_single_agent_eval"
            entry["experiment"] = "missing-experiment"
            catalog["patterns"][0]["evidence_level"] = "controlled_single_agent_eval"
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

            report = audit_guidebook(
                catalog_path=catalog_path,
                guidebook_path=GUIDEBOOK_PATH,
                evidence_root=root / "evidence",
            )

            self.assertFalse(report["passed"])
            self.assertTrue(
                any(
                    "missing-experiment is absent from evidence" in issue
                    for issue in report["issues"]
                )
            )

    def test_audit_rejects_projection_that_strengthens_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            catalog["patterns"][1]["evidence_level"] = "production_reinforced"
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

            report = audit_guidebook(
                catalog_path=catalog_path,
                guidebook_path=GUIDEBOOK_PATH,
                evidence_root=root / "evidence",
            )

            self.assertFalse(report["passed"])
            self.assertIn(
                "projection changed evidence_level for verification.vague-quality-language",
                report["issues"],
            )


if __name__ == "__main__":
    unittest.main()
