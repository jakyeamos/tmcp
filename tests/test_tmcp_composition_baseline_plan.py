from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.generate_composition_baseline_plan import build_baseline_plan
from scripts.tmcp_skill_eval_campaign_protocol import build_cells, selected_rows
from tmcp_runtime.api.evaluation import validate_evaluation_plan


STUDY_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "composition-explore-unknowns-v1-2026-07-17"
)
SOURCE_PLAN = STUDY_DIR / "generated" / "tmcp-composition-study-plan.json"
BASELINE_PLAN = STUDY_DIR / "generated" / "tmcp-composition-baseline-plan.json"


@unittest.skipUnless(SOURCE_PLAN.is_file(), "source-only composition study")
class CompositionBaselinePlanTests(unittest.TestCase):
    def test_checked_in_baseline_plan_is_derived_and_control_only(self) -> None:
        source = json.loads(SOURCE_PLAN.read_text(encoding="utf-8"))
        generated = build_baseline_plan(source)
        checked_in = json.loads(BASELINE_PLAN.read_text(encoding="utf-8"))
        self.assertEqual(generated, checked_in)
        validate_evaluation_plan(checked_in)
        self.assertEqual(
            checked_in["experiment"]["campaign_policy"]["design"],
            "baseline_reliability",
        )
        self.assertEqual(
            checked_in["experiment"]["baseline_source_experiment_id"],
            source["experiment"]["experiment_id"],
        )
        self.assertNotIn("baseline_dependency", checked_in["experiment"])

    def test_baseline_cells_bind_exactly_to_the_causal_control(self) -> None:
        source = json.loads(SOURCE_PLAN.read_text(encoding="utf-8"))
        baseline = json.loads(BASELINE_PLAN.read_text(encoding="utf-8"))
        source_controls = {
            str(row["task_id"]): row
            for row in selected_rows(
                source,
                pattern_id="composition.source-bundle-inclusion",
                intervention_target="source_bundle",
                design="baseline_reliability",
            )
        }
        baseline_controls = selected_rows(
            baseline,
            pattern_id="composition.source-bundle-inclusion",
            intervention_target="source_bundle",
            design="baseline_reliability",
        )
        self.assertEqual(len(baseline_controls), 6)
        self.assertEqual(
            {
                str(row["task_id"]): row["fixture_digest"]
                for row in baseline_controls
            },
            {task_id: row["fixture_digest"] for task_id, row in source_controls.items()},
        )
        self.assertEqual(
            {
                str(row["task_id"]): row["skill_attachment"]
                for row in baseline_controls
            },
            {task_id: row["skill_attachment"] for task_id, row in source_controls.items()},
        )
        self.assertEqual(
            {
                str(row["task_id"]): row["skill_digest"]
                for row in baseline_controls
            },
            {task_id: row["skill_digest"] for task_id, row in source_controls.items()},
        )
        self.assertEqual(
            {
                str(row["task_id"]): row["composition_provenance"]["packet_sha256"]
                for row in baseline_controls
            },
            {
                task_id: row["composition_provenance"]["packet_sha256"]
                for task_id, row in source_controls.items()
            },
        )
        self.assertEqual(
            baseline["experiment"]["analysis_policy"],
            source["experiment"]["analysis_policy"],
        )
        self.assertEqual(
            baseline["experiment"]["promotion_thresholds"],
            source["experiment"]["promotion_thresholds"],
        )
        self.assertEqual(
            baseline["experiment"]["campaign_policy"]["runner_configurations"],
            source["experiment"]["campaign_policy"]["runner_configurations"],
        )
        self.assertEqual(
            baseline["experiment"]["campaign_policy"]["judge_configuration"],
            source["experiment"]["campaign_policy"]["judge_configuration"],
        )
        cells = build_cells(
            baseline,
            pattern_id="composition.source-bundle-inclusion",
            intervention_target="source_bundle",
            model="unused",
            runner_efforts=[],
            runner_configurations=[
                ("gpt-5.6-sol", "high"),
                ("gpt-5.6-terra", "high"),
                ("gpt-5.6-luna", "high"),
            ],
            design="baseline_reliability",
            repetitions=2,
            expected_fixtures=6,
            seed=20260717,
            codex_version="codex-cli-0.144.2",
        )
        self.assertEqual(len(cells), 36)
        self.assertEqual({cell.variant_id for cell in cells}, {"packet_only"})
        self.assertEqual({cell.fixture_digest for cell in cells}, {
            str(row["fixture_digest"]) for row in baseline_controls
        })


if __name__ == "__main__":
    unittest.main()
