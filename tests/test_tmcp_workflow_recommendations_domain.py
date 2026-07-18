from __future__ import annotations

import unittest

from tmcp_runtime.domain import workflow_catalog, workflow_recommendations


class WorkflowRecommendationsDomainTests(unittest.TestCase):
    def test_source_bundle_does_not_score_as_performance_evidence(self) -> None:
        workflow = workflow_catalog.workflow_catalog_by_id()[
            "performance_review_workflow"
        ]
        source_nodes = [
            {
                "path": "/tmp/project/study.md",
                "relative_path": "docs/study.md",
                "title": "Source-bundle study",
                "source_type": "project_documentation",
                "behavior_atoms": [],
                "guidance_labels": [],
                "excerpt": "A preregistered source-bundle study.",
                "signal_text": "A preregistered source-bundle study.",
            }
        ]

        score = workflow_recommendations.score_workflow_signal(
            workflow,
            source_nodes,
            node_signal_text=lambda node: str(node["signal_text"]),
            signal_guidance_label_ids={},
        )

        self.assertEqual(score["score"], 0.0)
        self.assertEqual(score["evidence"], [])

    def test_scoring_uses_injected_harvest_text_and_guidance_labels(self) -> None:
        workflow = workflow_catalog.workflow_catalog_by_id()[
            "release_readiness_workflow"
        ]
        source_nodes = [
            {
                "path": "/tmp/project/README.md",
                "relative_path": "README.md",
                "title": "Release readiness",
                "source_type": "project_documentation",
                "behavior_atoms": ["artifact-contract"],
                "guidance_labels": [{"id": "release:readiness"}],
                "excerpt": "Release verification evidence.",
                "signal_text": "release ci package verification",
            }
        ]

        score = workflow_recommendations.score_workflow_signal(
            workflow,
            source_nodes,
            node_signal_text=lambda node: str(node["signal_text"]),
            signal_guidance_label_ids={"release_readiness": ("release:readiness",)},
        )

        self.assertEqual(score["stability"], "stable")
        self.assertEqual(score["score"], 6.0)
        self.assertEqual(score["confidence"], 0.5)
        self.assertEqual(score["evidence"][0]["source_scope"], "repo_or_project_local")
        self.assertIn("release", score["evidence"][0]["matched_terms"])
        self.assertEqual(
            workflow_recommendations.recommendation_reason(score),
            "Harvest matched ci, package, release, verification signals across 1 source nodes.",
        )

    def test_templates_rubrics_and_instances_preserve_candidate_contracts(self) -> None:
        workflow = workflow_catalog.workflow_catalog_by_id()[
            "developer_experience_workflow"
        ]
        harvest = {
            "source_paths": ["/tmp/project"],
            "source_count": 1,
            "matched_source_count": 1,
        }
        score = {
            "evidence": [
                {
                    "relative_path": "README.md",
                    "source_type": "project_documentation",
                    "matched_terms": ["onboarding"],
                    "matched_behavior_atoms": ["artifact-contract"],
                    "guidance_labels": [],
                }
            ]
        }

        rubric = workflow_recommendations.workflow_rubric_seed(
            workflow, "Improve CLI onboarding."
        )
        template = workflow_recommendations.workflow_template(workflow)
        instance = workflow_recommendations.workflow_instance(
            workflow=workflow,
            objective="Improve CLI onboarding.",
            harvest=harvest,
            score=score,
        )

        self.assertEqual(rubric["profile"], "developer_experience")
        self.assertEqual(rubric["dimension_seeds"][0]["id"], "command_discoverability")
        self.assertEqual(template["id"], "developer_experience_workflow")
        self.assertEqual(instance["template_id"], template["id"])
        self.assertTrue(instance["id"].startswith("developer_experience_workflow."))
        self.assertTrue(instance["approval_required"])
        self.assertEqual(
            workflow_recommendations.source_scope_for("/Users/name/.codex/skills/foo"),
            "user_or_agent_skill",
        )


if __name__ == "__main__":
    unittest.main()
