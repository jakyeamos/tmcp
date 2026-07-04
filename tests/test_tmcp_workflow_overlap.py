from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers


class TmcpWorkflowOverlapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_recommend_workflows_labels_non_ui_skill_contributions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "RELEASE.md").write_text(
                "\n".join(
                    [
                        "# Release Readiness",
                        "Release readiness requires CI evidence, package checks, version evidence, changelog review, and rollback notes.",
                        "Keep verification gates and ordered remediation actions explicit before ship decisions.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["release_readiness"],
                    "min_confidence": 0.1,
                },
            )

        self.assertTrue(result["ok"])
        recommendation = result["recommended_workflows"][0]
        guidance_label_ids = {
            label["id"]
            for evidence in recommendation["evidence"]
            for label in evidence["guidance_labels"]
        }
        self.assertIn("release:readiness", guidance_label_ids)
        self.assertIn("verification:gates", guidance_label_ids)
        source_map_label_ids = {
            label["id"]
            for node in result["adaptive_workflow_pack"]["harvested_source_map"]
            for label in node["guidance_labels"]
        }
        self.assertIn("release:readiness", source_map_label_ids)

    def test_adaptive_workflow_pack_reports_overlapping_source_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "release").mkdir(parents=True)
            (root / "docs").mkdir()
            (root / "skills" / "release" / "SKILL.md").write_text(
                "# Release Skill\n\nUse release readiness with CI evidence, package checks, changelog review, and version evidence.",
                encoding="utf-8",
            )
            (root / "docs" / "release.md").write_text(
                "# Release Checklist\n\nRelease readiness needs CI verification, package checks, rollback notes, and changelog review.",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["release_readiness"],
                    "min_confidence": 0.1,
                },
            )

        self.assertTrue(result["ok"])
        overlap = result["adaptive_workflow_pack"]["overlap_analysis"]
        clusters = overlap["clusters"]
        release_cluster = next(
            cluster for cluster in clusters if cluster["label_id"] == "release:readiness"
        )
        self.assertEqual(release_cluster["source_count"], 2)
        self.assertEqual(release_cluster["recommended_action"], "consolidate_or_rank")
        self.assertEqual(
            release_cluster["decision_rule"],
            "Prefer the highest-priority local source when labels duplicate; preserve distinct matched terms as supporting context.",
        )


if __name__ == "__main__":
    unittest.main()
