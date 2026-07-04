from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers


class TmcpFileRootHarvestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_harvest_file_roots_keep_distinct_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alpha = root / "alpha" / "SKILL.md"
            beta = root / "beta" / "SKILL.md"
            alpha.parent.mkdir(parents=True)
            beta.parent.mkdir(parents=True)
            alpha.write_text(
                "# Alpha Skill\n\nUse tests and verification evidence for alpha workflows.\n",
                encoding="utf-8",
            )
            beta.write_text(
                "# Beta Skill\n\nUse tests and verification evidence for beta workflows.\n",
                encoding="utf-8",
            )

            harvest = self.server._harvest_skills(
                {
                    "source_paths": [str(alpha), str(beta)],
                    "limit": 10,
                }
            )
            promotion = self.server._call_tool(
                "tmcp_promote_harvest",
                {
                    "source_paths": [str(alpha), str(beta)],
                    "min_confidence": 0.1,
                    "write_artifacts": False,
                },
            )

        harvested_paths = {node["relative_path"] for node in harvest["source_nodes"]}
        self.assertEqual(harvested_paths, {"alpha/SKILL.md", "beta/SKILL.md"})

        graph_paths = {
            node["relative_path"]
            for node in promotion["promotion_graph"]["source_nodes"]
        }
        self.assertEqual(graph_paths, {"alpha/SKILL.md", "beta/SKILL.md"})
        edge_sources = {
            edge["from"]
            for edge in promotion["promotion_graph"]["edges"]
            if edge["relation"] == "declares_behavior_atom"
        }
        self.assertTrue({"alpha/SKILL.md", "beta/SKILL.md"}.issubset(edge_sources))


if __name__ == "__main__":
    unittest.main()
