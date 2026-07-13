from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tmcp_runtime.services import recommendations


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = PLUGIN_ROOT / "tmcp_runtime" / "services" / "recommendations.py"


def _harvest_result() -> dict[str, object]:
    return {
        "schema": "tmcp-harvest-result-v0.1",
        "source_paths": ["/tmp/project"],
        "source_count": 1,
        "matched_source_count": 1,
        "redaction_summary": {},
        "warnings": [],
        "source_nodes": [
            {
                "path": "/tmp/project/SKILL.md",
                "relative_path": "SKILL.md",
                "title": "UI Review",
                "source_type": "skill_definition",
                "frontmatter": {},
                "behavior_atoms": [
                    "artifact-contract",
                    "concrete-citations",
                    "evidence-backed-claims",
                ],
                "guidance_labels": [{"id": "ui:browser-verification"}],
                "keywords": ["buttons", "responsive", "screenshot"],
                "excerpt": "Use buttons, responsive layout, and screenshot evidence.",
                "signal_excerpt": "Use buttons, responsive layout, and screenshot evidence.",
            }
        ],
    }


class RecommendationServiceTests(unittest.TestCase):
    def test_service_forwards_advisories_and_ranks_filtered_candidates(self) -> None:
        source_advisories = Mock(return_value=[])
        with patch.object(
            recommendations,
            "harvest_skills",
            return_value=_harvest_result(),
        ) as harvest_skills:
            result = recommendations.recommend_workflows(
                {
                    "objective": "Review the responsive UI controls.",
                    "candidate_workflows": ["ui_quality"],
                    "min_confidence": 0.1,
                    "write_artifacts": True,
                },
                source_advisories=source_advisories,
            )

        harvest_arguments = harvest_skills.call_args.args[0]
        self.assertFalse(harvest_arguments["write_artifacts"])
        self.assertIs(
            harvest_skills.call_args.kwargs["source_advisories"],
            source_advisories,
        )
        self.assertEqual(
            [item["id"] for item in result["recommended_workflows"]],
            ["expert_ui_rubric_workflow"],
        )
        self.assertNotIn("composed_packet", result)

    def test_compose_preview_runs_only_when_requested(self) -> None:
        preview = Mock(return_value={"schema": "tmcp-composed-packet-v0.1"})
        with patch.object(
            recommendations,
            "harvest_skills",
            return_value=_harvest_result(),
        ):
            without_compose = recommendations.recommend_workflows(
                {"candidate_workflows": ["ui_quality"]},
                compose_preview=preview,
            )
            with_compose = recommendations.recommend_workflows(
                {"candidate_workflows": ["ui_quality"], "compose": True},
                compose_preview=preview,
            )

        preview.assert_called_once_with()
        self.assertNotIn("composed_packet", without_compose)
        self.assertEqual(
            with_compose["composed_packet"]["schema"],
            "tmcp-composed-packet-v0.1",
        )

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
