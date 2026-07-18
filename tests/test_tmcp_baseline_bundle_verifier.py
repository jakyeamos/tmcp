from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.verify_baseline_bundle import verify_baseline_bundle


STUDY_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "composition-explore-unknowns-v1-2026-07-17"
)
CAUSAL_PLAN = STUDY_DIR / "generated" / "tmcp-composition-study-plan.json"
BASELINE_PLAN = STUDY_DIR / "generated" / "tmcp-composition-baseline-plan.json"


@unittest.skipUnless(CAUSAL_PLAN.is_file(), "source-only composition study")
class BaselineBundleVerifierTests(unittest.TestCase):
    def test_missing_receipt_cannot_become_a_ready_baseline_bundle(self) -> None:
        causal = json.loads(CAUSAL_PLAN.read_text(encoding="utf-8"))
        baseline = json.loads(BASELINE_PLAN.read_text(encoding="utf-8"))
        report = verify_baseline_bundle(
            causal,
            baseline,
            None,
            baseline_plan_path=BASELINE_PLAN,
            manifest_path=None,
            traces_path=None,
            report_path=None,
            receipt_path=None,
        )

        self.assertFalse(report["ready"])
        self.assertIn("baseline_receipt_required", report["gaps"])
        self.assertIn("baseline_receipt_digest_not_preregistered", report["gaps"])
        self.assertNotIn("baseline_plan_not_derived_from_causal_plan", report["gaps"])

    def test_detached_manifest_and_trace_paths_are_rejected(self) -> None:
        causal = json.loads(CAUSAL_PLAN.read_text(encoding="utf-8"))
        baseline = json.loads(BASELINE_PLAN.read_text(encoding="utf-8"))
        report = verify_baseline_bundle(
            causal,
            baseline,
            None,
            baseline_plan_path=BASELINE_PLAN,
            manifest_path=Path("/tmp/missing-baseline-manifest.json"),
            traces_path=Path("/tmp/missing-baseline-traces.json"),
            report_path=Path("/tmp/missing-baseline-report.json"),
            receipt_path=None,
        )

        self.assertFalse(report["ready"])
        self.assertIn("baseline_manifest_missing", report["gaps"])
        self.assertIn("baseline_traces_missing", report["gaps"])
        self.assertIn("baseline_report_missing", report["gaps"])


if __name__ == "__main__":
    unittest.main()
