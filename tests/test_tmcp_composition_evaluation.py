from __future__ import annotations

import ast
import copy
import inspect
import unittest
from pathlib import Path
from typing import Any

from tmcp_runtime.api.evaluation import evaluate_skills
from tmcp_runtime.domain.composition_benchmark_receipt_projection import (
    build_benchmark_receipt_provenance,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
import tmcp_runtime.services.composition_evaluation as composition_evaluation
from tmcp_runtime.services.composition_evaluation import (
    assess_project_recipe_promotion,
    build_composition_evaluation_variants,
    score_composition_results,
)


class CompositionEvaluationTests(unittest.TestCase):
    def _results(self) -> list[dict[str, Any]]:
        return [
            {"variant_id": "baseline", "quality_score": 0.20},
            {
                "variant_id": "naive_union",
                "quality_score": 0.55,
                "context_tokens": 1000,
            },
            {"variant_id": "singleton:research", "quality_score": 0.60},
            {"variant_id": "singleton:writing", "quality_score": 0.65},
            {"variant_id": "singleton:review", "quality_score": 0.62},
            {
                "variant_id": "full_composition",
                "quality_score": 0.80,
                "context_tokens": 700,
            },
            {"variant_id": "leave_one_out:research", "quality_score": 0.72},
            {"variant_id": "leave_one_out:writing", "quality_score": 0.70},
            {"variant_id": "leave_one_out:review", "quality_score": 0.74},
            {"variant_id": "wrong_order", "quality_score": 0.70},
        ]

    def test_builds_complete_deterministic_composition_matrix(self) -> None:
        skill_ids = ["research", "writing", "review"]
        original = list(skill_ids)

        variants = build_composition_evaluation_variants(skill_ids)

        self.assertEqual(skill_ids, original)
        self.assertEqual(
            [item["variant_id"] for item in variants],
            [
                "baseline",
                "naive_union",
                "singleton:research",
                "singleton:writing",
                "singleton:review",
                "full_composition",
                "leave_one_out:research",
                "leave_one_out:writing",
                "leave_one_out:review",
                "wrong_order",
            ],
        )
        self.assertEqual(variants[0]["variant_kind"], "no_skill")
        self.assertEqual(variants[0]["selected_skill_ids"], [])
        self.assertFalse(variants[1]["composition_enabled"])
        self.assertTrue(variants[5]["composition_enabled"])
        self.assertEqual(
            variants[-1]["ordered_skill_ids"], ["review", "writing", "research"]
        )

    def test_variant_matrix_rejects_ambiguous_skill_sets(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            build_composition_evaluation_variants(["research"])
        with self.assertRaisesRegex(ValueError, "must be unique"):
            build_composition_evaluation_variants(["research", "research"])

    def test_public_evaluator_routes_composition_plan_and_score_modes(self) -> None:
        plan = evaluate_skills(
            {
                "mode": "composition-plan",
                "composition_skill_ids": ["research", "writing", "review"],
            }
        )

        self.assertEqual(plan["schema"], "tmcp-composition-evaluation-plan-v0.1")
        self.assertEqual(plan["variants"][-1]["variant_id"], "wrong_order")

        summary = evaluate_skills(
            {
                "mode": "composition-score",
                "composition_results": self._results(),
            }
        )

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["schema"], "tmcp-composition-evaluation-summary-v0.1")
        self.assertEqual(summary["quality_metrics"]["synergy_lift"], 0.15)

    def test_scores_normalized_lifts_and_context_ratio(self) -> None:
        results = self._results()
        original = copy.deepcopy(results)

        summary = score_composition_results(results)

        self.assertEqual(results, original)
        self.assertEqual(summary["quality_metrics"]["synergy_lift"], 0.15)
        self.assertEqual(summary["quality_metrics"]["compiler_lift"], 0.25)
        self.assertEqual(summary["quality_metrics"]["order_lift"], 0.10)
        self.assertEqual(summary["cost_metrics"]["context_ratio"], 0.70)
        self.assertEqual(summary["best_singleton"]["skill_id"], "writing")
        self.assertEqual(
            summary["quality_metrics"]["leave_one_out_lifts"],
            {"research": 0.08, "review": 0.06, "writing": 0.10},
        )
        self.assertTrue(summary["eligible"])

    def test_safety_failure_makes_evaluation_ineligible(self) -> None:
        results = self._results()
        results[-1]["gate_results"] = [
            {
                "gate_id": "security-boundary",
                "category": "safety",
                "status": "failed",
            }
        ]

        summary = score_composition_results(results)

        self.assertFalse(summary["eligible"])
        self.assertEqual(summary["ineligibility_reasons"], ["safety_failure_present"])
        self.assertEqual(
            summary["safety"]["failed_variants"],
            [
                {
                    "variant_id": "wrong_order",
                    "failures": ["security-boundary"],
                }
            ],
        )

    def test_scoring_requires_complete_matching_ablation_pairs(self) -> None:
        results = [
            item
            for item in self._results()
            if item["variant_id"] != "leave_one_out:review"
        ]

        with self.assertRaisesRegex(ValueError, "same unique skill ids"):
            score_composition_results(results)

    def test_service_has_no_io_storage_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(composition_evaluation))
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
            "tmcp_runtime.adapters",
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


class ProjectRecipePromotionTests(unittest.TestCase):
    _GRAPH_DIGEST = "a" * 32
    _PLAN_ID = "composition-" + "b" * 20
    _PREFLIGHT_ID = "preflight-" + "c" * 20
    _RECIPE_DIGEST = "d" * 32
    _PLAN_DIGEST = "e" * 64

    def _phase_capsule_binding(self) -> dict[str, Any]:
        payload = {
            "schema": "tmcp-composition-phase-capsule-binding-v0.1",
            "composition_plan_id": self._PLAN_ID,
            "composition_plan_digest": self._PLAN_DIGEST,
            "preflight_id": self._PREFLIGHT_ID,
            "graph_digest": self._GRAPH_DIGEST,
            "recipe_digest": self._RECIPE_DIGEST,
            "context_accounting_digest": "a" * 64,
            "preflight_capsule_digest": "b" * 64,
            "phase_capsule_trace": [
                {
                    "stage_id": "stage-1",
                    "capsule_digest": "c" * 64,
                    "incoming_handoff_digests": [],
                }
            ],
        }
        return {**payload, "binding_digest": stable_digest(payload)}

    def _receipt(
        self,
        packet_id: str,
        fixture_id: str,
        *,
        graph_digest: str | None = None,
        synergy_lift: float = 0.12,
        compiler_lift: float = 0.08,
        order_lift: float = 0.06,
        context_ratio: float = 0.70,
    ) -> dict[str, Any]:
        binding = self._phase_capsule_binding()
        receipt: dict[str, Any] = {
            "packet_id": packet_id,
            "recipe_id": binding["composition_plan_id"],
            "graph_digest": graph_digest or self._GRAPH_DIGEST,
            "composition_fixture_id": fixture_id,
            "outcome": "passed",
            "verification_results": ["focused tests passed"],
            "user_overrides": [],
            "context_execution_mode": "isolated_phase_capsule",
            "composition_plan_digest": binding["composition_plan_digest"],
            "phase_capsule_binding_digest": binding["binding_digest"],
            "benchmark_control_input_digest": "d" * 64,
            "benchmark_execution_recipe_digest": "e" * 64,
            "context_accounting_digest": "a" * 64,
            "preflight_capsule_digest": "b" * 64,
            "phase_capsule_trace": [
                {
                    "stage_id": "stage-1",
                    "capsule_digest": "c" * 64,
                    "incoming_handoff_digests": [],
                }
            ],
            "gate_results": [
                {"gate_id": "safety-boundary", "category": "safety", "passed": True}
            ],
            "quality_metrics": {
                "synergy_lift": synergy_lift,
                "compiler_lift": compiler_lift,
                "order_lift": order_lift,
            },
            "cost_metrics": {"context_ratio": context_ratio},
        }
        self._refresh_provenance(receipt)
        return receipt

    def _refresh_provenance(self, receipt: dict[str, Any]) -> None:
        receipt.pop("benchmark_receipt_provenance", None)
        receipt["benchmark_receipt_provenance"] = build_benchmark_receipt_provenance(
            receipt,
            fixture_digest=stable_digest(
                {"fixture_id": receipt["composition_fixture_id"]}
            ),
            control_plan_id="benchmark-control-" + "f" * 20,
            control_plan_digest="1" * 64,
            host_artifact_digest="2" * 64,
            host_receipt_digest="3" * 64,
        )

    def test_three_verified_receipts_across_two_fixtures_are_eligible(self) -> None:
        receipts = [
            self._receipt("packet-1", "fixture-a", synergy_lift=0.11),
            self._receipt("packet-2", "fixture-a", synergy_lift=0.12),
            self._receipt("packet-3", "fixture-b", synergy_lift=0.13),
            self._receipt("old-graph", "fixture-c", graph_digest="f" * 32),
        ]
        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="recipe-123",
            graph_digest=self._GRAPH_DIGEST,
            phase_capsule_binding=self._phase_capsule_binding(),
        )

        self.assertTrue(eligibility["eligible"])
        self.assertEqual(eligibility["cache_policy"], "project")
        self.assertFalse(eligibility["auto_promote"])
        self.assertTrue(eligibility["explicit_promotion_required"])
        self.assertEqual(eligibility["evidence"]["verified_receipt_count"], 3)
        self.assertEqual(eligibility["evidence"]["fixture_count"], 2)
        self.assertEqual(
            eligibility["evidence"]["rejected_receipt_counts"][
                "different_graph_digest"
            ],
            1,
        )
        self.assertEqual(eligibility["aggregate_metrics"]["synergy_lift"], 0.12)
        self.assertEqual(
            eligibility["evidence"]["isolated_phase_capsule_receipt_count"], 3
        )

    def test_unrelated_but_well_formed_phase_digests_block_promotion(self) -> None:
        receipts = [
            self._receipt("packet-1", "fixture-a"),
            self._receipt("packet-2", "fixture-a"),
            self._receipt("packet-3", "fixture-b"),
        ]
        receipts[1]["phase_capsule_trace"][0]["capsule_digest"] = "f" * 64
        self._refresh_provenance(receipts[1])

        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="recipe-123",
            graph_digest=self._GRAPH_DIGEST,
            phase_capsule_binding=self._phase_capsule_binding(),
        )

        self.assertFalse(eligibility["eligible"])
        self.assertIn(
            "unmatched_phase_capsule_provenance", eligibility["blocking_reasons"]
        )
        self.assertEqual(
            eligibility["evidence"]["structurally_valid_phase_capsule_evidence_receipt_count"],
            3,
        )
        self.assertEqual(
            eligibility["evidence"]["bound_phase_capsule_evidence_receipt_count"],
            2,
        )
        self.assertEqual(
            eligibility["evidence"]["unmatched_phase_capsule_provenance_receipts"],
            ["packet-2"],
        )

    def test_same_host_or_missing_context_execution_blocks_promotion(self) -> None:
        receipts = [
            self._receipt("packet-1", "fixture-a"),
            self._receipt("packet-2", "fixture-a"),
            self._receipt("packet-3", "fixture-b"),
        ]
        receipts[0]["context_execution_mode"] = "same_host_transcript"
        self._refresh_provenance(receipts[0])
        receipts[1].pop("context_execution_mode")

        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="recipe-123",
            graph_digest=self._GRAPH_DIGEST,
            phase_capsule_binding=self._phase_capsule_binding(),
        )

        self.assertFalse(eligibility["eligible"])
        self.assertIn(
            "unqualified_context_execution", eligibility["blocking_reasons"]
        )
        self.assertEqual(
            eligibility["evidence"]["unqualified_context_execution_receipts"],
            ["packet-1"],
        )
        self.assertEqual(
            eligibility["evidence"]["rejected_receipt_counts"][
                "unqualified_context_execution"
            ],
            1,
        )
        self.assertEqual(eligibility["evidence"]["verified_receipt_count"], 1)
        self.assertEqual(
            eligibility["evidence"]["invalid_benchmark_receipt_provenance_receipts"],
            ["packet-2"],
        )

    def test_missing_benchmark_receipt_provenance_blocks_promotion_distinctly(
        self,
    ) -> None:
        receipts = [
            self._receipt("packet-1", "fixture-a"),
            self._receipt("packet-2", "fixture-a"),
            self._receipt("packet-3", "fixture-b"),
        ]
        receipts[0].pop("benchmark_receipt_provenance")

        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="recipe-123",
            graph_digest=self._GRAPH_DIGEST,
            phase_capsule_binding=self._phase_capsule_binding(),
        )

        self.assertFalse(eligibility["eligible"])
        self.assertIn(
            "missing_benchmark_receipt_provenance",
            eligibility["blocking_reasons"],
        )
        self.assertEqual(
            eligibility["evidence"]["missing_benchmark_receipt_provenance_receipts"],
            ["packet-1"],
        )
        self.assertEqual(
            eligibility["evidence"]["rejected_receipt_counts"][
                "missing_benchmark_receipt_provenance"
            ],
            1,
        )

    def test_invalid_and_unmatched_benchmark_receipt_provenance_are_metered(
        self,
    ) -> None:
        receipts = [
            self._receipt("packet-1", "fixture-a"),
            self._receipt("packet-2", "fixture-a"),
            self._receipt("packet-3", "fixture-b"),
        ]
        receipts[0]["benchmark_receipt_provenance"]["fixture_digest"] = "x" * 64
        receipts[1]["phase_capsule_binding_digest"] = "f" * 64
        self._refresh_provenance(receipts[1])

        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="recipe-123",
            graph_digest=self._GRAPH_DIGEST,
            phase_capsule_binding=self._phase_capsule_binding(),
        )

        self.assertFalse(eligibility["eligible"])
        self.assertIn(
            "invalid_benchmark_receipt_provenance",
            eligibility["blocking_reasons"],
        )
        self.assertIn(
            "unmatched_benchmark_receipt_provenance",
            eligibility["blocking_reasons"],
        )
        self.assertEqual(
            eligibility["evidence"]["invalid_benchmark_receipt_provenance_receipts"],
            ["packet-1"],
        )
        self.assertEqual(
            eligibility["evidence"]["unmatched_benchmark_receipt_provenance_receipts"],
            ["packet-2"],
        )

    def test_malformed_safe_phase_capsule_evidence_blocks_and_is_metered(self) -> None:
        receipts = [
            self._receipt("packet-1", "fixture-a"),
            self._receipt("packet-2", "fixture-a"),
            self._receipt("packet-3", "fixture-b"),
        ]
        receipts[0]["context_accounting_digest"] = "not-a-digest"
        receipts[1]["phase_capsule_trace"] = [
            {
                "stage_id": "stage-1",
                "capsule_digest": "c" * 64,
                "incoming_handoff_digests": [],
                "context_instance_id": "must-not-persist",
            }
        ]
        receipts[2]["phase_capsule_trace"] = []
        for receipt in receipts:
            self._refresh_provenance(receipt)

        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="recipe-123",
            graph_digest=self._GRAPH_DIGEST,
            phase_capsule_binding=self._phase_capsule_binding(),
        )

        self.assertFalse(eligibility["eligible"])
        self.assertIn(
            "invalid_phase_capsule_evidence", eligibility["blocking_reasons"]
        )
        self.assertEqual(
            eligibility["evidence"]["invalid_phase_capsule_evidence_receipts"],
            ["packet-1", "packet-2", "packet-3"],
        )
        self.assertEqual(
            eligibility["evidence"]["rejected_receipt_counts"][
                "invalid_phase_capsule_evidence"
            ],
            3,
        )

    def test_safety_failure_and_override_block_promotion(self) -> None:
        receipts = [
            self._receipt("packet-1", "fixture-a"),
            self._receipt("packet-2", "fixture-a"),
            self._receipt("packet-3", "fixture-b"),
        ]
        receipts[1]["user_overrides"] = ["skip safety gate"]
        receipts[2]["gate_results"] = [
            {
                "gate_id": "safety-boundary",
                "category": "safety",
                "passed": False,
            }
        ]

        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="recipe-123",
            graph_digest=self._GRAPH_DIGEST,
            phase_capsule_binding=self._phase_capsule_binding(),
        )

        self.assertFalse(eligibility["eligible"])
        self.assertIn("safety_failure_present", eligibility["blocking_reasons"])
        self.assertIn("override_present", eligibility["blocking_reasons"])
        self.assertEqual(
            eligibility["evidence"]["safety_failure_receipts"], ["packet-3"]
        )
        self.assertEqual(eligibility["evidence"]["override_receipts"], ["packet-2"])

    def test_failed_verification_blocks_even_when_safety_gate_passes(self) -> None:
        receipts = [
            self._receipt("packet-1", "fixture-a"),
            self._receipt("packet-2", "fixture-a"),
            self._receipt("packet-3", "fixture-b"),
        ]
        receipts[2]["verification_results"] = ["focused tests failed"]

        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="recipe-123",
            graph_digest=self._GRAPH_DIGEST,
            phase_capsule_binding=self._phase_capsule_binding(),
        )

        self.assertFalse(eligibility["eligible"])
        self.assertIn(
            "minimum_verified_receipts_not_met", eligibility["blocking_reasons"]
        )
        self.assertEqual(eligibility["evidence"]["verified_receipt_count"], 2)
        self.assertEqual(
            eligibility["evidence"]["rejected_receipt_counts"]["unverified"],
            1,
        )

    def test_missing_or_ambiguous_safety_gate_evidence_blocks_promotion(self) -> None:
        invalid_gate_results = (
            [],
            [{"gate_id": "quality", "category": "quality", "passed": True}],
            [{"gate_id": "safety-boundary", "category": "safety"}],
        )
        for gate_results in invalid_gate_results:
            with self.subTest(gate_results=gate_results):
                receipts = [
                    self._receipt("packet-1", "fixture-a"),
                    self._receipt("packet-2", "fixture-a"),
                    self._receipt("packet-3", "fixture-b"),
                    self._receipt("packet-missing-safety", "fixture-c"),
                ]
                receipts[-1]["gate_results"] = gate_results

                eligibility = assess_project_recipe_promotion(
                    receipts,
                    recipe_id="recipe-123",
                    graph_digest=self._GRAPH_DIGEST,
                    phase_capsule_binding=self._phase_capsule_binding(),
                )

                self.assertFalse(eligibility["eligible"])
                self.assertIn(
                    "missing_safety_gate_evidence",
                    eligibility["blocking_reasons"],
                )
                self.assertEqual(eligibility["evidence"]["verified_receipt_count"], 3)
                self.assertEqual(
                    eligibility["evidence"]["missing_safety_gate_receipts"],
                    ["packet-missing-safety"],
                )
                self.assertEqual(
                    eligibility["evidence"]["rejected_receipt_counts"][
                        "missing_safety_gate_evidence"
                    ],
                    1,
                )

    def test_median_lift_and_context_thresholds_are_enforced(self) -> None:
        receipts = [
            self._receipt(
                "packet-1",
                "fixture-a",
                synergy_lift=0.05,
                compiler_lift=0.01,
                order_lift=0.01,
                context_ratio=0.90,
            ),
            self._receipt(
                "packet-2",
                "fixture-a",
                synergy_lift=0.06,
                compiler_lift=0.02,
                order_lift=0.02,
                context_ratio=0.85,
            ),
            self._receipt(
                "packet-3",
                "fixture-b",
                synergy_lift=0.07,
                compiler_lift=0.03,
                order_lift=0.03,
                context_ratio=0.80,
            ),
        ]

        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="recipe-123",
            graph_digest=self._GRAPH_DIGEST,
            phase_capsule_binding=self._phase_capsule_binding(),
        )

        self.assertFalse(eligibility["eligible"])
        self.assertIn("synergy_lift_below_threshold", eligibility["blocking_reasons"])
        self.assertIn("compiler_lift_below_threshold", eligibility["blocking_reasons"])
        self.assertIn("order_lift_below_threshold", eligibility["blocking_reasons"])
        self.assertIn("context_ratio_above_threshold", eligibility["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
