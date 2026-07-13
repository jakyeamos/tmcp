from __future__ import annotations

import ast
import unittest
from pathlib import Path

import tmcp_runtime.services.diagnostics as diagnostics
from tmcp_runtime.services.diagnostics import (
    build_doctor_report,
    build_status_report,
)


class TmcpDiagnosticsServiceTests(unittest.TestCase):
    def test_doctor_assembles_checks_and_codex_guidance(self) -> None:
        result = build_doctor_report(
            "codex",
            "[REDACTED:path]",
            plugin_root_exists=True,
            node_launcher_exists=True,
            node_available=True,
            python_server_exists=True,
            python_available=True,
            artifact_persistence=True,
            aios_available=True,
            aios_root_display="[REDACTED:aios]",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            [check["id"] for check in result["checks"]],
            [
                "plugin_root",
                "node_launcher",
                "node_runtime",
                "python_server",
                "python_runtime",
                "secure_artifact_persistence",
                "aios_adapter",
            ],
        )
        self.assertEqual(result["plugin_root"], "[REDACTED:path]")
        self.assertEqual(
            result["codex_tool_discovery"]["codex_mcp_config"]["mcp_servers"]["tmcp"][
                "cwd"
            ],
            "[REDACTED:path]",
        )
        self.assertIn("[REDACTED:aios]", result["checks"][-1]["detail"])

    def test_doctor_failures_drive_next_action_but_limited_is_not_failure(self) -> None:
        result = build_doctor_report(
            "plain_mcp",
            "/plugin",
            plugin_root_exists=True,
            node_launcher_exists=False,
            node_available=True,
            python_server_exists=True,
            python_available=True,
            artifact_persistence=False,
            aios_available=False,
            aios_root_display=None,
        )

        self.assertFalse(result["ok"])
        self.assertIn("Fix failing checks", result["next_action"])
        self.assertIsNone(result["codex_tool_discovery"])
        statuses = {check["id"]: check["status"] for check in result["checks"]}
        self.assertEqual(statuses["secure_artifact_persistence"], "limited")
        self.assertEqual(statuses["aios_adapter"], "optional")

    def test_status_capability_and_aios_projection(self) -> None:
        result = build_status_report(
            "/plugin",
            False,
            False,
            aios_root_display=None,
        )

        self.assertTrue(result["ok"])
        self.assertNotIn("artifact_write", result["standalone"]["capabilities"])
        self.assertFalse(result["aios_adapter"]["configured"])
        self.assertIsNone(result["aios_adapter"]["aios_root"])

        enabled = build_status_report(
            "/plugin",
            True,
            True,
            aios_root_display="[REDACTED:aios]",
        )
        self.assertIn("artifact_write", enabled["standalone"]["capabilities"])
        self.assertEqual(enabled["aios_adapter"]["aios_root"], "[REDACTED:aios]")
        self.assertTrue(enabled["aios_adapter"]["configured"])

    def test_service_has_no_filesystem_or_script_imports(self) -> None:
        source_path = Path(diagnostics.__file__ or "")
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
        self.assertFalse(
            any(module.startswith("scripts") for module in imported_modules)
        )
        self.assertFalse(
            any(module in {"os", "pathlib", "shutil"} for module in imported_modules)
        )


if __name__ == "__main__":
    unittest.main()
