from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.storage.migrations as migrations
from tmcp_runtime.storage.migrations import migrate_legacy_promotion_summary


class StorageMigrationTests(unittest.TestCase):
    def test_legacy_summary_projects_nested_graph_without_mutation(self) -> None:
        payload = {
            "schema": "tmcp-global-promoted-harvest-v0.1",
            "promotion_name": "release",
            "created_at": "2026-07-13T12:00:00Z",
            "promotion_graph": {
                "created_at": "2026-07-13T12:00:00Z",
                "workflow_nodes": [{"id": "release_readiness_workflow"}],
                "edges": [],
            },
        }
        original_graph = dict(payload["promotion_graph"])

        migrated = migrate_legacy_promotion_summary(
            payload,
            graph_schema="tmcp-promoted-harvest-graph-v0.1",
        )

        self.assertEqual(migrated["schema"], "tmcp-promoted-harvest-graph-v0.1")
        self.assertEqual(migrated["promotion_name"], "release")
        self.assertEqual(migrated["trust"], "advisory_untrusted")
        self.assertEqual(payload["promotion_graph"], original_graph)

    def test_non_legacy_or_malformed_summary_is_not_migrated(self) -> None:
        self.assertIsNone(
            migrate_legacy_promotion_summary(
                {"schema": "tmcp-promoted-harvest-graph-v0.1"},
                graph_schema="tmcp-promoted-harvest-graph-v0.1",
            )
        )
        self.assertIsNone(
            migrate_legacy_promotion_summary(
                {
                    "schema": "tmcp-global-promoted-harvest-v0.1",
                    "promotion_graph": "not-an-object",
                },
                graph_schema="tmcp-promoted-harvest-graph-v0.1",
            )
        )

    def test_migration_module_has_no_filesystem_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(migrations))
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
            "os",
            "pathlib",
            "scripts",
            "shutil",
            "subprocess",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage.artifacts",
            "tmcp_runtime.storage.global_cache",
        )
        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in imported_modules
                for prefix in forbidden_prefixes
            )
        )


if __name__ == "__main__":
    unittest.main()
