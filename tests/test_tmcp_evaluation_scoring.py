from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.evaluation_scoring as evaluation_scoring


class EvaluationScoringServiceTests(unittest.TestCase):
    def _plan(self) -> dict[str, object]:
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
        self.assertEqual(report["scorecard"]["outcome_lift"]["score"], 1.0)
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
