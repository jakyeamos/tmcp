from __future__ import annotations

import unittest

from tests import test_tmcp_composition_benchmarks as benchmark_test_support
from tmcp_runtime.domain.composition_benchmarks import (
    score_behavioral_benchmark,
    score_composition_benchmark,
    score_routing_benchmark,
)


class CompositionBenchmarkAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = benchmark_test_support.CompositionBenchmarkTests()
        cls.builder.setUpClass()

    def test_combined_acceptance_reports_conflicts_provenance_and_context_failures(
        self,
    ) -> None:
        observed = self.builder._behavioral_results()
        first_fixture = self.builder.fixture_definitions[0]
        first = observed[0]
        conflict_source, conflict_target = first["selected_skill_ids"][:2]
        slices = {item["skill_id"]: item["slice_id"] for item in first["source_slices"]}
        first["relationships"].append(
            {
                "source_id": conflict_source,
                "target_id": conflict_target,
                "relation": "conflicts_with",
                "citations": [slices[conflict_source], slices[conflict_target]],
            }
        )
        missing_target = first_fixture["expected_skill_ids"][-1]
        first["relationships"] = [
            relationship
            for relationship in first["relationships"]
            if relationship["target_id"] != missing_target
        ]
        first["compiled_context_tokens"] = 900
        self.builder._refresh_behavioral_integrity(first_fixture, first)

        summary = score_composition_benchmark(
            golden_cases=self.builder.golden_cases,
            fixture_definitions=self.builder.fixture_definitions,
            routing_results=self.builder._routing_results(),
            behavioral_results=observed,
        )

        behavioral = summary["behavioral_metrics"]
        self.assertFalse(summary["eligible"])
        self.assertEqual(behavioral["active_conflict_violation_count"], 1)
        self.assertIn(
            {"fixture_id": first_fixture["fixture_id"], "skill_id": missing_target},
            behavioral["missing_incoming_relationships"],
        )
        self.assertEqual(behavioral["maximum_fixture_context_ratio"], 0.9)
        self.assertIn("active_conflict_violations", summary["failed_checks"])
        self.assertIn("incoming_provenance_relationships", summary["failed_checks"])
        self.assertIn("context_ratio", summary["failed_checks"])

    def test_expected_relationships_and_order_are_hard_acceptance_gates(self) -> None:
        observed = self.builder._behavioral_results()
        observed[0]["relationships"][0]["relation"] = "complements"
        self.builder._refresh_behavioral_integrity(
            self.builder.fixture_definitions[0], observed[0]
        )
        observed[1]["ordered_skill_ids"] = list(
            reversed(observed[1]["ordered_skill_ids"])
        )
        observed[1]["active_stages"] = list(reversed(observed[1]["active_stages"]))

        summary = score_composition_benchmark(
            golden_cases=self.builder.golden_cases,
            fixture_definitions=self.builder.fixture_definitions,
            routing_results=self.builder._routing_results(),
            behavioral_results=observed,
        )

        self.assertFalse(summary["eligible"])
        self.assertIn("incoming_provenance_relationships", summary["failed_checks"])
        self.assertIn("expected_order", summary["failed_checks"])

    def test_complete_observed_results_meet_acceptance_thresholds(self) -> None:
        summary = score_composition_benchmark(
            golden_cases=self.builder.golden_cases,
            fixture_definitions=self.builder.fixture_definitions,
            routing_results=self.builder._routing_results(),
            behavioral_results=self.builder._behavioral_results(),
        )

        self.assertTrue(summary["eligible"])
        self.assertEqual(summary["failed_checks"], [])
        self.assertTrue(all(summary["acceptance_checks"].values()))

    def test_scorer_requires_run_supplied_quality_scores(self) -> None:
        observed = self.builder._behavioral_results()
        del observed[0]["quality_scores"]

        with self.assertRaisesRegex(ValueError, "must be supplied by the run"):
            score_behavioral_benchmark(self.builder.fixture_definitions, observed)

    def test_routing_scorer_rejects_missing_case_as_malformed(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Routing observations must match golden case ids exactly",
        ):
            score_routing_benchmark(
                self.builder.golden_cases,
                self.builder._routing_results()[1:],
            )

    def test_routing_execution_manifest_binds_selected_skills(self) -> None:
        observed = self.builder._routing_results()
        observed[0]["selected_skill_ids"].append("post-run-tamper")

        with self.assertRaisesRegex(ValueError, "result_digest"):
            score_routing_benchmark(self.builder.golden_cases, observed)

    def test_active_stages_must_cover_ordered_skills_exactly(self) -> None:
        observed = self.builder._behavioral_results()
        observed[0]["active_stages"] = [
            {"stage_id": "declared-but-empty", "active_skill_ids": []}
        ]

        with self.assertRaisesRegex(ValueError, "cover ordered skills exactly once"):
            score_behavioral_benchmark(self.builder.fixture_definitions, observed)

    def test_graph_identity_is_recomputed_from_materialized_sources(self) -> None:
        observed = self.builder._behavioral_results()
        observed[0]["graph_digest"] = "f" * 32
        observed[0]["run_receipt"]["graph_digest"] = "f" * 32

        with self.assertRaisesRegex(ValueError, "source content and relationships"):
            score_behavioral_benchmark(self.builder.fixture_definitions, observed)

    def test_evaluator_evidence_must_resolve_to_hash_bound_content(self) -> None:
        observed = self.builder._behavioral_results()
        evidence = observed[0]["evidence_manifest"][0]
        evidence["content"] = "made-up-reference"

        with self.assertRaisesRegex(
            ValueError, "content_digest does not match content"
        ):
            score_behavioral_benchmark(self.builder.fixture_definitions, observed)
