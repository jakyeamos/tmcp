from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.explain as explain_service
from tmcp_runtime.services.explain import ExplainService, ExplainServiceContext


class ExplainServiceTests(unittest.TestCase):
    def test_standalone_builds_packet_and_optional_compose_preview(self) -> None:
        composed_arguments: list[dict[str, object]] = []
        service = ExplainService(
            ExplainServiceContext(
                compose_packet=lambda arguments: (
                    composed_arguments.append(arguments)
                    or {"schema": "tmcp-composed-packet-v0.1"}
                )
            )
        )

        result = service.standalone(
            {
                "objective": "Review release safety",
                "project_path": "/project",
                "phase": "planning",
                "domain": "release",
                "compose": True,
            }
        )

        self.assertEqual(result["command"], "tmcp-explain")
        self.assertEqual(result["packet"]["project_path"], "/project")
        self.assertEqual(
            composed_arguments,
            [
                {
                    "objective": "Review release safety",
                    "project_path": "/project",
                    "source_path": "/project",
                    "phase": "planning",
                    "cache_policy": "none",
                }
            ],
        )

    def test_service_has_no_adapter_or_persistence_imports(self) -> None:
        source_path = Path(inspect.getfile(explain_service))
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
            "scripts",
            "shutil",
            "subprocess",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
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
