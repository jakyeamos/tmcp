from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from typing import Any

import tmcp_runtime.services.evaluation_evidence as evaluation_evidence
import tmcp_runtime.services.evaluation_guidebook as evaluation_guidebook
import tmcp_runtime.services.evaluation_plan as evaluation_plan


PATTERN_ID = "structure.explicit-verification-section"
TESTED_ATOM = "verification_section"
INTERVENTION_TARGET = "verification"


class EvaluationEvidenceServiceTests(unittest.TestCase):
    def _plan(
        self,
        *,
        fixture_count: int = 2,
        causal: bool = True,
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for fixture_index in range(fixture_count):
            for variant in ("original", "ablated"):
                rows.append(
                    {
                        "experiment_id": "experiment-1",
                        "matrix_row_id": f"row-{fixture_index}-{variant}",
                        "task_id": f"task-{fixture_index}",
                        "fixture_family": f"family-{fixture_index % 3}",
                        "fixture_digest": f"fixture-{fixture_index}",
                        "skill_digest": "skill-1",
                        "contrast_id": f"contrast-{fixture_index}",
                        "pattern_id": PATTERN_ID,
                        "intervention_variant": "ablated",
                        "control_variant": "original",
                        "intervention_target": INTERVENTION_TARGET,
                        "tested_atom": TESTED_ATOM,
                        "pattern_intervention_contract": {
                            "tested_atom": TESTED_ATOM,
                            "allowed_targets": [INTERVENTION_TARGET],
                            "allowed_kinds": ["single_section_ablation"],
                            "claim_granularity": "section",
                            "expected_support_direction": "negative",
                        },
                        "claim_granularity": "section",
                        "expected_effect_direction": "negative",
                        "variant_id": variant,
                        "ablation_section": (
                            INTERVENTION_TARGET if variant == "ablated" else None
                        ),
                        "skill_path": "/project/SKILL.md",
                        "expected_observables": ["reports the concrete command result"],
                        "failure_smells": ["claims success without a command result"],
                        "intervention": {
                            "kind": (
                                "single_section_ablation"
                                if variant == "ablated"
                                else "full_skill"
                            ),
                            "causal_attribution": (
                                causal if variant == "ablated" else False
                            ),
                            "target": (
                                INTERVENTION_TARGET if variant == "ablated" else None
                            ),
                        },
                    }
                )
        return {
            "experiment": {
                "experiment_id": "experiment-1",
                "promotion_thresholds": evaluation_evidence.DEFAULT_THRESHOLDS,
            },
            "task_matrix": rows,
        }

    def _traces(
        self,
        plan: dict[str, Any],
        *,
        configurations: tuple[str, ...] = ("config-a",),
        repetitions: int = 2,
        blinded: bool = True,
        include_regressions: bool = True,
    ) -> list[dict[str, Any]]:
        traces: list[dict[str, Any]] = []
        for row in plan["task_matrix"]:
            for configuration in configurations:
                for replicate in range(repetitions):
                    variant = str(row["variant_id"])
                    verdict: dict[str, Any] = {
                        "passed": variant == "original",
                        "evidence": ["blind judge case verdict"],
                    }
                    if include_regressions:
                        verdict.update(
                            {"safety_regression": False, "cost_regression": False}
                        )
                    traces.append(
                        {
                            "trace_id": (
                                f"trace-{row['matrix_row_id']}-{configuration}-{replicate}"
                            ),
                            "experiment_id": "experiment-1",
                            "matrix_row_id": row["matrix_row_id"],
                            "replicate_id": f"replicate-{replicate}",
                            "task_id": row["task_id"],
                            "variant_id": variant,
                            "agent": {
                                "name": "runner",
                                "model": "model",
                                "configuration_id": configuration,
                            },
                            "provenance": {
                                "runner_blinded": blinded,
                                "judge_blinded": blinded,
                                "isolated_session": blinded,
                            },
                            "observations": [
                                {"kind": "assistant_message", "value": "artifact"}
                            ],
                            "case_verdict": verdict,
                        }
                    )
        return traces

    def test_controlled_single_requires_paired_repetitions_and_blinding(self) -> None:
        plan = self._plan()
        claim = evaluation_evidence.analyze_pattern_evidence(plan, self._traces(plan))[
            0
        ]

        self.assertEqual(claim["evidence_level"], "controlled_single_agent_eval")
        self.assertEqual(claim["controlled_summary"]["absolute_lift"], -1.0)
        self.assertEqual(claim["claim_granularity"], "section")
        self.assertFalse(claim["promotion_eligible"])
        self.assertIn("fixture_count 2 is below required 6", claim["promotion_gaps"])

    def test_unblinded_named_agents_do_not_launder_controlled_evidence(self) -> None:
        plan = self._plan()
        claim = evaluation_evidence.analyze_pattern_evidence(
            plan, self._traces(plan, blinded=False)
        )[0]

        self.assertEqual(claim["evidence_level"], "dogfooded")
        self.assertEqual(claim["controlled_summary"]["trace_count"], 0)
        reasons = {item["reason"] for item in claim["controlled_exclusion_reasons"]}
        self.assertIn("provenance.runner_blinded must be true", reasons)

    def test_unpaired_or_noncausal_results_remain_static(self) -> None:
        plan = self._plan(causal=False)
        traces = [
            trace for trace in self._traces(plan) if trace["variant_id"] == "ablated"
        ]
        claim = evaluation_evidence.analyze_pattern_evidence(plan, traces)[0]

        self.assertEqual(claim["evidence_level"], "hypothesis")
        self.assertIsNone(claim["observed_summary"]["absolute_lift"])
        self.assertFalse(claim["causal_contrast_valid"])

    def test_multi_agent_gate_requires_full_72_run_design(self) -> None:
        plan = self._plan(fixture_count=6)
        traces = self._traces(
            plan,
            configurations=("config-a", "config-b", "config-c"),
        )
        self.assertEqual(len(traces), 72)

        claim = evaluation_evidence.analyze_pattern_evidence(plan, traces)[0]

        self.assertEqual(claim["evidence_level"], "controlled_multi_agent_eval")
        self.assertEqual(claim["promotion_decision"], "eligible_for_manual_review")
        self.assertTrue(claim["promotion_eligible"])
        self.assertEqual(claim["promotion_gaps"], [])

    def test_multi_agent_promotion_requires_interval_to_clear_zero(self) -> None:
        plan = self._plan(fixture_count=6)
        traces = self._traces(
            plan,
            configurations=("config-a", "config-b", "config-c"),
        )
        ablated = [trace for trace in traces if trace["variant_id"] == "ablated"]
        for trace in ablated[:32]:
            trace["case_verdict"]["passed"] = True

        claim = evaluation_evidence.analyze_pattern_evidence(plan, traces)[0]

        self.assertEqual(claim["evidence_level"], "controlled_multi_agent_eval")
        self.assertFalse(claim["promotion_eligible"])
        self.assertTrue(
            any("interval lower bound" in gap for gap in claim["promotion_gaps"])
        )

    def test_multi_agent_promotion_rejects_configuration_reversal(self) -> None:
        plan = self._plan(fixture_count=6)
        traces = self._traces(
            plan,
            configurations=("config-a", "config-b", "config-c"),
        )
        for trace in traces:
            if trace["agent"]["configuration_id"] == "config-c":
                trace["case_verdict"]["passed"] = trace["variant_id"] == "ablated"

        claim = evaluation_evidence.analyze_pattern_evidence(plan, traces)[0]

        self.assertEqual(claim["evidence_level"], "controlled_multi_agent_eval")
        self.assertFalse(claim["promotion_eligible"])
        self.assertIn(
            "agent-configuration effect reversal detected: config-c",
            claim["promotion_gaps"],
        )

    def test_duplicate_controlled_cell_is_rejected(self) -> None:
        plan = self._plan()
        traces = self._traces(plan)

        with self.assertRaisesRegex(ValueError, "Duplicate controlled evaluation cell"):
            evaluation_evidence.analyze_pattern_evidence(plan, [*traces, traces[0]])

    def test_static_findings_are_candidates_not_recommendations(self) -> None:
        entries = evaluation_guidebook.guidebook_entries(
            static_findings=[
                {
                    "pattern_id": PATTERN_ID,
                    "classification": "effective_pattern",
                    "skill_path": "/project/SKILL.md",
                }
            ],
            claims=[],
            effective_patterns=[
                {
                    "pattern_id": PATTERN_ID,
                    "label": "Concrete command",
                    "classification": "effective_pattern",
                    "internal_atoms": ["behavior-verification"],
                    "good_example": "Run `pnpm test` and report pass/fail.",
                    "weak_example": "Make sure it works.",
                }
            ],
            anti_pattern_catalog=[],
        )

        self.assertEqual(entries[0]["status"], "candidate")
        self.assertEqual(entries[0]["evidence_level"], "static_review")
        self.assertFalse(entries[0]["promotion"]["eligible"])

    def test_case_scores_preserve_fixture_oracles(self) -> None:
        plan = self._plan()
        score = evaluation_evidence.case_scores(plan, self._traces(plan))[0]

        self.assertEqual(
            score["expected_observables"], ["reports the concrete command result"]
        )
        self.assertTrue(score["judge_evidence_valid"])
        self.assertTrue(score["controlled_provenance_valid"])

    def test_ablation_contrast_does_not_pool_other_section_rows(self) -> None:
        plan = self._plan(fixture_count=1)
        intervention = next(
            row for row in plan["task_matrix"] if row["variant_id"] == "ablated"
        )
        unrelated = {
            **intervention,
            "matrix_row_id": "row-ablate-output",
            "ablation_section": "output",
        }
        plan["task_matrix"].append(unrelated)
        traces = self._traces(plan, repetitions=1)

        claim = evaluation_evidence.analyze_pattern_evidence(plan, traces)[0]

        self.assertEqual(claim["observed_summary"]["intervention"]["total"], 1)
        self.assertEqual(claim["observed_summary"]["minimum_repetitions_per_cell"], 1)

    def test_ablation_against_empty_baseline_is_not_a_causal_contrast(self) -> None:
        plan = self._plan(fixture_count=1)
        original = next(
            row for row in plan["task_matrix"] if row["variant_id"] == "original"
        )
        original["variant_id"] = "baseline"
        for row in plan["task_matrix"]:
            row["control_variant"] = "baseline"

        claim = evaluation_evidence.analyze_pattern_evidence(
            plan, self._traces(plan, repetitions=1)
        )[0]

        self.assertFalse(claim["causal_contrast_valid"])
        self.assertEqual(claim["evidence_level"], "hypothesis")

    def test_fixture_coverage_counts_unique_digests_not_task_rows(self) -> None:
        plan = self._plan(fixture_count=2)
        for row in plan["task_matrix"]:
            row["fixture_digest"] = "same-fixture"

        claim = evaluation_evidence.analyze_pattern_evidence(plan, self._traces(plan))[
            0
        ]

        self.assertEqual(claim["controlled_summary"]["fixture_count"], 1)
        self.assertEqual(claim["evidence_level"], "hypothesis")

    def test_verdict_without_evidence_does_not_count_as_dogfood(self) -> None:
        plan = self._plan()
        traces = self._traces(plan)
        for trace in traces:
            trace["case_verdict"]["evidence"] = []

        claim = evaluation_evidence.analyze_pattern_evidence(plan, traces)[0]

        self.assertEqual(claim["observed_summary"]["trace_count"], 0)
        self.assertEqual(claim["evidence_level"], "hypothesis")

    def test_aggregate_lift_aligns_negative_expected_effects(self) -> None:
        result = evaluation_evidence.aggregate_lift(
            [
                {
                    "evidence_level": "controlled_single_agent_eval",
                    "expected_effect_direction": "positive",
                    "controlled_summary": {"absolute_lift": 1.0},
                },
                {
                    "evidence_level": "controlled_single_agent_eval",
                    "expected_effect_direction": "negative",
                    "controlled_summary": {"absolute_lift": -1.0},
                },
            ]
        )

        self.assertEqual(result["score"], 1.0)

    def test_plan_cannot_lower_conservative_promotion_floors(self) -> None:
        plan = self._plan()
        plan["experiment"]["promotion_thresholds"] = {
            level: {key: 0 for key in values}
            for level, values in evaluation_evidence.DEFAULT_THRESHOLDS.items()
        }

        claim = evaluation_evidence.analyze_pattern_evidence(plan, self._traces(plan))[
            0
        ]

        self.assertEqual(claim["evidence_level"], "controlled_single_agent_eval")
        self.assertFalse(claim["promotion_eligible"])

    def test_dogfooded_guidebook_entry_uses_observed_sample(self) -> None:
        entries = evaluation_guidebook.guidebook_entries(
            static_findings=[],
            claims=[
                {
                    "pattern_id": PATTERN_ID,
                    "evidence_level": "dogfooded",
                    "expected_effect_direction": "negative",
                    "observed_summary": {"trace_count": 4, "absolute_lift": -0.5},
                    "controlled_summary": {"trace_count": 0, "absolute_lift": None},
                    "promotion_eligible": False,
                    "promotion_decision": "hold",
                    "promotion_gaps": ["more evidence required"],
                }
            ],
            effective_patterns=[
                {
                    "pattern_id": PATTERN_ID,
                    "label": "Explicit verification section",
                    "classification": "effective_pattern",
                    "good_example": "Use an explicit Verification section.",
                    "weak_example": "Scatter verification hints.",
                }
            ],
            anti_pattern_catalog=[],
        )

        self.assertEqual(entries[0]["status"], "supported")
        self.assertEqual(entries[0]["sample"]["trace_count"], 4)

    def test_unrun_tagged_fixture_is_only_a_hypothesis(self) -> None:
        claim = evaluation_evidence.analyze_pattern_evidence(self._plan(), [])[0]

        self.assertEqual(claim["evidence_level"], "hypothesis")

    def test_same_intervention_and_control_cannot_form_a_causal_claim(self) -> None:
        plan = self._plan()
        for row in plan["task_matrix"]:
            row["control_variant"] = "ablated"

        claim = evaluation_evidence.analyze_pattern_evidence(plan, self._traces(plan))[
            0
        ]

        self.assertFalse(claim["causal_contrast_valid"])
        self.assertEqual(claim["evidence_level"], "hypothesis")

    def test_scaffolded_slice_vs_baseline_cannot_earn_empirical_tier(self) -> None:
        fixtures = [
            {
                "id": f"task-{index}",
                "fixture_family": "verification",
                "pattern_id": PATTERN_ID,
                "intervention_variant": "verification-only",
                "control_variant": "baseline",
                "intervention_target": "verification_gates",
                "tested_atom": "verification_gates",
                "expected_observables": [],
            }
            for index in range(2)
        ]
        with self.assertRaisesRegex(ValueError, "intervention kind"):
            evaluation_plan.build_evaluation_plan_from_sources(
                [
                    evaluation_plan.EvaluationSource(
                        "/project/SKILL.md",
                        "---\nname: example\n---\n\n## Verification\nRun `pnpm test`.\n",
                    )
                ],
                fixtures,
                ["baseline", "verification-only"],
                anti_patterns=[],
                effective_patterns=[
                    {
                        "pattern_id": PATTERN_ID,
                        "tested_interventions": [
                            {
                                "tested_atom": "verification_gates",
                                "allowed_targets": ["verification_gates"],
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
        source_path = Path(inspect.getfile(evaluation_evidence))
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
