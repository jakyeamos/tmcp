from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.storage import artifact_persistence_available


class TmcpArtifactWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_default_promotion_directory_uses_a_slugged_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            (root / "SKILL.md").write_text(
                "# Release Readiness\n\nUse release checks and package verification.\n",
                encoding="utf-8",
            )
            result = self.server._call_tool(
                "tmcp_promote_harvest",
                {
                    "source_path": str(root),
                    "candidate_workflows": ["release_readiness"],
                    "selected_workflows": ["release_readiness_workflow"],
                    "min_confidence": 0.1,
                    "promotion_name": "../../outside",
                    "persist_global": False,
                },
            )

            output_dir = root / ".tmcp" / "promoted-harvests" / "outside"

            self.assertTrue(result["artifact_paths"])
            self.assertTrue((output_dir / "promotion-graph.json").exists())
            self.assertFalse((root / "outside").exists())

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_receipt_redacts_direct_values_and_uses_a_safe_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secret = "sk-" + "S" * 40
            tmcp_home = Path(tmp) / "tmcp-home"
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                result = self.server._call_tool(
                    "tmcp_record_receipt",
                    {
                        "packet_id": secret,
                        "commands_run": [f"deploy --token {secret}"],
                        "user_overrides": [secret],
                        "outcome": secret,
                    },
                )
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

            receipt_path = Path(result["artifact_paths"]["receipt_json"])
            receipt_text = receipt_path.read_text(encoding="utf-8")

        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, receipt_text)
        self.assertNotIn(secret, receipt_path.name)
        self.assertIn("[REDACTED:", receipt_text)
        self.assertGreater(result["redaction_summary"].get("openai_key", 0), 0)

    def test_global_cache_read_redacts_legacy_payload_and_skips_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            secret = "sk-" + "G" * 40
            tmcp_home = sandbox / "tmcp-home"
            cache_dir = tmcp_home / "promoted-harvests" / "safe"
            cache_dir.mkdir(parents=True)
            graph_path = cache_dir / "promotion-graph.json"
            graph_path.write_text(
                json.dumps({"schema": "legacy", "secret": secret}),
                encoding="utf-8",
            )
            outside = sandbox / "outside"
            outside.mkdir()
            (outside / "promotion-graph.json").write_text(
                json.dumps({"schema": "legacy", "secret": "EXTERNAL_ONLY"}),
                encoding="utf-8",
            )
            linked_dir = tmcp_home / "promoted-harvests" / "linked"
            try:
                linked_dir.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"Symlinks are unavailable in this environment: {exc}")
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                graphs, warnings = self.server._load_global_promoted_graphs("global")
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

        serialized = json.dumps({"graphs": graphs, "warnings": warnings})
        self.assertEqual(len(graphs), 1)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("EXTERNAL_ONLY", serialized)
        self.assertIn("[REDACTED:", serialized)
