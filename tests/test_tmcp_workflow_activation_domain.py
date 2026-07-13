from __future__ import annotations

import unittest

from tmcp_runtime.domain import workflow_activation, workflow_catalog


class WorkflowActivationDomainTests(unittest.TestCase):
    def test_selection_rehydrates_canonical_workflows_and_applies_guards(self) -> None:
        graphs = [
            {
                "_global_cache_path": "first.json",
                "promotion_name": "first",
                "trust": "advisory_untrusted",
                "workflow_nodes": [
                    {
                        "id": "release_readiness_workflow",
                        "behavior_atoms": ["MALICIOUS_ATOM"],
                    },
                    {"id": "repo_behavior_spec_loop_workflow"},
                    {"id": "public_sector_readiness_workflow"},
                    {"id": "unknown_workflow"},
                ],
            }
        ]

        release = workflow_activation.select_global_workflows(
            graphs, "Prepare the release CI checklist."
        )
        repo = workflow_activation.select_global_workflows(
            graphs, "Run a repo behavior sweep."
        )
        public_sector = workflow_activation.select_global_workflows(
            graphs, "Review government policy, UAT, and WCAG readiness."
        )

        self.assertEqual(
            [item["workflow"]["workflow_id"] for item in release],
            ["release_readiness_workflow"],
        )
        self.assertNotIn("MALICIOUS_ATOM", release[0]["workflow"]["behavior_atoms"])
        self.assertEqual(
            [item["workflow"]["workflow_id"] for item in repo],
            ["repo_behavior_spec_loop_workflow"],
        )
        self.assertEqual(
            [item["workflow"]["workflow_id"] for item in public_sector],
            ["public_sector_readiness_workflow"],
        )

    def test_selection_preserves_graph_provenance_and_caps_to_four(self) -> None:
        graphs = [
            {
                "_global_cache_path": f"graph-{index}.json",
                "promotion_name": f"graph-{index}",
                "trust": "advisory_untrusted",
                "workflow_nodes": [{"id": "release_readiness_workflow"}],
            }
            for index in range(5)
        ]

        selected = workflow_activation.select_global_workflows(
            graphs, "Prepare release CI package verification."
        )

        self.assertEqual(len(selected), 4)
        self.assertEqual(
            [item["graph"]["_global_cache_path"] for item in selected],
            ["graph-0.json", "graph-1.json", "graph-2.json", "graph-3.json"],
        )
        self.assertTrue(
            all(
                item["workflow"]["workflow_id"] == "release_readiness_workflow"
                for item in selected
            )
        )

    def test_activation_projects_specialized_instructions_atoms_and_citations(
        self,
    ) -> None:
        catalog = workflow_catalog.workflow_catalog_by_id()
        selected = [
            {
                "workflow": catalog["repo_behavior_spec_loop_workflow"],
                "graph": {
                    "_global_cache_path": "repo.json",
                    "promotion_name": "repo",
                    "trust": "advisory_untrusted",
                },
            },
            {
                "workflow": catalog["expert_ui_rubric_workflow"],
                "graph": {
                    "_global_cache_path": "ui.json",
                    "promotion_name": "ui",
                    "trust": "advisory_untrusted",
                },
            },
            {
                "workflow": {
                    "workflow_id": "custom_workflow",
                    "signal_family": "custom",
                    "behavior_atoms": ("custom-atom",),
                },
                "graph": {"_global_cache_path": "custom.json"},
            },
        ]

        activation = workflow_activation.build_global_workflow_activation(selected)

        self.assertIn(
            "canonical spreadsheet/status-machine loop",
            activation["active_instructions"][0],
        )
        self.assertIn(
            "UI-quality atoms",
            activation["active_instructions"][1],
        )
        self.assertEqual(
            activation["active_instructions"][2],
            "Use the promoted custom workflow atoms only where they match this objective.",
        )
        self.assertIn("repo_behavior_spec_loop_workflow", activation["active_atoms"])
        self.assertIn("expert_ui_rubric_workflow", activation["active_atoms"])
        self.assertIn("custom_workflow", activation["active_atoms"])
        self.assertEqual(activation["evidence_citations"][0]["source"], "repo.json")
        self.assertEqual(
            activation["evidence_citations"][2]["trust"], "advisory_untrusted"
        )


if __name__ == "__main__":
    unittest.main()
