from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tmcp_runtime.services import promotion


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = PLUGIN_ROOT / "tmcp_runtime" / "services" / "promotion.py"


def _recommendation() -> dict[str, object]:
    return {
        "source_harvest": {"source_count": 1},
        "priority_profile": {"primary_signals": ["release_readiness"]},
        "recommended_workflows": [
            {
                "id": "release_readiness_workflow",
                "name": "Release Readiness Workflow",
                "signal_family": "release_readiness",
            }
        ],
        "recommended_scoped_packet_seeds": [
            {
                "id": "scoped-seed",
                "name": "Scoped Seed",
                "relative_path": "docs/seed.json#scoped-seed",
                "behavior_atoms": ["artifact-contract"],
            }
        ],
        "adaptive_workflow_pack": {
            "harvested_source_map": [
                {
                    "relative_path": "docs/release.md",
                    "behavior_atoms": ["artifact-contract"],
                }
            ]
        },
    }


class PromotionServiceTests(unittest.TestCase):
    def test_preview_forwards_callbacks_and_uses_fixed_clock(self) -> None:
        source_advisories = Mock(return_value=[])
        compose_preview_for_objective = Mock(
            return_value={"schema": "tmcp-composed-packet-v0.1"}
        )
        preview_results: list[dict[str, object]] = []

        def recommend(
            arguments: dict[str, object],
            *,
            source_advisories: object,
            compose_preview: object,
        ) -> dict[str, object]:
            self.assertFalse(arguments["write_artifacts"])
            self.assertIs(source_advisories, source_advisories_input)
            self.assertIsNotNone(compose_preview)
            preview_results.append(compose_preview())
            return _recommendation()

        source_advisories_input = source_advisories
        with patch.object(promotion, "recommend_workflows", side_effect=recommend):
            result = promotion.promote_harvest(
                {
                    "objective": "Release readiness!",
                    "compose": True,
                    "write_artifacts": False,
                },
                source_advisories=source_advisories,
                compose_preview_for_objective=compose_preview_for_objective,
                now_iso=lambda: "2026-07-12T00:00:00Z",
            )

        compose_preview_for_objective.assert_called_once_with("Release readiness!")
        self.assertEqual(
            preview_results,
            [{"schema": "tmcp-composed-packet-v0.1"}],
        )
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["promotion_name"], "release-readiness")
        self.assertEqual(
            result["promotion_graph"]["created_at"],
            "2026-07-12T00:00:00Z",
        )
        self.assertNotIn("artifact_paths", result)

    def test_selection_and_missing_workflows_are_reported_without_writes(self) -> None:
        with patch.object(
            promotion,
            "recommend_workflows",
            return_value=_recommendation(),
        ):
            result = promotion.promote_harvest(
                {
                    "selected_workflows": [
                        "release_readiness_workflow",
                        "missing-workflow",
                    ],
                    "write_artifacts": True,
                },
                source_advisories=None,
                compose_preview_for_objective=None,
                now_iso=lambda: "2026-07-12T00:00:00Z",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "partial_promotion")
        self.assertEqual(
            result["promoted_workflow_ids"],
            ["release_readiness_workflow"],
        )
        self.assertEqual(result["missing_selected_workflows"], ["missing-workflow"])

    def test_scoped_seed_only_preview_suppresses_workflow_promotion(self) -> None:
        with patch.object(
            promotion,
            "recommend_workflows",
            return_value=_recommendation(),
        ):
            result = promotion.promote_harvest(
                {
                    "selected_scoped_packet_seeds": ["scoped-seed"],
                    "write_artifacts": False,
                },
                source_advisories=None,
                compose_preview_for_objective=None,
                now_iso=lambda: "2026-07-12T00:00:00Z",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["promoted_workflow_ids"], [])
        self.assertEqual(result["promoted_scoped_packet_seed_ids"], ["scoped-seed"])
        self.assertEqual(result["status"], "preview")

    def test_service_does_not_import_the_adapter(self) -> None:
        module = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(module)
            if isinstance(node, ast.Import)
            for alias in node.names
        )

        self.assertFalse(
            any(module_name.startswith("scripts") for module_name in imported_modules)
        )


if __name__ == "__main__":
    unittest.main()
