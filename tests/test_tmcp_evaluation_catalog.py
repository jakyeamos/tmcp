from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

import tmcp_runtime.services.evaluation_catalog as evaluation_catalog


class EvaluationCatalogTests(unittest.TestCase):
    def test_catalog_owns_public_evaluator_policy_data(self) -> None:
        self.assertEqual(evaluation_catalog.DEFAULT_VARIANTS[0], "baseline")
        self.assertIn("static_review", evaluation_catalog.EVIDENCE_LEVELS)
        self.assertNotIn("deprecated", evaluation_catalog.EVIDENCE_LEVELS)
        self.assertIn("deprecated", evaluation_catalog.PATTERN_LIFECYCLE_STATUSES)
        self.assertIn(
            "verification.vague-quality-language",
            {item["pattern_id"] for item in evaluation_catalog.V01_ANTI_PATTERNS},
        )
        self.assertIn(
            "verification.concrete-command",
            {item["pattern_id"] for item in evaluation_catalog.EFFECTIVE_PATTERNS},
        )

    def test_service_has_no_filesystem_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(evaluation_catalog))
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
            "datetime",
            "os",
            "pathlib",
            "scripts",
            "shutil",
            "subprocess",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
            "uuid",
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
