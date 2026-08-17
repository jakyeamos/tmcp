from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "score_invocation_admission_pilot",
    ROOT / "scripts" / "score_invocation_admission_pilot.py",
)
assert SPEC and SPEC.loader
scorer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scorer)


class InvocationAdmissionPilotScoringTests(unittest.TestCase):
    def _write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def _corpus(self, root: Path) -> tuple[Path, Path]:
        manifest = {
            "tasks": [
                {
                    "fixture_id": "skill-creator-rotate-pdf",
                    "prompt": "Create a bounded PDF rotation plan.",
                    "expected_automatic_action": "bypass",
                    "negative_control": True,
                    "review_or_audit_task": False,
                }
            ],
            "policies": [
                {"id": "explicit-only"},
                {"id": "always-on"},
                {"id": "admission-controlled"},
            ],
            "matrix_rows": 3,
            "acceptance": {
                "quality_noninferiority_margin": 0.25,
                "minimum_median_overhead_reduction_vs_always_on": 0.2,
                "maximum_review_source_rate_for_non_review_tasks": 0.05,
                "overhead_evaluation_scope": "negative_controls",
            },
        }
        manifest_path = root / "manifest.json"
        self._write_json(manifest_path, manifest)
        pilot_dir = root / "pilot"
        rows = []
        for index, policy in enumerate(
            ("explicit-only", "always-on", "admission-controlled"), start=1
        ):
            blind_id = f"pilot-{index:03d}"
            action = {
                "explicit-only": "disabled",
                "always-on": "forced",
                "admission-controlled": "bypass",
            }[policy]
            rows.append(
                {
                    "blind_id": blind_id,
                    "fixture_id": "skill-creator-rotate-pdf",
                    "policy_id": policy,
                    "metrics": {
                        "admission_action": action,
                        "packet_injected": policy == "always-on",
                        "packet_markdown_chars": 100 if policy == "always-on" else 0,
                        "review_source_count": 0,
                        "runner_wall_time_ms": (100 if policy == "always-on" else 50),
                        "selected_source_count": 0,
                    },
                }
            )
            artifact = pilot_dir / "runner-artifacts" / f"{blind_id}.md"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("bounded artifact\n", encoding="utf-8")
            self._write_json(
                pilot_dir / "judge-results" / f"{blind_id}.json",
                {
                    "blind_id": blind_id,
                    "pass": True,
                    "weighted_score": 0.9,
                    "verification_quality_score": 0.9,
                    "irrelevant_constraint_count": 0,
                    "unsafe_or_unjustified_action_count": 0,
                    "dimensions": [
                        {"id": "scope", "score": 0.9, "evidence": "bounded"}
                    ],
                    "smells_present": [],
                    "reason": "bar satisfied",
                },
            )
        self._write_json(
            pilot_dir / "secret-plan.json",
            {"row_count": 3, "rows": rows, "unavailable_measures": []},
        )
        return manifest_path, pilot_dir

    def test_complete_corpus_scores_and_applies_all_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path, pilot_dir = self._corpus(Path(tmp))
            report = scorer.score(manifest_path, pilot_dir)

        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["rows_scored"], 3)
        self.assertTrue(report["promotion_authorized"])
        self.assertTrue(
            all(item["passed"] for item in report["acceptance_gates"].values())
        )
        overhead = report["acceptance_gates"]["median_overhead_reduction_vs_always_on"]
        self.assertEqual(overhead["scope"], "negative_controls")
        self.assertEqual(overhead["admission_rows"], 1)
        self.assertEqual(overhead["always_on_rows"], 1)

    def test_partial_corpus_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path, pilot_dir = self._corpus(Path(tmp))
            (pilot_dir / "judge-results" / "pilot-003.json").unlink()
            with self.assertRaisesRegex(ValueError, "missing judge result"):
                scorer.score(manifest_path, pilot_dir)


if __name__ == "__main__":
    unittest.main()
