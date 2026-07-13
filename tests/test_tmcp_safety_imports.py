from __future__ import annotations

import ast
import unittest
from pathlib import Path


class RuntimeSafetyImportTests(unittest.TestCase):
    def test_runtime_safety_owns_redaction_without_script_imports(self) -> None:
        safety_root = Path(__file__).resolve().parents[1] / "tmcp_runtime" / "safety"
        imported_modules: set[str] = set()
        for path in safety_root.glob("*.py"):
            module = ast.parse(path.read_text(encoding="utf-8"))
            imported_modules.update(
                node.module or ""
                for node in ast.walk(module)
                if isinstance(node, ast.ImportFrom)
            )
            imported_modules.update(
                alias.name
                for node in ast.walk(module)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
        self.assertFalse(
            any(module.startswith("scripts") for module in imported_modules)
        )


if __name__ == "__main__":
    unittest.main()
