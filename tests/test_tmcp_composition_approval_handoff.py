from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.build_composition_approval_handoff import build_handoff


STUDY_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "composition-refactor-clean-v1-2026-07-18"
)


@unittest.skipUnless(STUDY_DIR.is_dir(), "source-only composition study")
class CompositionApprovalHandoffTests(unittest.TestCase):
    def test_handoff_counts_calls_and_keeps_execution_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "approval-handoff.json"
            report = build_handoff(STUDY_DIR, output)
            output_text = output.read_text(encoding="utf-8")

        self.assertEqual(report["status"], "approval_required")
        self.assertFalse(report["model_calls_authorized"])
        self.assertFalse(report["execution_started"])
        self.assertEqual(report["baseline"]["cell_count"], 36)
        self.assertEqual(report["baseline"]["runner_calls"], 36)
        self.assertEqual(report["baseline"]["primary_judge_calls"], 36)
        self.assertEqual(report["baseline"]["cost_rejudge_calls"], 36)
        self.assertEqual(report["causal"]["cell_count"], 72)
        self.assertEqual(report["causal"]["runner_calls"], 72)
        self.assertEqual(report["causal"]["primary_judge_calls"], 72)
        self.assertEqual(report["causal"]["cost_rejudge_calls"], 72)
        self.assertTrue(report["baseline"]["receipt_required_before_causal"])
        self.assertIsNone(report["baseline"]["receipt_sha256"])
        self.assertIsNone(report["baseline"]["verification_sha256"])
        self.assertEqual(output_text.count("approval_required"), 1)

    def test_handoff_rejects_a_self_declared_but_structurally_invalid_verification(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            study = Path(temporary) / "study"
            shutil.copytree(STUDY_DIR, study)
            verification_path = study / "generated" / "study-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["plan_path"] = str(
                study / "generated" / "tmcp-composition-study-plan.json"
            )
            verification["static"]["plan_valid"] = False
            verification_path.write_text(
                json.dumps(verification, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "plan_valid"):
                build_handoff(study)

    def test_handoff_rejects_readiness_matrix_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            study = Path(temporary) / "study"
            shutil.copytree(STUDY_DIR, study)
            verification_path = study / "generated" / "study-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["plan_path"] = str(
                study / "generated" / "tmcp-composition-study-plan.json"
            )
            verification_path.write_text(
                json.dumps(verification, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            readiness_path = study / "generated" / "baseline-readiness-gate.json"
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
            readiness["runner_models"] = ["unapproved-model"]
            readiness_path.write_text(
                json.dumps(readiness, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "runner models"):
                build_handoff(study)

    def test_handoff_rejects_readiness_effort_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            study = Path(temporary) / "study"
            shutil.copytree(STUDY_DIR, study)
            verification_path = study / "generated" / "study-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["plan_path"] = str(
                study / "generated" / "tmcp-composition-study-plan.json"
            )
            verification_path.write_text(
                json.dumps(verification, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            readiness_path = study / "generated" / "baseline-readiness-gate.json"
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
            readiness["runner_configurations"][0]["reasoning_effort"] = "low"
            readiness_path.write_text(
                json.dumps(readiness, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "runner configurations"):
                build_handoff(study)


if __name__ == "__main__":
    unittest.main()
