from __future__ import annotations

import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tmcp_runtime.storage.global_cache as global_cache
from tmcp_runtime.storage.global_cache import read_global_cache_snapshot


GRAPH_SCHEMA = "tmcp-promoted-harvest-graph-v0.1"
RECEIPT_SCHEMA = "tmcp-run-receipt-v0.1"


def _graph_payload() -> dict[str, object]:
    return {
        "schema": GRAPH_SCHEMA,
        "promotion_name": "release",
        "created_at": "2026-07-12T00:00:00Z",
        "source_nodes": [],
        "behavior_atoms": [],
        "workflow_nodes": [
            {"id": "release_readiness_workflow"},
            {"id": "unknown_workflow", "active_instructions": ["MALICIOUS"]},
        ],
        "edges": [],
        "trust": "advisory_untrusted",
    }


def _receipt_payload(packet_id: str) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "created_at": "2026-07-12T00:00:00Z",
        "packet_id": packet_id,
        "activated_atoms": [],
        "ignored_atoms": [],
        "commands_run": [],
        "verification_results": [],
        "user_overrides": [],
        "outcome": "passed",
        "trust": "advisory_untrusted",
        "instruction_override_policy": "Advisory only.",
    }


def _legacy_summary_payload() -> dict[str, object]:
    return {
        "schema": "tmcp-global-promoted-harvest-v0.1",
        "promotion_name": "legacy-release",
        "created_at": "2026-07-12T00:00:00Z",
        "promotion_graph": {
            "source_nodes": [],
            "behavior_atoms": [],
            "workflow_nodes": [{"id": "release_readiness_workflow"}],
            "edges": [],
        },
        "trust": "advisory_untrusted",
    }


class GlobalCacheReaderTests(unittest.TestCase):
    def _snapshot(self, root: Path, *, receipt_limit: object = 25):
        return read_global_cache_snapshot(
            promoted_root=root / "promoted-harvests",
            receipts_root=root / "receipts",
            cache_policy="global",
            graph_schema=GRAPH_SCHEMA,
            receipt_schema=RECEIPT_SCHEMA,
            known_workflow_ids={"release_readiness_workflow"},
            receipt_limit=receipt_limit,
        )

    def test_non_global_policy_does_not_probe_cache_roots(self) -> None:
        with patch.object(global_cache, "_safe_global_cache_entries") as entries:
            snapshot = read_global_cache_snapshot(
                promoted_root=Path("/not-read/promoted-harvests"),
                receipts_root=Path("/not-read/receipts"),
                cache_policy="globla",
                graph_schema=GRAPH_SCHEMA,
                receipt_schema=RECEIPT_SCHEMA,
                known_workflow_ids=set(),
            )

        entries.assert_not_called()
        self.assertEqual(snapshot.promoted_graphs, ())
        self.assertEqual(snapshot.receipts, ())
        self.assertEqual(snapshot.warnings, ())

    def test_reader_returns_only_redacted_canonical_projections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph_path = (
                root
                / "promoted-harvests"
                / "release"
                / "promotion-graph.json"
            )
            receipt_path = root / "receipts" / "2026-07" / "receipt.json"
            graph_path.parent.mkdir(parents=True)
            receipt_path.parent.mkdir(parents=True)
            graph_path.write_text(json.dumps(_graph_payload()), encoding="utf-8")
            secret = "sk-" + "A" * 40
            receipt_path.write_text(
                json.dumps(_receipt_payload(secret)),
                encoding="utf-8",
            )

            snapshot = self._snapshot(root)

        self.assertEqual(
            snapshot.promoted_graphs,
            (
                {
                    "schema": GRAPH_SCHEMA,
                    "promotion_name": "release",
                    "workflow_nodes": [{"id": "release_readiness_workflow"}],
                    "_global_cache_path": str(graph_path),
                    "trust": "advisory_untrusted",
                },
            ),
        )
        self.assertEqual(len(snapshot.receipts), 1)
        rendered = json.dumps(snapshot.__dict__)
        self.assertNotIn(secret, rendered)
        self.assertNotIn("MALICIOUS", rendered)
        self.assertTrue(any("unknown workflow IDs" in item for item in snapshot.warnings))

    def test_reader_orders_receipts_by_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt_dir = root / "receipts" / "2026-07"
            receipt_dir.mkdir(parents=True)
            older = receipt_dir / "older.json"
            newer = receipt_dir / "newer.json"
            older.write_text(json.dumps(_receipt_payload("older")), encoding="utf-8")
            newer.write_text(json.dumps(_receipt_payload("newer")), encoding="utf-8")
            os.utime(older, ns=(1_700_000_000_000_000_000,) * 2)
            os.utime(newer, ns=(1_700_000_001_000_000_000,) * 2)

            snapshot = self._snapshot(root)

        self.assertEqual(
            [item["packet_id"] for item in snapshot.receipts],
            ["newer", "older"],
        )

    def test_reader_migrates_legacy_summary_when_graph_file_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = (
                root
                / "promoted-harvests"
                / "legacy-release"
                / "promoted-harvest.json"
            )
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps(_legacy_summary_payload()),
                encoding="utf-8",
            )

            snapshot = self._snapshot(root)

        self.assertEqual(len(snapshot.promoted_graphs), 1)
        self.assertEqual(
            snapshot.promoted_graphs[0]["promotion_name"],
            "legacy-release",
        )
        self.assertEqual(
            snapshot.promoted_graphs[0]["_global_cache_path"],
            str(summary_path),
        )

    def test_current_graph_file_wins_over_legacy_summary_in_same_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "promoted-harvests" / "release"
            directory.mkdir(parents=True)
            (directory / "promotion-graph.json").write_text(
                json.dumps(_graph_payload()),
                encoding="utf-8",
            )
            legacy = _legacy_summary_payload()
            legacy["promotion_name"] = "legacy-duplicate"
            (directory / "promoted-harvest.json").write_text(
                json.dumps(legacy),
                encoding="utf-8",
            )

            snapshot = self._snapshot(root)

        self.assertEqual(len(snapshot.promoted_graphs), 1)
        self.assertEqual(snapshot.promoted_graphs[0]["promotion_name"], "release")

    def test_reader_has_no_adapter_or_write_authority(self) -> None:
        source_path = Path(global_cache.__file__ or "")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden_prefixes = (
            "scripts",
            "subprocess",
            "tmcp_runtime.storage.artifacts",
            "tmcp_runtime.storage.sessions",
        )

        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in imported_modules
                for prefix in forbidden_prefixes
            )
        )
        self.assertTrue(
            {
                "tmcp_runtime.safety",
                "tmcp_runtime.storage.cache_policy",
            }.issubset(imported_modules)
        )
        self.assertFalse(
            any(
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr == "environ"
                for node in ast.walk(tree)
            )
        )


if __name__ == "__main__":
    unittest.main()
