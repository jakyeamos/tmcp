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
        self.assertEqual(report["entry_count"], 5)
        self.assertEqual(report["projection_count"], 5)
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

    def test_audit_rejects_eligible_entry_without_policy_bound_replication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            entry = catalog["guidebook_entries"][0]
            entry["evidence_level"] = "controlled_multi_agent_eval"
            entry["experiment"] = "composition-study"
            entry["promotion"] = {
                "decision": "eligible_for_manual_review",
                "eligible": True,
            }
            catalog["patterns"][0]["evidence_level"] = "controlled_multi_agent_eval"
            catalog["patterns"][0]["promotion"] = dict(entry["promotion"])
            evidence_root = root / "evidence"
            evidence_root.mkdir()
            (evidence_root / "study.md").write_text(
                "composition-study", encoding="utf-8"
            )
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

            report = audit_guidebook(
                catalog_path=catalog_path,
                guidebook_path=GUIDEBOOK_PATH,
                evidence_root=evidence_root,
            )

            self.assertFalse(report["passed"])
            self.assertIn(
                "verification.concrete-command eligible promotion has no policy envelope",
                report["issues"],
            )
            self.assertIn(
                "verification.concrete-command eligible promotion has no evidence_refs",
                report["issues"],
            )
            self.assertIn(
                "verification.concrete-command eligible promotion has no replication record",
                report["issues"],
            )

    def test_audit_rejects_auto_apply_even_with_replication_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            entry = catalog["guidebook_entries"][0]
            entry.update(
                {
                    "evidence_level": "controlled_single_agent_eval",
                    "experiment": "composition-study",
                    "promotion": {
                        "decision": "eligible_for_manual_review",
                        "eligible": True,
                    },
                    "promotion_policy": {
                        "auto_apply": True,
                        "requires_human_review": True,
                        "requires_replication": True,
                        "requires_independent_rejudge": True,
                    },
                    "evidence_refs": ["primary-digest", "rejudge-digest"],
                    "replication": {"primary": True, "independent_rejudge": True},
                }
            )
            catalog["patterns"][0].update(
                {
                    "evidence_level": entry["evidence_level"],
                    "promotion": dict(entry["promotion"]),
                }
            )
            evidence_root = root / "evidence"
            evidence_root.mkdir()
            (evidence_root / "study.md").write_text(
                "composition-study", encoding="utf-8"
            )
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

            report = audit_guidebook(
                catalog_path=catalog_path,
                guidebook_path=GUIDEBOOK_PATH,
                evidence_root=evidence_root,
            )

            self.assertFalse(report["passed"])
            self.assertIn(
                "verification.concrete-command promotion policy auto_apply must be False",
                report["issues"],
            )


if __name__ == "__main__":
    unittest.main()
