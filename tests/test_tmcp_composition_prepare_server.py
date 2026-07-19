from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import cast

from tests.tmcp_test_client import TestWorkspace


class CompositionPrepareServerTests(unittest.TestCase):
    def test_prepare_composition_is_available_over_mcp_without_writes(self) -> None:
        with TestWorkspace() as workspace:
            assert workspace.project is not None
            assert workspace.tmcp_home is not None
            (workspace.project / "AGENTS.md").write_text(
                "# Instructions\n\nRead before modifying. Verify focused tests.\n",
                encoding="utf-8",
            )
            for name, content in (
                ("review", "# Review\n\nInspect the implementation and verify behavior.\n"),
                ("generic", "# Generic\n\nUse the generic procedure.\n"),
            ):
                skill = workspace.project / "skills" / name / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text(content, encoding="utf-8")
            responses = workspace.run_mcp(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "tmcp_prepare_composition",
                            "arguments": {
                                "objective": "Implement and verify the change",
                                "project_path": str(workspace.project),
                                "source_path": str(workspace.project),
                                "include_all_active_source_slices": True,
                            },
                        },
                    }
                ]
            )

            result = cast(Mapping[str, object], responses[0]["result"])
            structured = cast(Mapping[str, object], result["structuredContent"])

            self.assertEqual(structured["schema"], "tmcp-composition-preflight-v0.1")
            self.assertEqual(
                cast(Mapping[str, object], structured["semantic_proposal_contract"])[
                    "schema"
                ],
                "tmcp-semantic-proposal-v0.1",
            )
            harvest_diagnostics = cast(
                Mapping[str, object], structured["harvest_diagnostics"]
            )
            self.assertTrue(harvest_diagnostics["ranked_before_limit"])
            source_roles = cast(Mapping[str, int], structured["source_roles"])
            self.assertEqual(source_roles["active_skill"], 2)
            self.assertEqual(list(workspace.tmcp_home.iterdir()), [])
