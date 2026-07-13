from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.storage import artifact_persistence_available


def _symlink_or_skip(test_case: unittest.TestCase, link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (NotImplementedError, OSError) as exc:
        test_case.skipTest(f"Symlinks are unavailable in this environment: {exc}")


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

            output_dir = Path(result["artifact_paths"]["promotion_graph_json"]).parent

            self.assertTrue(result["artifact_paths"])
            self.assertTrue((output_dir / "promotion-graph.json").exists())
            self.assertEqual(
                output_dir.parent.resolve(),
                (root / ".tmcp" / "promoted-harvests").resolve(),
            )
            self.assertTrue(output_dir.name.startswith("outside-"))
            self.assertFalse((root / "outside").exists())

    def test_default_recommendation_and_promotion_never_write_through_source_link(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            real_root = sandbox / "real-project"
            source_link = sandbox / "project-link"
            real_root.mkdir()
            (real_root / "SKILL.md").write_text(
                "# Release Readiness\n\nUse release checks and package verification.\n",
                encoding="utf-8",
            )
            _symlink_or_skip(self, source_link, real_root)

            with self.assertRaisesRegex(ValueError, "provide output_dir"):
                self.server._call_tool(
                    "expert_rubric_review_plan",
                    {
                        "objective": "Review release safety",
                        "project_path": str(source_link),
                        "harvest_sources": False,
                    },
                )
            with self.assertRaisesRegex(ValueError, "provide output_dir"):
                self.server._call_tool(
                    "tmcp_recommend_workflows",
                    {
                        "source_path": str(source_link),
                        "follow_symlinks": True,
                        "candidate_workflows": ["release_readiness"],
                        "min_confidence": 0.1,
                        "write_artifacts": True,
                    },
                )
            with self.assertRaisesRegex(ValueError, "provide output_dir"):
                self.server._call_tool(
                    "tmcp_promote_harvest",
                    {
                        "source_path": str(source_link),
                        "follow_symlinks": True,
                        "candidate_workflows": ["release_readiness"],
                        "selected_workflows": ["release_readiness_workflow"],
                        "min_confidence": 0.1,
                        "persist_global": False,
                    },
                )

            self.assertFalse((real_root / ".tmcp").exists())
            self.assertFalse((real_root / ".aios").exists())

    def test_no_promotable_selection_does_not_persist_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            output_dir = Path(tmp) / "promotion"
            root.mkdir()
            (root / "SKILL.md").write_text(
                "# Unrelated\n\nDocument a local convention.\n",
                encoding="utf-8",
            )

            result = self.server._call_tool(
                "tmcp_promote_harvest",
                {
                    "source_path": str(root),
                    "selected_workflows": ["does-not-exist"],
                    "output_dir": str(output_dir),
                },
            )
            output_exists = output_dir.exists()

        self.assertEqual(result["status"], "no_promotable_workflows")
        self.assertFalse(result["ok"])
        self.assertEqual(result["artifact_paths"], {})
        self.assertEqual(result["global_artifact_paths"], {})
        self.assertFalse(output_exists)

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

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_receipt_directory_uses_the_receipt_timestamp_month(self) -> None:
        created_at = "2026-08-01T00:00:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            tmcp_home = Path(tmp) / "tmcp-home"
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                with patch.object(self.server, "_now_iso", return_value=created_at):
                    result = self.server._record_receipt(
                        {"packet_id": "packet-123", "outcome": "passed"}
                    )
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

            receipt_path = Path(result["artifact_paths"]["receipt_json"])
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

        self.assertEqual(receipt_path.parent.name, "2026-08")
        self.assertEqual(receipt["created_at"], created_at)

    def test_global_cache_rejects_legacy_payloads_and_skips_symlinks(self) -> None:
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
        self.assertEqual(graphs, [])
        self.assertNotIn(secret, serialized)
        self.assertNotIn("EXTERNAL_ONLY", serialized)
        self.assertTrue(any("unexpected schema" in warning for warning in warnings))
        self.assertTrue(any("symlink" in warning.lower() for warning in warnings))
