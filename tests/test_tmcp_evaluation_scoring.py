from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from typing import Any

import tmcp_runtime.services.evaluation_scoring as evaluation_scoring


class EvaluationScoringServiceTests(unittest.TestCase):
    def _plan(self) -> dict[str, Any]:
        return {
            "schema": "tmcp-skill-evaluation-plan-v0.1",
            "evaluated_skills": [
                {
                    "skill_path": "/project/SKILL.md",
                    "title": "example",
                    "static_findings": [],
                }
            ],
            "task_matrix": [
                {
                    "task_id": "task-1",
                    "variant_id": "original",
                    "skill_path": "/project/SKILL.md",
                    "prompt": "Run the task.",
                    "skill_attachment": "Run pnpm test.",
                }
            ],
            "observable_behavior_contract": [],
            "packet_inclusion_contracts": [
                {
                    "skill_path": "/project/SKILL.md",
                    "expected": {"required_reads": [], "verification_gates": []},
                }
            ],
        }

    def test_score_traces_assembles_dimensions_and_feedback(self) -> None:
        traces = [
            {
                "task_id": "task-1",
                "variant_id": "original",
                "observations": [
                    {
                        "kind": "assistant_message",
                        "value": "Run pnpm test and report pass.",
                    }
                ],
                "outcome": "passed",
            }
        ]

        report = evaluation_scoring.score_traces(
            self._plan(),
            traces,
            anti_pattern_catalog=[],
            effective_patterns=[],
            report_schema="report",
            created_at="now",
        )

        self.assertEqual(report["schema"], "report")
        self.assertEqual(report["scorecard"]["outcome_lift"]["score"], 0.0)
        self.assertIn("No paired", report["scorecard"]["outcome_lift"]["notes"])
        self.assertEqual(
            report["scorecard"]["claim_boundary"]["promotion_source"],
            "pattern_claims",
        )
        self.assertIn(
            "activation",
            report["scorecard"]["claim_boundary"]["diagnostic_only_dimensions"],
        )
        self.assertEqual(report["promotion_policy"]["auto_promote"], False)

    def test_normalize_trace_accepts_legacy_line_observations(self) -> None:
        trace = evaluation_scoring._normalize_trace(
            {
                "task_id": "task-1",
                "variant_id": "original",
                "trace": ["Agent read AGENTS.md", "Ran pnpm test"],
            }
        )

        self.assertEqual(trace["schema"], "tmcp-skill-eval-trace-v0.1")
        self.assertEqual(
            [item["kind"] for item in trace["observations"]],
            ["file_read", "command_run"],
        )

    def test_normalize_trace_rejects_malformed_schema_trace(self) -> None:
        with self.assertRaisesRegex(ValueError, "observations"):
            evaluation_scoring._normalize_trace(
                {
                    "schema": "tmcp-skill-eval-trace-v0.1",
                    "agent": "bad",
                    "observations": ["not an object"],
                }
            )

    def test_score_outcome_rejects_nonnumeric_human_quality(self) -> None:
        with self.assertRaisesRegex(ValueError, "human_quality_score"):
            evaluation_scoring.score_traces(
                self._plan(),
                [
                    {
                        "task_id": "task-1",
                        "variant_id": "original",
                        "observations": [
                            {"kind": "assistant_message", "value": "done"}
                        ],
                        "human_labels": [{"human_quality_score": "bad"}],
                    }
                ],
                anti_pattern_catalog=[],
                effective_patterns=[],
                report_schema="report",
                created_at="now",
            )

    def test_outcome_does_not_trust_verdict_without_judge_evidence(self) -> None:
        score = evaluation_scoring._score_outcome(
            {
                "case_verdict": {"passed": True, "evidence": []},
                "outcome": "failed",
                "human_labels": [],
            }
        )

        self.assertEqual(score["score"], 0.0)
        self.assertEqual(score["confidence"], "low")
        self.assertFalse(score["signals"]["case_verdict_valid"])

    def test_compose_callback_failure_is_not_downgraded_to_trace_fallback(self) -> None:
        def failing_compose(
            row: dict[str, object], project_path: str | None
        ) -> dict[str, object]:
            raise ValueError("compose failed")

        with self.assertRaisesRegex(ValueError, "compose failed"):
            evaluation_scoring.score_traces(
                self._plan(),
                [
                    {
                        "task_id": "task-1",
                        "variant_id": "original",
                        "observations": [
                            {"kind": "assistant_message", "value": "done"}
                        ],
                    }
                ],
                compose_evaluation_row=failing_compose,
                project_path="/project",
                anti_pattern_catalog=[],
                effective_patterns=[],
                report_schema="report",
                created_at="now",
            )

    def test_duplicate_trace_ids_are_rejected(self) -> None:
        traces = [
            {
                "trace_id": "trace-1",
                "task_id": "task-1",
                "variant_id": "original",
                "observations": [{"kind": "assistant_message", "value": "done"}],
            },
            {
                "trace_id": "trace-1",
                "task_id": "task-1",
                "variant_id": "original",
                "observations": [{"kind": "assistant_message", "value": "done"}],
            },
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate evaluation trace_id"):
            evaluation_scoring.score_traces(
                self._plan(),
                traces,
                anti_pattern_catalog=[],
                effective_patterns=[],
                report_schema="report",
                created_at="now",
            )

    def test_correct_baseline_nonactivation_scores_as_success(self) -> None:
        plan = self._plan()
        plan["task_matrix"] = [
            {
                "task_id": "task-1",
                "variant_id": "baseline",
                "skill_path": "/project/SKILL.md",
                "prompt": "Run the task.",
                "skill_attachment": "",
            }
        ]

        report = evaluation_scoring.score_traces(
            plan,
            [
                {
                    "task_id": "task-1",
                    "variant_id": "baseline",
                    "observations": [
                        {"kind": "assistant_message", "value": "Completed task."}
                    ],
                }
            ],
            anti_pattern_catalog=[],
            effective_patterns=[],
            report_schema="report",
            created_at="now",
        )

        activation = report["activation_scores"][0]
        self.assertEqual(activation["score"], 1.0)
        self.assertFalse(activation["signals"]["skill_selected"])
        self.assertFalse(activation["signals"]["skill_should_be_selected"])

    def test_direct_attachment_baseline_reports_reliability_not_causal_lift(
        self,
    ) -> None:
        plan = self._plan()
        plan["experiment"] = {
            "experiment_id": "experiment-1",
            "campaign_policy": {
                "schema": "tmcp-skill-eval-campaign-policy-v0.1",
                "design": "baseline_reliability",
                "runner_configurations": [
                    {"model": "runner-model", "reasoning_effort": "high"}
                ],
                "baseline_reliability": {
                    "control_variant": "original",
                    "minimum_control_pass_rate": 0.5,
                    "minimum_per_fixture_control_pass_rate": 0.5,
                    "require_predeclared_clustered_interval": True,
                },
            },
        }
        plan["task_matrix"][0].update(
            {
                "matrix_row_id": "row-1",
                "fixture_digest": "fixture-1",
                "fixture_family": "family-1",
            }
        )
        trace = {
            "trace_id": "trace-1",
            "experiment_id": "experiment-1",
            "matrix_row_id": "row-1",
            "replicate_id": "replicate-1",
            "task_id": "task-1",
            "variant_id": "original",
            "agent": {
                "name": "codex-cli-blind-runner",
                "model": "runner-model",
                "configuration_id": "runner-model-high",
            },
            "provenance": {
                "runner_blinded": True,
                "judge_blinded": True,
                "isolated_session": True,
                "instruction_delivery": "direct_attachment",
            },
            "campaign": {"runner_artifact": "cells/row-1/runner.txt"},
            "observations": [{"kind": "assistant_message", "value": "artifact"}],
            "case_verdict": {
                "passed": True,
                "evidence": ["judge verdict"],
                "safety_regression": False,
                "cost_regression": False,
            },
        }

        report = evaluation_scoring.score_traces(
            plan,
            [trace],
            anti_pattern_catalog=[],
            effective_patterns=[],
            report_schema="report",
            created_at="now",
            cost_rejudgments={"trace-1": True},
        )

        self.assertEqual(report["study_design"], "baseline_reliability")
        self.assertEqual(report["baseline_reliability"]["pass_rate"], 1.0)
        self.assertEqual(
            report["baseline_reliability"]["adjudicated_cost_regressions"], 1
        )
        self.assertEqual(report["pattern_claims"], [])
        self.assertIsNone(report["scorecard"]["outcome_lift"]["score"])
        self.assertIsNone(report["scorecard"]["activation"]["score"])
        self.assertIsNone(report["scorecard"]["adherence"]["score"])
        self.assertEqual(report["scorecard"]["cost"]["score"], 0.0)
        self.assertEqual(
            report["scorecard"]["cost"]["source"],
            "condition_blind_cost_rejudgment",
        )

    def test_bound_legacy_trace_cannot_gain_controlled_provenance(self) -> None:
        plan = self._plan()
        common = {
            "fixture_family": "family-a",
            "fixture_digest": "fixture-a",
            "pattern_id": "verification.concrete-command",
            "contrast_id": "contrast-a",
            "intervention_variant": "original",
            "control_variant": "baseline",
            "expected_effect_direction": "positive",
            "skill_digest": "skill-a",
            "intervention": {"causal_attribution": True},
        }
        plan["experiment"] = {"experiment_id": "experiment-a"}
        plan["task_matrix"] = [
            {
                **common,
                "matrix_row_id": "row-original",
                "task_id": "task-1",
                "variant_id": "original",
                "skill_path": "/project/SKILL.md",
                "skill_attachment": "Run pnpm test.",
            },
            {
                **common,
                "matrix_row_id": "row-baseline",
                "task_id": "task-1",
                "variant_id": "baseline",
                "skill_path": "/project/SKILL.md",
                "skill_attachment": "",
            },
        ]
        traces = [
            {
                "task_id": "task-1",
                "variant_id": variant,
                "agent": {"configuration_id": "config-a"},
                "provenance": {
                    "runner_blinded": True,
                    "judge_blinded": True,
                    "isolated_session": True,
                },
                "observations": [{"kind": "assistant_message", "value": "artifact"}],
                "case_verdict": {
                    "passed": variant == "original",
                    "evidence": ["judge verdict"],
                },
            }
            for variant in ("original", "baseline")
        ]

        report = evaluation_scoring.score_traces(
            plan,
            traces,
            anti_pattern_catalog=[],
            effective_patterns=[],
            report_schema="report",
            created_at="now",
        )

        claim = report["pattern_claims"][0]
        self.assertEqual(claim["controlled_summary"]["trace_count"], 0)
        reasons = {item["reason"] for item in claim["controlled_exclusion_reasons"]}
        self.assertIn("matrix_row_id is missing", reasons)
        self.assertIn("experiment_id is missing", reasons)

    def test_service_has_no_filesystem_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(evaluation_scoring))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden_prefixes = (
            "datetime",
            "os",
            "pathlib",
            "scripts",
            "shutil",
            "subprocess",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
            "uuid",
        )
        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in imported_modules
                for prefix in forbidden_prefixes
            )
        )


if __name__ == "__main__":
    unittest.main()
