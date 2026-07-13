from __future__ import annotations

import unittest

from tmcp_runtime.domain import workflow_adaptive


class WorkflowAdaptiveDomainTests(unittest.TestCase):
    def test_scoped_seed_projection_preserves_candidate_contract(self) -> None:
        recommendations = workflow_adaptive.recommended_scoped_packet_seeds(
            [
                {
                    "id": "release-packet",
                    "seed_id": "release-packet",
                    "title": "Release packet",
                    "source_type": "scoped_packet_seed",
                    "relative_path": "seeds/release.json",
                    "canonical_source": "skills/release/SKILL.md",
                    "source_references": ["README.md"],
                    "loads": ["release"],
                    "chains_before": ["harvest"],
                    "chains_after": ["review"],
                    "do_not_activate_with": ["migration"],
                    "use_when": ["release readiness"],
                    "modes": ["review"],
                    "minimum_spec_fields": ["version"],
                    "ticket_types": ["release"],
                    "behavior_atoms": ["quality-gate-disclosure"],
                    "verification_expectations": ["run checks"],
                    "required_receipts": ["ci output"],
                    "guidance_labels": [{"id": "release:readiness"}],
                    "promotion_status": "proposal_not_promoted",
                    "promote_as_single_global_graph": True,
                },
                {"id": "ignored", "source_type": "project_documentation"},
                {"id": " ", "source_type": "scoped_packet_seed"},
            ]
        )

        self.assertEqual(len(recommendations), 1)
        recommendation = recommendations[0]
        self.assertEqual(recommendation["id"], "release-packet")
        self.assertEqual(recommendation["kind"], "scoped_packet_seed")
        self.assertEqual(recommendation["trust"], "advisory_untrusted")
        self.assertTrue(recommendation["approval_required"])
        self.assertTrue(recommendation["promote_as_single_global_graph"])
        self.assertEqual(recommendation["loads"], ["release"])
        self.assertIn("`release-packet`", recommendation["routing_trigger"])

    def test_adaptive_pack_groups_sources_and_uses_selection_fallback(self) -> None:
        source_nodes = [
            {
                "id": "project-release",
                "path": "/tmp/project/RELEASE.md",
                "relative_path": "RELEASE.md",
                "title": "Release notes",
                "source_type": "project_documentation",
                "behavior_atoms": ["source-traceability"],
                "guidance_labels": [
                    {
                        "id": "release:readiness",
                        "label": "Release readiness",
                        "summary": "Release evidence.",
                        "matched_terms": ["release"],
                    }
                ],
                "keywords": ["release", "verification"],
            },
            {
                "id": "release-packet",
                "seed_id": "release-packet",
                "path": "/Users/example/.codex/skills/release/seed.json",
                "relative_path": "seeds/release.json",
                "title": "Release packet",
                "source_type": "scoped_packet_seed",
                "behavior_atoms": ["source-traceability"],
                "guidance_labels": [
                    {
                        "id": "release:readiness",
                        "label": "Release readiness",
                        "summary": "Release evidence.",
                        "matched_terms": ["ci"],
                    }
                ],
                "use_when": ["release readiness"],
            },
        ]
        recommended = [
            {
                "id": "release_readiness_workflow",
                "signal_family": "release_readiness",
                "stability": "stable",
                "template": {"id": "release_readiness_workflow"},
                "workflow_instance": {
                    "routing_trigger": "Use release readiness for verified releases."
                },
            }
        ]
        scoped_seeds = workflow_adaptive.recommended_scoped_packet_seeds(source_nodes)
        custom_ideas = workflow_adaptive.custom_workflow_ideas(
            source_nodes, recommended
        )

        pack = workflow_adaptive.build_adaptive_workflow_pack(
            harvest={
                "source_paths": ["/tmp/project"],
                "source_count": 2,
                "matched_source_count": 2,
            },
            source_nodes=source_nodes,
            priority_profile={
                "primary_signals": ["release_readiness"],
                "secondary_signals": [],
                "weak_signals": [],
            },
            recommended=recommended,
            recommended_scoped_packet_seeds=scoped_seeds,
            not_recommended=[],
            custom_workflow_ideas=custom_ideas,
        )

        self.assertEqual(pack["artifact_type"], "adaptive_workflow_pack")
        self.assertEqual(
            pack["operating_profile"]["source_scope_counts"],
            [
                {"id": "repo_or_project_local", "count": 1},
                {"id": "user_or_agent_skill", "count": 1},
            ],
        )
        self.assertEqual(
            pack["overlap_analysis"]["clusters"][0]["label_id"],
            "release:readiness",
        )
        self.assertEqual(pack["overlap_analysis"]["clusters"][0]["source_count"], 2)
        self.assertEqual(
            pack["next_workflow_selection"]["candidate_scoped_seed_ids"],
            ["release-packet"],
        )
        self.assertEqual(
            pack["next_workflow_selection"]["candidate_template_ids"],
            ["release_readiness_workflow"],
        )
        self.assertEqual(
            pack["generated_custom_workflow_ideas"][0]["id"],
            "custom_source_traceability_workflow",
        )
        self.assertEqual(pack["documented_process_gaps"][0]["id"], "selection_required")
        self.assertIn(
            "Use release readiness for verified releases.",
            pack["suggested_routing_triggers"],
        )

    def test_markdown_renderer_covers_all_recommendation_sections(self) -> None:
        markdown = workflow_adaptive.render_workflow_recommendations_markdown(
            {
                "priority_profile": {
                    "primary_signals": ["release_readiness"],
                    "secondary_signals": ["testing_quality"],
                    "weak_signals": ["ui_quality"],
                },
                "recommended_workflows": [
                    {
                        "id": "release_readiness_workflow",
                        "confidence": 0.7,
                        "stability": "stable",
                        "signal_family": "release_readiness",
                        "why": "Release evidence matched.",
                        "starter_prompt": "Review release readiness.",
                        "workflow_instance": {"id": "release.123"},
                    }
                ],
                "recommended_scoped_packet_seeds": [
                    {"id": "release-packet", "promotion_status": "proposal"}
                ],
                "custom_workflow_ideas": [
                    {
                        "id": "custom_release_workflow",
                        "why": "Release behavior is repeated.",
                    }
                ],
                "not_recommended": [{"id": "ui_workflow", "reason": "No UI evidence."}],
            }
        )

        self.assertTrue(markdown.endswith("\n"))
        self.assertIn("### release_readiness_workflow", markdown)
        self.assertIn("## Recommended Scoped Packet Seeds", markdown)
        self.assertIn("`custom_release_workflow`", markdown)
        self.assertIn("`ui_workflow`", markdown)


if __name__ == "__main__":
    unittest.main()
