from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.evaluation_plan as evaluation_plan


class EvaluationPlanServiceTests(unittest.TestCase):
    def test_builds_plan_from_safe_sources_without_filesystem_access(self) -> None:
        plan = evaluation_plan.build_evaluation_plan_from_sources(
            [
                evaluation_plan.EvaluationSource(
                    display_path="skills/example/SKILL.md",
                    text=(
                        "---\nname: example\n---\n\n"
                        "## Required reads\nRead AGENTS.md first.\n\n"
                        "## Verification\nRun `pnpm test`.\n"
                    ),
                )
            ],
            [{"id": "task-1", "prompt": "Run the task.", "expected_observables": []}],
            ["original", "negative_control"],
            anti_patterns=[],
            effective_patterns=[],
            created_at="now",
            max_matrix_rows=10,
        )

        self.assertEqual(plan["schema"], "tmcp-skill-evaluation-plan-v0.2")
        self.assertEqual(plan["created_at"], "now")
        self.assertEqual(len(plan["task_matrix"]), 2)
        self.assertEqual(plan["variants"], ["negative_control", "original"])
        self.assertEqual(plan["evaluated_skills"][0]["title"], "example")
        self.assertEqual(
            plan["experiment"]["protocol_version"],
            "tmcp-skill-evaluation-protocol-v0.2",
        )
        self.assertEqual(
            plan["experiment"]["analysis_policy"]["clustered_interval"]["method"],
            "fixture_block_bootstrap_by_configuration",
        )
        self.assertEqual(
            plan["experiment"]["promotion_thresholds"]["controlled_multi_agent_eval"][
                "minimum_per_fixture_control_pass_rate"
            ],
            0.5,
        )
        row_ids = [row["matrix_row_id"] for row in plan["task_matrix"]]
        self.assertEqual(len(row_ids), len(set(row_ids)))
        original = next(
            row for row in plan["task_matrix"] if row["variant_id"] == "original"
        )
        self.assertEqual(original["experiment_id"], plan["experiment"]["experiment_id"])
        self.assertIn(
            "AGENTS.md", original["expected_packet_contract"]["required_reads"]
        )

    def test_ablation_rows_have_unique_identifiers(self) -> None:
        plan = evaluation_plan.build_evaluation_plan_from_sources(
            [
                evaluation_plan.EvaluationSource(
                    "SKILL.md",
                    "# Skill\n\n## Verification\nRun one.\n\n## Output\nReport it.\n",
                )
            ],
            [{"id": "task-1", "expected_observables": []}],
            ["ablated"],
            anti_patterns=[],
            effective_patterns=[],
            created_at="now",
            max_matrix_rows=10,
        )

        rows = plan["task_matrix"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({row["matrix_row_id"] for row in rows}), 3)
        self.assertEqual(
            {row["ablation_section"] for row in rows},
            {"preamble", "verification", "output"},
        )

    def test_campaign_policy_is_normalized_and_bound_to_experiment_identity(
        self,
    ) -> None:
        source = [evaluation_plan.EvaluationSource("SKILL.md", "# Skill\n")]
        fixtures = [{"id": "task-1", "expected_observables": []}]
        policy = {
            "schema": "tmcp-skill-eval-campaign-policy-v0.1",
            "design": "baseline_reliability",
            "runner_configurations": [
                {"model": "model-b", "reasoning_effort": "high"},
                {"model": "model-a", "reasoning_effort": "low"},
                {"model": "model-a", "reasoning_effort": "high"},
            ],
            "baseline_reliability": {
                "control_variant": "original",
                "minimum_control_pass_rate": 0.5,
                "minimum_per_fixture_control_pass_rate": 0.5,
                "require_predeclared_clustered_interval": True,
            },
            "judge_configuration": {"model": "judge-model", "reasoning_effort": "high"},
            "cross_model_confirmation": {
                "required": True,
                "minimum_distinct_runner_models": 2,
                "minimum_fixture_count_per_model": 1,
                "minimum_repetitions_per_cell": 2,
                "require_directional_replication": True,
            },
        }
        with_policy = evaluation_plan.build_evaluation_plan_from_sources(
            source,
            fixtures,
            ["original"],
            anti_patterns=[],
            effective_patterns=[],
            created_at="now",
            max_matrix_rows=10,
            campaign_policy=policy,
        )
        without_policy = evaluation_plan.build_evaluation_plan_from_sources(
            source,
            fixtures,
            ["original"],
            anti_patterns=[],
            effective_patterns=[],
            created_at="now",
            max_matrix_rows=10,
        )

        self.assertEqual(
            [
                item["model"]
                for item in with_policy["experiment"]["campaign_policy"][
                    "runner_configurations"
                ]
            ],
            ["model-a", "model-a", "model-b"],
        )
        self.assertNotEqual(
            with_policy["experiment"]["experiment_id"],
            without_policy["experiment"]["experiment_id"],
        )

    def test_rejects_matrix_budget_before_rows_are_appended(self) -> None:
        with self.assertRaisesRegex(ValueError, "matrix"):
            evaluation_plan.build_evaluation_plan_from_sources(
                [evaluation_plan.EvaluationSource("SKILL.md", "# Skill\n")],
                [{"id": "task-1", "expected_observables": []}],
                ["original"],
                anti_patterns=[],
                effective_patterns=[],
                created_at="now",
                max_matrix_rows=0,
            )

    def test_identical_skill_content_at_distinct_paths_has_distinct_rows(self) -> None:
        skill_text = "# Skill\n\n## Verification\nRun `pnpm test`.\n"

        plan = evaluation_plan.build_evaluation_plan_from_sources(
            [
                evaluation_plan.EvaluationSource("skills/a/SKILL.md", skill_text),
                evaluation_plan.EvaluationSource("skills/b/SKILL.md", skill_text),
            ],
            [{"id": "task-1", "expected_observables": []}],
            ["original"],
            anti_patterns=[],
            effective_patterns=[],
            created_at="now",
            max_matrix_rows=10,
        )

        rows = plan["task_matrix"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row["matrix_row_id"] for row in rows}), 2)

    def test_pattern_ablation_requires_one_named_intervention_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "intervention_target"):
            evaluation_plan.build_evaluation_plan_from_sources(
                [evaluation_plan.EvaluationSource("SKILL.md", "# Skill\n")],
                [
                    {
                        "id": "task-1",
                        "pattern_id": "pattern-1",
                        "intervention_variant": "ablated",
                        "control_variant": "baseline",
                        "expected_observables": [],
                    }
                ],
                ["ablated", "baseline"],
                anti_patterns=[],
                effective_patterns=[
                    {
                        "pattern_id": "pattern-1",
                        "tested_interventions": [
                            {
                                "tested_atom": "verification_gates",
                                "allowed_targets": ["verification"],
                                "allowed_kinds": ["single_section_ablation"],
                                "claim_granularity": "section",
                                "expected_support_direction": "negative",
                            }
                        ],
                    }
                ],
                created_at="now",
                max_matrix_rows=10,
            )

    def test_scaffolded_slice_vs_empty_baseline_is_not_a_pattern_contrast(self) -> None:
        with self.assertRaisesRegex(ValueError, "intervention kind"):
            evaluation_plan.build_evaluation_plan_from_sources(
                [
                    evaluation_plan.EvaluationSource(
                        "SKILL.md",
                        "---\nname: example\n---\n\n## Verification\nRun `pnpm test`.\n",
                    )
                ],
                [
                    {
                        "id": "task-1",
                        "pattern_id": "structure.explicit-verification-section",
                        "tested_atom": "verification_section",
                        "intervention_variant": "verification-only",
                        "control_variant": "baseline",
                        "intervention_target": "verification",
                        "expected_observables": [],
                    }
                ],
                ["verification-only", "baseline"],
                anti_patterns=[],
                effective_patterns=[
                    {
                        "pattern_id": "structure.explicit-verification-section",
                        "tested_interventions": [
                            {
                                "tested_atom": "verification_section",
                                "allowed_targets": ["verification"],
                                "allowed_kinds": ["single_section_ablation"],
                                "claim_granularity": "section",
                                "expected_support_direction": "negative",
                            }
                        ],
                    }
                ],
                created_at="now",
                max_matrix_rows=10,
            )

    def test_pattern_rejects_mislabeled_or_unmatched_interventions(self) -> None:
        source = evaluation_plan.EvaluationSource(
            "SKILL.md",
            "---\nname: example\n---\n\n## Verification\nRun `pnpm test`.\n",
        )
        pattern = {
            "pattern_id": "structure.explicit-verification-section",
            "tested_interventions": [
                {
                    "tested_atom": "verification_section",
                    "allowed_targets": ["verification"],
                    "allowed_kinds": ["single_section_ablation"],
                    "claim_granularity": "section",
                    "expected_support_direction": "negative",
                }
            ],
        }
        base_fixture = {
            "id": "task-1",
            "pattern_id": "structure.explicit-verification-section",
            "tested_atom": "verification_section",
            "control_variant": "baseline",
            "intervention_target": "verification",
            "expected_observables": [],
        }

        with self.assertRaisesRegex(ValueError, "intervention kind"):
            evaluation_plan.build_evaluation_plan_from_sources(
                [source],
                [{**base_fixture, "intervention_variant": "trigger-only"}],
                ["trigger-only", "baseline"],
                anti_patterns=[],
                effective_patterns=[pattern],
                created_at="now",
                max_matrix_rows=10,
            )
        with self.assertRaisesRegex(ValueError, "control-kind"):
            evaluation_plan.build_evaluation_plan_from_sources(
                [source],
                [{**base_fixture, "intervention_variant": "negative_control"}],
                ["negative_control", "baseline"],
                anti_patterns=[],
                effective_patterns=[pattern],
                created_at="now",
                max_matrix_rows=10,
            )

    def test_section_ablation_requires_original_matched_control(self) -> None:
        with self.assertRaisesRegex(ValueError, "matched control"):
            evaluation_plan.build_evaluation_plan_from_sources(
                [
                    evaluation_plan.EvaluationSource(
                        "SKILL.md",
                        "# Example\n\n## Verification\nRun `pnpm test`.\n",
                    )
                ],
                [
                    {
                        "id": "task-1",
                        "pattern_id": "structure.explicit-verification-section",
                        "tested_atom": "verification_section",
                        "intervention_variant": "ablated",
                        "control_variant": "baseline",
                        "intervention_target": "verification",
                        "expected_observables": [],
                    }
                ],
                ["ablated", "baseline"],
                anti_patterns=[],
                effective_patterns=[
                    {
                        "pattern_id": "structure.explicit-verification-section",
                        "tested_interventions": [
                            {
                                "tested_atom": "verification_section",
                                "allowed_targets": ["verification"],
                                "allowed_kinds": ["single_section_ablation"],
                                "claim_granularity": "section",
                                "expected_support_direction": "negative",
                            }
                        ],
                    }
                ],
                created_at="now",
                max_matrix_rows=10,
            )

    def test_section_pattern_keeps_semantic_atom_distinct_from_section_slug(
        self,
    ) -> None:
        plan = evaluation_plan.build_evaluation_plan_from_sources(
            [
                evaluation_plan.EvaluationSource(
                    "SKILL.md",
                    "# Example\n\n## Verification\nRun `pnpm test`.\n",
                )
            ],
            [
                {
                    "id": "task-1",
                    "pattern_id": "structure.explicit-verification-section",
                    "tested_atom": "verification_section",
                    "intervention_variant": "ablated",
                    "control_variant": "original",
                    "intervention_target": "verification",
                    "expected_observables": [],
                }
            ],
            ["original", "ablated"],
            anti_patterns=[],
            effective_patterns=[
                {
                    "pattern_id": "structure.explicit-verification-section",
                    "tested_interventions": [
                        {
                            "tested_atom": "verification_section",
                            "allowed_targets": ["verification"],
                            "allowed_kinds": ["single_section_ablation"],
                            "claim_granularity": "section",
                            "expected_support_direction": "negative",
                        }
                    ],
                }
            ],
            created_at="now",
            max_matrix_rows=10,
        )

        row = next(
            item
            for item in plan["task_matrix"]
            if item["variant_id"] == "ablated"
            and item["ablation_section"] == "verification"
        )
        self.assertEqual(row["tested_atom"], "verification_section")
        self.assertEqual(row["intervention_target"], "verification")
        self.assertEqual(row["expected_effect_direction"], "negative")
        self.assertEqual(row["claim_granularity"], "section")

    def test_non_lossless_ablation_is_rejected_before_plan_emission(self) -> None:
        with self.assertRaisesRegex(ValueError, "lossless causal contrast"):
            evaluation_plan.build_evaluation_plan_from_sources(
                [
                    evaluation_plan.EvaluationSource(
                        "SKILL.md",
                        "---\nname: malformed\n\n## Verification\nRun `pnpm test`.\n",
                    )
                ],
                [
                    {
                        "id": "task-1",
                        "pattern_id": "structure.explicit-verification-section",
                        "tested_atom": "verification_section",
                        "intervention_variant": "ablated",
                        "control_variant": "original",
                        "intervention_target": "verification",
                        "expected_observables": [],
                    }
                ],
                ["original", "ablated"],
                anti_patterns=[],
                effective_patterns=[
                    {
                        "pattern_id": "structure.explicit-verification-section",
                        "tested_interventions": [
                            {
                                "tested_atom": "verification_section",
                                "allowed_targets": ["verification"],
                                "allowed_kinds": ["single_section_ablation"],
                                "claim_granularity": "section",
                                "expected_support_direction": "negative",
                            }
                        ],
                    }
                ],
                created_at="now",
                max_matrix_rows=10,
            )

    def test_service_has_no_filesystem_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(evaluation_plan))
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
