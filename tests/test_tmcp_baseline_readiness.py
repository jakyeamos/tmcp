from __future__ import annotations

import unittest

from scripts.tmcp_skill_eval_campaign_planning import _json_sha256
from scripts.tmcp_skill_eval_campaign_protocol import (
    BASELINE_RECEIPT_SCHEMA,
    CampaignCell,
    build_cells,
    campaign_readiness_report,
)
from tmcp_runtime.services.evaluation_plan import displayed_content_digest


class BaselineReadinessTests(unittest.TestCase):
    def _plan(self) -> dict:
        rows = []
        for fixture_index in range(6):
            for variant in ("original", "ablated"):
                rows.append(
                    {
                        "experiment_id": "experiment-1",
                        "matrix_row_id": f"row-{fixture_index}-{variant}",
                        "task_id": f"task-{fixture_index}",
                        "fixture_family": f"family-{fixture_index}",
                        "fixture_digest": f"fixture-{fixture_index}",
                        "pattern_id": "evaluation.staged-workflow-section",
                        "intervention_target": "workflow",
                        "variant_id": variant,
                        "ablation_section": "workflow"
                        if variant == "ablated"
                        else None,
                        "skill_attachment": "ATTACHMENT_ONLY",
                        "prompt": "TASK_ONLY",
                        "expected_observables": ["BAR_SECRET"],
                        "failure_smells": ["SMELL_SECRET"],
                    }
                )
        return {"experiment": {"experiment_id": "experiment-1"}, "task_matrix": rows}

    def _causal_plan_with_baseline(self) -> tuple[dict, list[CampaignCell], dict]:
        plan = self._plan()
        for row in plan["task_matrix"]:
            row["control_variant"] = "original"
            row["intervention_variant"] = "ablated"
        configurations = [("model-a", "high"), ("model-b", "high"), ("model-c", "high")]
        plan["experiment"].update(
            {
                "analysis_policy": {
                    "clustered_interval": {
                        "method": "fixture_block_bootstrap_by_configuration",
                        "confidence": 0.95,
                        "cluster_unit": "fixture_digest",
                        "resamples": 10000,
                        "seed": 7,
                    }
                },
                "promotion_thresholds": {
                    "controlled_multi_agent_eval": {
                        "minimum_control_pass_rate": 0.5,
                        "minimum_per_fixture_control_pass_rate": 0.5,
                    }
                },
                "campaign_policy": {
                    "schema": "tmcp-skill-eval-campaign-policy-v0.1",
                    "design": "causal_contrast",
                    "runner_configurations": [
                        {"model": model, "reasoning_effort": effort}
                        for model, effort in configurations
                    ],
                    "baseline_reliability": {
                        "control_variant": "original",
                        "minimum_control_pass_rate": 0.5,
                        "minimum_per_fixture_control_pass_rate": 0.5,
                        "require_predeclared_clustered_interval": True,
                    },
                    "fixture_review": {
                        "independent_reviewer": True,
                        "prompt_event_directness": True,
                        "bar_skill_expressibility": True,
                    },
                    "judge_configuration": {
                        "model": "judge-model",
                        "reasoning_effort": "high",
                    },
                    "cross_model_confirmation": {
                        "required": True,
                        "minimum_distinct_runner_models": 3,
                        "minimum_fixture_count_per_model": 6,
                        "minimum_repetitions_per_cell": 2,
                        "require_directional_replication": True,
                    },
                },
            }
        )
        plan["experiment"]["baseline_dependency"] = {
            "schema": BASELINE_RECEIPT_SCHEMA,
            "required": True,
            "receipt_sha256": "sha256:" + "b" * 64,
        }
        cells = build_cells(
            plan,
            pattern_id="evaluation.staged-workflow-section",
            intervention_target="workflow",
            model="fallback-model",
            runner_efforts=[],
            runner_configurations=configurations,
            design="causal_contrast",
            repetitions=2,
            expected_fixtures=6,
            seed=7,
            codex_version="codex-cli-0.144.2",
        )
        control_rows = [
            row for row in plan["task_matrix"] if row["variant_id"] == "original"
        ]
        compatibility = {
            "control_variant": "original",
            "fixture_digests": sorted({row["fixture_digest"] for row in control_rows}),
            "task_evidence_digests": sorted(
                {displayed_content_digest(row["prompt"]) for row in control_rows}
            ),
            "control_attachment_digests": sorted(
                {displayed_content_digest(row["skill_attachment"]) for row in control_rows}
            ),
            "source_digests": [],
            "packet_digests": [],
            "analysis_policy_sha256": _json_sha256(plan["experiment"]["analysis_policy"]),
            "control_thresholds": plan["experiment"]["promotion_thresholds"][
                "controlled_multi_agent_eval"
            ],
            "runner_configurations": plan["experiment"]["campaign_policy"][
                "runner_configurations"
            ],
            "judge_configuration": plan["experiment"]["campaign_policy"][
                "judge_configuration"
            ],
        }
        receipt = {
            "schema": BASELINE_RECEIPT_SCHEMA,
            "evidence_state": "completed",
            "causal_applicable": False,
            "meets_predeclared_floors": True,
            "control_variant": "original",
            "compatibility": compatibility,
            "evidence": {
                field: "sha256:" + "a" * 64
                for field in ("plan_sha256", "manifest_sha256", "traces_sha256", "report_sha256")
            },
            "counts": {
                "fixture_count": 6,
                "fixture_family_count": 6,
                "per_fixture": [],
                "per_runner_model": [],
            },
            "safety": {"raw_status": "clear", "adjudicated_status": "clear"},
            "cost": {"raw_status": "clear", "adjudicated_status": "clear"},
        }
        return plan, cells, receipt

    def test_causal_readiness_requires_a_completed_baseline_receipt(self) -> None:
        plan, cells, receipt = self._causal_plan_with_baseline()
        missing = campaign_readiness_report(
            plan, cells=cells, design="causal_contrast", judge_model="judge-model", judge_effort="high"
        )
        self.assertFalse(missing["ready"])
        self.assertIn("baseline_receipt_required", missing["gaps"])

        held = dict(receipt)
        held["meets_predeclared_floors"] = False
        rejected = campaign_readiness_report(
            plan,
            cells=cells,
            design="causal_contrast",
            judge_model="judge-model",
            judge_effort="high",
            baseline_receipt=held,
            baseline_receipt_digest="sha256:" + "b" * 64,
        )
        self.assertFalse(rejected["ready"])
        self.assertIn("baseline_receipt_floors_not_met", rejected["gaps"])

        ready = campaign_readiness_report(
            plan,
            cells=cells,
            design="causal_contrast",
            judge_model="judge-model",
            judge_effort="high",
            baseline_receipt=receipt,
            baseline_receipt_digest="sha256:" + "b" * 64,
        )
        self.assertTrue(ready["ready"])

    def test_causal_readiness_rejects_baseline_compatibility_drift(self) -> None:
        plan, cells, receipt = self._causal_plan_with_baseline()
        receipt["compatibility"]["fixture_digests"] = ["drifted"]
        readiness = campaign_readiness_report(
            plan,
            cells=cells,
            design="causal_contrast",
            judge_model="judge-model",
            judge_effort="high",
            baseline_receipt=receipt,
            baseline_receipt_digest="sha256:" + "b" * 64,
        )
        self.assertFalse(readiness["ready"])
        self.assertIn("baseline_fixture_digests_mismatch", readiness["gaps"])


if __name__ == "__main__":
    unittest.main()
