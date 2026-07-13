from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_tmcp_mcp_server as helpers
import tmcp_runtime.storage.global_cache as global_cache


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
            "created_at": (
                f"2026-07-11T00:{index // 60:02d}:{index % 60:02d}+00:00"
            ),
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
                snapshot = self.server._global_cache_snapshot("global")
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

        graphs = list(snapshot.promoted_graphs)
        warnings = list(snapshot.warnings)
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

    def test_composition_ignores_global_cache_without_explicit_opt_in(self) -> None:
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
                        [{"id": "repo_behavior_spec_loop_workflow"}]
                    )
                ),
                encoding="utf-8",
            )
            original_home = self.server.TMCP_HOME
            self.server.TMCP_HOME = tmcp_home
            try:
                default_packet = self.server._call_tool(
                    "tmcp_compose_packet",
                    {
                        "source_path": str(source),
                        "project_path": str(source),
                        "objective": "run a repo behavior sweep",
                    },
                )
                invalid_policy_packet = self.server._call_tool(
                    "tmcp_compose_packet",
                    {
                        "source_path": str(source),
                        "project_path": str(source),
                        "objective": "run a repo behavior sweep",
                        "cache_policy": "globla",
                    },
                )
                opted_in_packet = self.server._call_tool(
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

        self.assertEqual(default_packet["global_cache"]["cache_policy"], "none")
        self.assertEqual(default_packet["global_cache"]["promoted_graph_count"], 0)
        self.assertNotIn(
            "canonical spreadsheet",
            " ".join(default_packet["active_instructions"]).lower(),
        )
        self.assertEqual(invalid_policy_packet["global_cache"]["cache_policy"], "none")
        self.assertEqual(invalid_policy_packet["global_cache"]["promoted_graph_count"], 0)
        self.assertNotIn(
            "canonical spreadsheet",
            " ".join(invalid_policy_packet["active_instructions"]).lower(),
        )
        self.assertGreaterEqual(opted_in_packet["global_cache"]["promoted_graph_count"], 1)
        self.assertIn(
            "canonical spreadsheet",
            " ".join(opted_in_packet["active_instructions"]).lower(),
        )

    def test_unknown_cache_policy_does_not_read_global_artifacts(self) -> None:
        with patch.object(global_cache, "_safe_global_cache_entries") as entries:
            snapshot = self.server._global_cache_snapshot("globla")

        entries.assert_not_called()
        self.assertEqual(snapshot.promoted_graphs, ())
        self.assertEqual(snapshot.receipts, ())
        self.assertEqual(snapshot.warnings, ())

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
                snapshot = self.server._global_cache_snapshot("global")
            finally:
                self.server.TMCP_HOME = original_home

        graphs = list(snapshot.promoted_graphs)
        warnings = list(snapshot.warnings)
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
                snapshot = self.server._global_cache_snapshot("global")
            finally:
                self.server.TMCP_HOME = original_home

        graphs = list(snapshot.promoted_graphs)
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
            self.server.TMCP_HOME = tmcp_home
            try:
                with patch.object(
                    global_cache,
                    "read_harvest_text",
                    wraps=global_cache.read_harvest_text,
                ) as read_harvest_text:
                    snapshot = self.server._global_cache_snapshot(
                        "global",
                        receipt_limit=5,
                    )
            finally:
                self.server.TMCP_HOME = original_home

        receipts = list(snapshot.receipts)
        warnings = list(snapshot.warnings)
        self.assertEqual(len(receipts), 5)
        self.assertLessEqual(read_harvest_text.call_count, 5)
        self.assertTrue(any("candidate limit" in warning for warning in warnings))

    def test_global_cache_skips_receipts_with_invalid_semantic_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmcp_home = Path(tmp) / "tmcp-home"
            receipt_dir = tmcp_home / "receipts" / "2026-07"
            receipt_dir.mkdir(parents=True)
            valid = self._receipt_payload(1)
            invalid = self._receipt_payload(2)
            secret = "sk-" + "R" * 40
            invalid["packet_id"] = secret
            invalid["created_at"] = "2026-07-11T00:00:02"
            (receipt_dir / "valid.json").write_text(
                json.dumps(valid),
                encoding="utf-8",
            )
            (receipt_dir / "invalid.json").write_text(
                json.dumps(invalid),
                encoding="utf-8",
            )
            original_home = self.server.TMCP_HOME
            self.server.TMCP_HOME = tmcp_home
            try:
                snapshot = self.server._global_cache_snapshot("global")
            finally:
                self.server.TMCP_HOME = original_home

        receipts = list(snapshot.receipts)
        warnings = list(snapshot.warnings)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["packet_id"], "packet-1")
        rendered = json.dumps({"receipts": receipts, "warnings": warnings})
        self.assertNotIn(secret, rendered)
        self.assertTrue(any("invalid metadata" in warning for warning in warnings))

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
