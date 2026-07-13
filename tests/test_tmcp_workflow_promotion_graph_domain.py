from __future__ import annotations

import unittest

from tmcp_runtime.domain import workflow_promotion


class WorkflowPromotionGraphDomainTests(unittest.TestCase):
    def test_selection_accepts_aliases_and_reports_sorted_missing_ids(self) -> None:
        recommendation = {
            "recommended_workflows": [
                {
                    "id": "release_readiness_workflow",
                    "signal_family": "release_readiness",
                    "name": "Release Readiness Workflow",
                },
                {
                    "id": "developer_experience_workflow",
                    "signal_family": "developer_experience",
                    "name": "Developer Experience Workflow",
                },
            ],
            "recommended_scoped_packet_seeds": [
                {
                    "id": "release-seed",
                    "name": "Release seed",
                    "relative_path": "seeds/release.json",
                }
            ],
        }

        targets = workflow_promotion.select_promotion_targets(
            recommendation,
            selected_workflows=["release_readiness", "missing-workflow"],
            selected_scoped_packet_seeds=["Release seed"],
            selected_scoped_seeds=["missing-seed"],
        )

        self.assertEqual(
            [item["id"] for item in targets["selected_workflows"]],
            ["release_readiness_workflow"],
        )
        self.assertEqual(targets["missing_workflows"], ["missing-workflow"])
        self.assertEqual(
            [item["id"] for item in targets["selected_scoped_packet_seeds"]],
            ["release-seed"],
        )
        self.assertEqual(targets["missing_scoped_packet_seeds"], ["missing-seed"])

        implicit_targets = workflow_promotion.select_promotion_targets(
            recommendation,
            selected_workflows=None,
            selected_scoped_packet_seeds=None,
            selected_scoped_seeds=None,
        )
        explicit_empty_targets = workflow_promotion.select_promotion_targets(
            recommendation,
            selected_workflows=[""],
            selected_scoped_packet_seeds=None,
            selected_scoped_seeds=None,
        )
        self.assertEqual(implicit_targets["selected_workflows"], [])
        self.assertEqual(
            [item["id"] for item in explicit_empty_targets["selected_workflows"]],
            ["release_readiness_workflow", "developer_experience_workflow"],
        )

    def test_graph_preserves_catalog_and_evidence_edges(self) -> None:
        graph = workflow_promotion.build_promotion_graph(
            promotion_name="release-check",
            created_at="2026-07-12T00:00:00Z",
            source_map=[
                {
                    "relative_path": "RELEASE.md",
                    "behavior_atoms": [
                        "quality-gate-disclosure",
                        "artifact-contract",
                    ],
                },
                {
                    "relative_path": "docs/release.md",
                    "behavior_atoms": ["quality-gate-disclosure"],
                },
            ],
            selected_workflows=[
                {
                    "id": "release_readiness_workflow",
                    "name": "Release Readiness Workflow",
                    "stability": "stable",
                    "signal_family": "release_readiness",
                    "confidence": 0.8,
                    "template": {"id": "release_readiness_workflow"},
                    "workflow_instance": {"id": "release.abc"},
                    "evidence": [
                        {
                            "relative_path": "RELEASE.md",
                            "matched_behavior_atoms": ["external-atom"],
                            "matched_terms": ["CI verification"],
                        }
                    ],
                }
            ],
            selected_scoped_packet_seeds=[
                {
                    "id": "release-seed",
                    "name": "Release seed",
                    "source_references": ["RELEASE.md", "RELEASE.md"],
                    "behavior_atoms": ["quality-gate-disclosure"],
                    "verification_expectations": ["Run the release checks."],
                    "routing_trigger": "Use the release seed.",
                }
            ],
        )

        self.assertEqual(graph["schema"], "tmcp-promoted-harvest-graph-v0.1")
        self.assertEqual(graph["behavior_atoms"][0]["id"], "quality-gate-disclosure")
        self.assertEqual(graph["behavior_atoms"][0]["source_count"], 2)
        self.assertEqual(
            graph["cross_source_behavior_atoms"], [graph["behavior_atoms"][0]]
        )
        self.assertEqual(graph["scoped_packet_seed_nodes"][0]["id"], "release-seed")
        self.assertEqual(
            graph["verification_expectation_nodes"][0]["id"],
            "verification:release-seed:1",
        )
        self.assertEqual(
            sum(
                edge["relation"] == "supports_scoped_packet_seed"
                for edge in graph["edges"]
            ),
            1,
        )
        self.assertTrue(
            any(
                edge["from"] == "quality-gate-disclosure"
                and edge["to"] == "release_readiness_workflow"
                and edge["relation"] == "supports_workflow"
                for edge in graph["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["from"] == "external-atom"
                and edge["relation"] == "supports_workflow"
                for edge in graph["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["from"] == "term:ci_verification"
                and edge["relation"] == "matched_routing_signal"
                for edge in graph["edges"]
            )
        )

    def test_markdown_renderer_includes_graph_summary_and_policy(self) -> None:
        markdown = workflow_promotion.render_promotion_markdown(
            {
                "promotion_name": "release-check",
                "status": "preview",
                "source_harvest": {"source_count": 2},
                "promoted_workflow_ids": ["release_readiness_workflow"],
                "promoted_scoped_packet_seed_ids": ["release-seed"],
                "promotion_graph": {
                    "source_nodes": [{}, {}],
                    "scoped_packet_seed_nodes": [{}],
                    "behavior_atoms": [{}, {}],
                    "edges": [{}, {}, {}],
                },
                "promotion_policy": ["Promotion remains advisory."],
            }
        )

        self.assertTrue(markdown.endswith("\n"))
        self.assertIn("# TMCP Harvest Promotion: release-check", markdown)
        self.assertIn("- Source nodes: 2", markdown)
        self.assertIn("- Edges: 3", markdown)
        self.assertIn("Promotion remains advisory.", markdown)


if __name__ == "__main__":
    unittest.main()
