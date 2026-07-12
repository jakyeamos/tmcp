from __future__ import annotations

import unittest

from tmcp_runtime.domain import workflow_catalog


class WorkflowCatalogDomainTests(unittest.TestCase):
    def test_candidate_selection_preserves_id_and_family_matching(self) -> None:
        all_workflows = workflow_catalog.workflow_catalog()

        self.assertEqual(
            workflow_catalog.select_workflow_catalog(["release_readiness_workflow"]),
            [
                item
                for item in all_workflows
                if item["workflow_id"] == "release_readiness_workflow"
            ],
        )
        self.assertEqual(
            workflow_catalog.select_workflow_catalog(["security_privacy"]),
            [
                item
                for item in all_workflows
                if item["signal_family"] == "security_privacy"
            ],
        )
        self.assertEqual(workflow_catalog.select_workflow_catalog(["  "]), all_workflows)

    def test_catalog_lookup_returns_unique_isolated_definitions(self) -> None:
        catalog = workflow_catalog.workflow_catalog()
        lookup = workflow_catalog.workflow_catalog_by_id()

        self.assertEqual(len(catalog), len(lookup))
        self.assertEqual(
            len({item["workflow_id"] for item in catalog}), len(catalog)
        )
        catalog[0]["name"] = "Mutated"
        self.assertNotEqual(workflow_catalog.workflow_catalog()[0]["name"], "Mutated")

    def test_stability_preserves_catalog_and_fallback_contracts(self) -> None:
        self.assertEqual(
            workflow_catalog.workflow_stability(
                {"workflow_id": "release_readiness_workflow"}
            ),
            "stable",
        )
        self.assertEqual(
            workflow_catalog.workflow_stability(
                {"workflow_id": "expert_ui_rubric_workflow"}
            ),
            "experimental",
        )
        self.assertEqual(
            workflow_catalog.workflow_stability(
                {"workflow_id": "custom", "stability": "stable"}
            ),
            "stable",
        )
        self.assertEqual(
            workflow_catalog.stable_workflow_ids(),
            ["developer_experience_workflow", "release_readiness_workflow"],
        )


if __name__ == "__main__":
    unittest.main()
