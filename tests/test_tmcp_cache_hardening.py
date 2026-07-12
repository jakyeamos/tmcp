from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_tmcp_mcp_server as helpers


class TmcpCacheHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    @staticmethod
    def _graph_payload(workflow_nodes: list[dict[str, object]]) -> dict[str, object]:
        return {
            "schema": "tmcp-promoted-harvest-graph-v0.1",
            "promotion_name": "cache-test",
            "created_at": "2026-07-11T00:00:00+00:00",
            "source_nodes": [],
            "behavior_atoms": [],
            "workflow_nodes": workflow_nodes,
            "edges": [],
            "trust": "advisory_untrusted",
        }

    @staticmethod
    def _receipt_payload(index: int) -> dict[str, object]:
        return {
            "schema": "tmcp-run-receipt-v0.1",
            "created_at": f"2026-07-11T00:00:{index:02d}+00:00",
            "packet_id": f"packet-{index}",
            "activated_atoms": [],
            "ignored_atoms": [],
            "commands_run": [],
            "verification_results": [],
            "user_overrides": [],
            "outcome": "passed",
            "trust": "advisory_untrusted",
            "instruction_override_policy": "Advisory only.",
        }

    def test_global_cache_projects_only_canonical_catalog_workflows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            source = sandbox / "source"
            tmcp_home = sandbox / "tmcp-home"
            source.mkdir()
            graph_path = (
                tmcp_home
                / "promoted-harvests"
                / "cache-test"
                / "promotion-graph.json"
            )
            graph_path.parent.mkdir(parents=True)
            graph_path.write_text(
                json.dumps(
                    self._graph_payload(
                        [
                            {
                                "id": "repo_behavior_spec_loop_workflow",
                                "signal_family": "malicious_override",
                                "behavior_atoms": ["MALICIOUS_ATOM"],
                                "active_instructions": ["MALICIOUS_INSTRUCTION"],
                            },
                            {
                                "id": "unknown_cache_workflow",
                                "signal_family": "repo_behavior_spec_loop",
                                "behavior_atoms": ["MALICIOUS_UNKNOWN_ATOM"],
                            },
                        ]
                    )
                ),
                encoding="utf-8",
            )
            original_home = self.server.TMCP_HOME
            self.server.TMCP_HOME = tmcp_home
            try:
                graphs, warnings = self.server._load_global_promoted_graphs("global")
                packet = self.server._call_tool(
                    "tmcp_compose_packet",
                    {
                        "source_path": str(source),
                        "project_path": str(source),
                        "objective": "run a repo behavior sweep",
                        "cache_policy": "global",
                    },
                )
            finally:
                self.server.TMCP_HOME = original_home

        self.assertEqual(len(graphs), 1)
        self.assertEqual(
            graphs[0]["workflow_nodes"],
            [{"id": "repo_behavior_spec_loop_workflow"}],
        )
        self.assertEqual(
            set(graphs[0]),
            {
                "schema",
                "promotion_name",
                "workflow_nodes",
                "_global_cache_path",
                "trust",
            },
        )
        self.assertTrue(any("unknown workflow IDs" in warning for warning in warnings))
        rendered = json.dumps({"graphs": graphs, "packet": packet})
        self.assertNotIn("MALICIOUS", rendered)
        self.assertIn("canonical spreadsheet", " ".join(packet["active_instructions"]).lower())

    def test_global_cache_rejects_deeply_nested_json_without_composition_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmcp_home = Path(tmp) / "tmcp-home"
            graph_path = (
                tmcp_home
                / "promoted-harvests"
                / "deep"
                / "promotion-graph.json"
            )
            graph_path.parent.mkdir(parents=True)
            graph_path.write_text(
                '{"nested":' + "[" * 2_000 + "0" + "]" * 2_000 + "}",
                encoding="utf-8",
            )
            original_home = self.server.TMCP_HOME
            self.server.TMCP_HOME = tmcp_home
            try:
                graphs, warnings = self.server._load_global_promoted_graphs("global")
            finally:
                self.server.TMCP_HOME = original_home

        self.assertEqual(graphs, [])
        self.assertTrue(
            any(
                "invalid global cache entry" in warning
                or "overly complex global cache entry" in warning
                for warning in warnings
            )
        )

    def test_global_cache_depth_bound_keeps_valid_entry_after_deep_junk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmcp_home = Path(tmp) / "tmcp-home"
            promoted_root = tmcp_home / "promoted-harvests"
            for index in range(80):
                junk_path = (
                    promoted_root
                    / "a-junk"
                    / f"nested-{index:03d}"
                    / "promotion-graph.json"
                )
                junk_path.parent.mkdir(parents=True)
                junk_path.write_text(
                    json.dumps(
                        self._graph_payload(
                            [{"id": "unknown_cache_workflow"}]
                        )
                    ),
                    encoding="utf-8",
                )
            valid_path = promoted_root / "z-valid" / "promotion-graph.json"
            valid_path.parent.mkdir(parents=True)
            valid_path.write_text(
                json.dumps(
                    self._graph_payload(
                        [{"id": "repo_behavior_spec_loop_workflow"}]
                    )
                ),
                encoding="utf-8",
            )
            original_home = self.server.TMCP_HOME
            self.server.TMCP_HOME = tmcp_home
            try:
                graphs, _ = self.server._load_global_promoted_graphs("global")
            finally:
                self.server.TMCP_HOME = original_home

        self.assertEqual(len(graphs), 1)
        self.assertEqual(
            graphs[0]["workflow_nodes"],
            [{"id": "repo_behavior_spec_loop_workflow"}],
        )

    def test_recent_receipts_limit_cache_reads_and_candidate_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmcp_home = Path(tmp) / "tmcp-home"
            receipt_dir = tmcp_home / "receipts" / "2026-07"
            receipt_dir.mkdir(parents=True)
            for index in range(80):
                (receipt_dir / f"receipt-{index:03d}.json").write_text(
                    json.dumps(self._receipt_payload(index)),
                    encoding="utf-8",
                )
            original_home = self.server.TMCP_HOME
            original_read = self.server.read_harvest_text
            self.server.TMCP_HOME = tmcp_home
            try:
                with patch.object(
                    self.server,
                    "read_harvest_text",
                    wraps=original_read,
                ) as read_harvest_text:
                    receipts, warnings = self.server._load_recent_receipts(
                        "global",
                        limit=5,
                    )
            finally:
                self.server.TMCP_HOME = original_home

        self.assertEqual(len(receipts), 5)
        self.assertLessEqual(read_harvest_text.call_count, 5)
        self.assertTrue(any("candidate limit" in warning for warning in warnings))

    def test_compose_packet_redacts_tmcp_home_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secret = "sk-" + "H" * 40
            source = Path(tmp) / "source"
            source.mkdir()
            original_home = self.server.TMCP_HOME
            self.server.TMCP_HOME = Path(tmp) / secret
            try:
                packet = self.server._call_tool(
                    "tmcp_compose_packet",
                    {
                        "source_path": str(source),
                        "project_path": str(source),
                        "objective": "review cache safety",
                        "cache_policy": "none",
                    },
                )
            finally:
                self.server.TMCP_HOME = original_home

        self.assertNotIn(secret, json.dumps(packet))
        self.assertIn("[REDACTED:", packet["global_cache"]["tmcp_home"])
