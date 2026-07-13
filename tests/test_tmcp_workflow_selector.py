from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers


class TmcpWorkflowSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_ui_quality_evidence_requires_positive_ui_specific_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "handoff").mkdir(parents=True)
            (root / "skills" / "data").mkdir(parents=True)
            (root / "skills" / "ui").mkdir(parents=True)
            (root / "skills" / "handoff" / "SKILL.md").write_text(
                "\n".join(
                    [
                        "# Agent Handoff",
                        "Capture current state, touched files, blockers, open questions, and next commands.",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "skills" / "data" / "SKILL.md").write_text(
                "\n".join(
                    [
                        "# Data Integrity Audit",
                        "Use data integrity for schema migrations, invariants, reconciliation, and backfills.",
                        "Do not use this for generic performance or UI data-display work.",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "skills" / "ui" / "SKILL.md").write_text(
                "\n".join(
                    [
                        "# UI Rubric",
                        "Use screenshots, visual polish, design-system fit, responsive checks, browser verification, buttons, controls, and tooltips.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["ui_quality"],
                    "min_confidence": 0.1,
                },
            )

        recommendation = result["recommended_workflows"][0]
        evidence_paths = {
            evidence["relative_path"] for evidence in recommendation["evidence"]
        }
        self.assertEqual(evidence_paths, {"skills/ui/SKILL.md"})

        source_labels = {
            node["relative_path"]: {label["id"] for label in node["guidance_labels"]}
            for node in result["adaptive_workflow_pack"]["harvested_source_map"]
        }
        self.assertNotIn("performance:readiness", source_labels["skills/data/SKILL.md"])

    def test_workflow_evidence_prefers_matching_guidance_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "tmcp-dx-audit").mkdir(parents=True)
            (root / "skills" / "tmcp-release-readiness").mkdir(parents=True)
            (root / "skills" / "tmcp-dx-audit" / "SKILL.md").write_text(
                "\n".join(
                    [
                        "# Developer Experience Audit",
                        "Review onboarding, CI clarity, package metadata, and separate verification evidence.",
                        "## Output Contract",
                        "Ordered actions and quality findings.",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "skills" / "tmcp-release-readiness" / "SKILL.md").write_text(
                "\n".join(
                    [
                        "# Release Readiness",
                        "Review release and ship decisions with CI status and verification evidence.",
                        "## Output Contract",
                        "Ordered remediation slices.",
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

        recommendation = result["recommended_workflows"][0]
        self.assertEqual(
            recommendation["evidence"][0]["relative_path"],
            "skills/tmcp-release-readiness/SKILL.md",
        )


if __name__ == "__main__":
    unittest.main()
