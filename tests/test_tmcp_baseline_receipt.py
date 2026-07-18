from __future__ import annotations

import unittest
from pathlib import Path

from scripts.build_baseline_receipt import (
    build_baseline_receipt,
    _load_list,
    _load_object,
)


BASELINE_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "skill-eval-multiconfig-2026-07-17"
    / "fresh-baseline"
)


@unittest.skipUnless(
    (BASELINE_DIR / "generated" / "tmcp-skill-evaluation-plan.json").is_file(),
    "source-only baseline evidence bundle",
)
class BaselineReceiptTests(unittest.TestCase):
    def test_held_baseline_builds_completed_but_ineligible_receipt(self) -> None:
        plan_path = BASELINE_DIR / "generated" / "tmcp-skill-evaluation-plan.json"
        manifest_path = BASELINE_DIR / "runs" / "campaign-manifest.json"
        traces_path = BASELINE_DIR / "runs" / "traces.json"
        report_path = (
            BASELINE_DIR / "scored" / "reinterpreted" / "tmcp-skill-evaluation-report.json"
        )
        receipt = build_baseline_receipt(
            _load_object(plan_path),
            _load_object(manifest_path),
            _load_list(traces_path),
            _load_object(report_path),
            plan_path=plan_path,
            manifest_path=manifest_path,
            traces_path=traces_path,
            report_path=report_path,
        )

        self.assertEqual(receipt["schema"], "tmcp-skill-eval-baseline-receipt-v0.1")
        self.assertEqual(receipt["evidence_state"], "completed")
        self.assertFalse(receipt["causal_applicable"])
        self.assertFalse(receipt["meets_predeclared_floors"])
        self.assertEqual(receipt["counts"]["fixture_count"], 6)
        self.assertEqual(receipt["cost"]["adjudicated_status"], "regression")
        self.assertTrue(receipt["evidence"]["report_sha256"].startswith("sha256:"))

    def test_builder_rejects_a_causal_source_plan(self) -> None:
        plan = {"experiment": {"campaign_policy": {"design": "causal_contrast"}}}
        with self.assertRaisesRegex(ValueError, "not a baseline reliability plan"):
            build_baseline_receipt(
                plan,
                {},
                [],
                {},
                plan_path=Path("plan.json"),
                manifest_path=Path("manifest.json"),
                traces_path=Path("traces.json"),
                report_path=Path("report.json"),
            )


if __name__ == "__main__":
    unittest.main()
