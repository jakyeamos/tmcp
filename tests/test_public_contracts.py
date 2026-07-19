from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import cast

from tests.tmcp_test_client import TestWorkspace
from tmcp_runtime.api.registry import (
    CLI_COMMAND_DEFAULT_ARGUMENTS,
    CLI_HELP_ALIASES,
    CLI_LIST_TOOLS_ALIASES,
    CLI_TOOL_ALIASES,
    TOOL_STATE_EFFECTS,
    VERSION,
    canonical_contract_fixture,
    mcp_server_info,
    mcp_tools,
)
from tmcp_runtime.api.cli import parse_cli_arguments


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PLUGIN_ROOT / "tests" / "fixtures" / "public-contract-v0.4.json"


class PublicContractTests(unittest.TestCase):
    def test_canonical_registry_matches_frozen_fixture(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(canonical_contract_fixture(), fixture)

    def test_packet_sessions_are_explicit_optional_writes(self) -> None:
        self.assertEqual(TOOL_STATE_EFFECTS["tmcp_compose_packet"], "optional_write")
        self.assertEqual(TOOL_STATE_EFFECTS["tmcp_runtime_next"], "optional_write")

    def test_composition_contract_marks_assisted_and_compatibility_paths(self) -> None:
        tools_by_name = {str(tool["name"]): tool for tool in mcp_tools()}
        compose_description = str(tools_by_name["tmcp_compose_packet"]["description"])
        explain_description = str(tools_by_name["tmcp_explain"]["description"])

        self.assertIn("tmcp_prepare_composition", compose_description)
        self.assertIn("compatibility", compose_description.lower())
        self.assertIn("prepare", explain_description.lower())
        self.assertIn("compatibility", explain_description.lower())

    def test_every_cli_alias_and_pseudo_command_resolves_from_registry(self) -> None:
        for alias, expected_tool in CLI_TOOL_ALIASES.items():
            with self.subTest(alias=alias):
                tool_name, arguments, compact = parse_cli_arguments([alias])
                self.assertEqual(tool_name, expected_tool)
                self.assertFalse(compact)
                self.assertEqual(
                    arguments,
                    CLI_COMMAND_DEFAULT_ARGUMENTS.get(alias, {}),
                )

        for alias in CLI_HELP_ALIASES:
            with self.subTest(alias=alias):
                self.assertEqual(parse_cli_arguments([alias]), ("help", {}, False))
        for alias in CLI_LIST_TOOLS_ALIASES:
            with self.subTest(alias=alias):
                self.assertEqual(
                    parse_cli_arguments([alias]), ("list-tools", {}, False)
                )
        self.assertEqual(parse_cli_arguments([]), ("help", {}, False))

    def test_mcp_and_cli_list_tools_share_the_same_hermetic_contract(self) -> None:
        with TestWorkspace() as workspace:
            responses = workspace.run_mcp(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05"},
                    },
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                ]
            )
            initialize_result = cast(dict[str, object], responses[0]["result"])
            tools_result = cast(dict[str, object], responses[1]["result"])
            self.assertEqual(initialize_result["serverInfo"], mcp_server_info())
            self.assertEqual(tools_result["tools"], mcp_tools())

            cli = workspace.run_cli(["list-tools", "--compact"])
            self.assertEqual(cli.returncode, 0, cli.stderr)
            cli_payload = cli.json()
            self.assertEqual(cli_payload["tools"], mcp_tools())
            assert workspace.tmcp_home is not None
            self.assertEqual(list(workspace.tmcp_home.iterdir()), [])

    def test_source_metadata_and_live_transport_match_the_registry(self) -> None:
        if not (PLUGIN_ROOT / "mcp-registry").exists():
            self.skipTest(
                "source-only registry metadata is intentionally excluded from release archives"
            )
        with TestWorkspace() as workspace:
            completed = subprocess.run(
                [sys.executable, "scripts/check_contracts.py", "."],
                cwd=PLUGIN_ROOT,
                env=workspace.environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["version"], VERSION.release)
