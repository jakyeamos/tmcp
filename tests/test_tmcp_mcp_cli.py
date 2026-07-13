from __future__ import annotations

import ast
import json
import subprocess
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers
from tests.tmcp_test_client import TestWorkspace
from tmcp_runtime.api import cli


PLUGIN_ROOT = helpers.PLUGIN_ROOT


class TmcpMcpCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_launcher_prefers_windows_python_launcher_on_windows(self) -> None:
        completed = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                (
                    "import { pythonCandidates } from './scripts/tmcp_launcher.mjs';"
                    "console.log(JSON.stringify(pythonCandidates({}, 'win32')));"
                ),
            ],
            cwd=PLUGIN_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        candidates = json.loads(completed.stdout)
        self.assertEqual(candidates[0]["command"], "py")
        self.assertEqual(candidates[0]["args"], ["-3"])

    def test_launcher_respects_explicit_python_env(self) -> None:
        completed = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                (
                    "import { pythonCandidates } from './scripts/tmcp_launcher.mjs';"
                    "console.log(JSON.stringify(pythonCandidates({ TMCP_PYTHON: '/opt/Python 3/python.exe' }, 'win32')));"
                ),
            ],
            cwd=PLUGIN_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        candidates = json.loads(completed.stdout)
        self.assertEqual(candidates[0]["command"], "/opt/Python 3/python.exe")
        self.assertEqual(candidates[0]["source"], "TMCP_PYTHON")

    def test_launcher_cli_status_calls_tool_directly(self) -> None:
        with TestWorkspace() as workspace:
            completed = workspace.run_cli(["status"])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["standalone"]["available"])
        self.assertIn("workflow_recommendation", payload["standalone"]["capabilities"])
        self.assertIn("artifact_persistence", payload["standalone"])

    def test_launcher_cli_explain_accepts_positional_objective(self) -> None:
        with TestWorkspace() as workspace:
            completed = workspace.run_cli(
                [
                    "explain",
                    "Use the TMCP expert UI rubric on Hoopscout",
                    "--project-path",
                    "/tmp/hoopscout",
                    "--adapter",
                    "standalone",
                ]
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["adapter"], "standalone")
        self.assertEqual(payload["packet"]["task_id"], "audit")

    def test_adapter_uses_the_runtime_cli_parser(self) -> None:
        self.assertIs(self.server._parse_cli_arguments, cli.parse_cli_arguments)

    def test_runtime_cli_parser_preserves_session_ids_and_rejects_invalid_json(self) -> None:
        _, arguments, _ = cli.parse_cli_arguments(
            [
                "compose-packet",
                "Improve the dashboard UI",
                "--session-id",
                "00123",
            ]
        )

        self.assertEqual(arguments["session_id"], "00123")
        with self.assertRaises(json.JSONDecodeError):
            cli.parse_cli_arguments(["explain", "Review UI quality", "--context", "{"])

    def test_runtime_cli_parser_rejects_unknown_options(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown TMCP option.*--bogus"):
            cli.parse_cli_arguments(["status", "--bogus"])

    def test_runtime_cli_parser_has_no_adapter_or_io_authority(self) -> None:
        source_path = Path(cli.__file__ or "")
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
            "shutil",
            "subprocess",
            "sys",
            "scripts",
            "tmcp_runtime.safety",
            "tmcp_runtime.services",
            "tmcp_runtime.storage",
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
                "tmcp_runtime.api.registry",
                "tmcp_runtime.api.tool_schemas",
            }.issubset(imported_modules)
        )

    def test_cli_parser_repeated_flags_become_lists(self) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            [
                "harvest",
                ".",
                "--include-globs",
                "**/SKILL.md",
                "--include-globs",
                "**/AGENTS.md",
                "--write-artifacts",
                "--no-redact-sensitive",
                "--compact",
            ]
        )

        self.assertEqual(tool_name, "tmcp_harvest_skills")
        self.assertTrue(compact)
        self.assertEqual(arguments["source_path"], ".")
        self.assertEqual(arguments["include_globs"], ["**/SKILL.md", "**/AGENTS.md"])
        self.assertTrue(arguments["write_artifacts"])
        self.assertFalse(arguments["redact_sensitive"])

    def test_cli_parser_schema_array_flags_accept_single_value(self) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            ["recommend", ".", "--candidate-workflows", "ui_quality"]
        )

        self.assertEqual(tool_name, "tmcp_recommend_workflows")
        self.assertFalse(compact)
        self.assertEqual(arguments["candidate_workflows"], ["ui_quality"])

    def test_cli_parser_promote_harvest_accepts_source_and_selected_workflow(
        self,
    ) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            [
                "promote-harvest",
                ".",
                "--selected-workflows",
                "repo_behavior_spec_loop_workflow",
                "--no-write-artifacts",
            ]
        )

        self.assertEqual(tool_name, "tmcp_promote_harvest")
        self.assertFalse(compact)
        self.assertEqual(arguments["source_path"], ".")
        self.assertEqual(
            arguments["selected_workflows"], ["repo_behavior_spec_loop_workflow"]
        )
        self.assertFalse(arguments["write_artifacts"])

    def test_cli_parser_accepts_composition_commands_and_flags(self) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            [
                "compose-packet",
                "Improve the dashboard UI",
                "--project-path",
                "/tmp/project",
                "--phase",
                "start",
                "--cache-policy",
                "global",
                "--runtime-context",
                '{"files_changed":["src/App.tsx"]}',
                "--session-id",
                "123",
                "--compact",
            ]
        )

        self.assertEqual(tool_name, "tmcp_compose_packet")
        self.assertTrue(compact)
        self.assertEqual(arguments["objective"], "Improve the dashboard UI")
        self.assertEqual(arguments["project_path"], "/tmp/project")
        self.assertEqual(arguments["phase"], "start")
        self.assertEqual(arguments["cache_policy"], "global")
        self.assertEqual(
            arguments["runtime_context"], {"files_changed": ["src/App.tsx"]}
        )
        self.assertEqual(arguments["session_id"], "123")

        tool_name, arguments, _ = self.server._parse_cli_arguments(
            [
                "runtime-next",
                "Fix the dashboard bug",
                "--project-path",
                "/tmp/project",
                "--current-phase",
                "final",
                "--files-changed",
                "app/page.tsx",
                "--failures",
                "vitest failed",
            ]
        )

        self.assertEqual(tool_name, "tmcp_runtime_next")
        self.assertEqual(arguments["objective"], "Fix the dashboard bug")
        self.assertEqual(arguments["current_phase"], "final")
        self.assertNotIn("cache_policy", arguments)
        self.assertEqual(arguments["files_changed"], ["app/page.tsx"])
        self.assertEqual(arguments["failures"], ["vitest failed"])

        tool_name, arguments, _ = self.server._parse_cli_arguments(
            [
                "record-receipt",
                "packet-123",
                "--activated-atoms",
                "ui-browser-verification",
                "--outcome",
                "passed",
            ]
        )

        self.assertEqual(tool_name, "tmcp_record_receipt")
        self.assertEqual(arguments["packet_id"], "packet-123")
        self.assertEqual(arguments["activated_atoms"], ["ui-browser-verification"])
        self.assertEqual(arguments["outcome"], "passed")

    def test_cli_parser_compose_flag_on_existing_tools(self) -> None:
        tool_name, arguments, _ = self.server._parse_cli_arguments(
            [
                "explain",
                "Review UI quality",
                "--project-path",
                "/tmp/project",
                "--compose",
            ]
        )

        self.assertEqual(tool_name, "tmcp_explain")
        self.assertTrue(arguments["compose"])

        tool_name, arguments, _ = self.server._parse_cli_arguments(
            ["recommend", "/tmp/project", "--compose"]
        )

        self.assertEqual(tool_name, "tmcp_recommend_workflows")
        self.assertTrue(arguments["compose"])

    def test_agent_docs_cover_composition_runtime_and_receipts(self) -> None:
        paths = [
            PLUGIN_ROOT / "skills" / "tmcp" / "SKILL.md",
            PLUGIN_ROOT / "skills" / "tmcp" / "references" / "cli.md",
            PLUGIN_ROOT / "skills" / "tmcp" / "references" / "workflows.md",
            PLUGIN_ROOT / "docs" / "CLI.md",
            PLUGIN_ROOT / "README.md",
        ]
        docs = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        for expected in (
            "tmcp_compose_packet",
            "tmcp_runtime_next",
            "tmcp_record_receipt",
            "compose-packet",
            "runtime-next",
            "record-receipt",
            "--compose",
            "session_id",
            "TMCP_HOME",
            "advisory",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, docs)

    def test_cli_expert_ui_rubric_alias_defaults_to_tmcp_workflow(self) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            [
                "expert-ui-rubric",
                "--project-path",
                "/tmp/fantasy",
                "--evidence-json",
                "[]",
            ]
        )

        self.assertEqual(tool_name, "expert_rubric_review_plan")
        self.assertFalse(compact)
        self.assertEqual(
            arguments["objective"], "Use the TMCP expert UI rubric on this project."
        )
        self.assertEqual(arguments["adapter"], "standalone")
        self.assertEqual(arguments["project_path"], "/tmp/fantasy")

    def test_cli_expert_ui_rubric_alias_accepts_objective_override(self) -> None:
        tool_name, arguments, compact = self.server._parse_cli_arguments(
            [
                "tmcp-expert-ui-rubric",
                "Use the TMCP expert UI rubric workflow on Fantasy",
            ]
        )

        self.assertEqual(tool_name, "expert_rubric_review_plan")
        self.assertFalse(compact)
        self.assertEqual(
            arguments["objective"], "Use the TMCP expert UI rubric workflow on Fantasy"
        )
        self.assertEqual(arguments["adapter"], "standalone")
