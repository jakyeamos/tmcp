"""Canonical public TMCP transport contracts.

The MCP adapter, CLI adapter, installer, release checks, and contract tests all
consume this module. Keeping the externally visible surface here lets the
runtime evolve without silently changing a deployed command or schema.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Final, Literal

from .tool_schemas import TOOLS


@dataclass(frozen=True)
class VersionDescriptor:
    """The release identity shared by every published TMCP surface."""

    release: str
    codex_plugin: str
    server_name: str
    minimum_node: str
    minimum_python: str


VERSION: Final = VersionDescriptor(
    release="0.5.7",
    codex_plugin="0.5.7+codex.20260716005835",
    server_name="tmcp",
    minimum_node=">=20",
    minimum_python=">=3.10",
)

ToolStability = Literal["stable", "experimental"]
StateEffect = Literal["read_only", "optional_write", "default_write"]


@dataclass(frozen=True)
class ToolContract:
    """A frozen public tool contract, including its CLI compatibility layer."""

    name: str
    description: str
    input_schema: Mapping[str, object]
    canonical_cli_command: str
    cli_aliases: tuple[str, ...]
    cli_defaults: Mapping[str, Mapping[str, object]]
    output_schema_ids: tuple[str, ...]
    stability: ToolStability
    state_effect: StateEffect


CLI_TOOL_ALIASES = {
    "doctor": "tmcp_doctor",
    "tmcp-doctor": "tmcp_doctor",
    "tmcp_doctor": "tmcp_doctor",
    "status": "tmcp_status",
    "tmcp-status": "tmcp_status",
    "tmcp_status": "tmcp_status",
    "explain": "tmcp_explain",
    "tmcp-explain": "tmcp_explain",
    "tmcp_explain": "tmcp_explain",
    "harvest": "tmcp_harvest_skills",
    "harvest-skills": "tmcp_harvest_skills",
    "tmcp-harvest-skills": "tmcp_harvest_skills",
    "tmcp_harvest_skills": "tmcp_harvest_skills",
    "evaluate-skills": "tmcp_evaluate_skills",
    "evaluate": "tmcp_evaluate_skills",
    "tmcp-evaluate-skills": "tmcp_evaluate_skills",
    "tmcp_evaluate_skills": "tmcp_evaluate_skills",
    "recommend": "tmcp_recommend_workflows",
    "recommend-workflows": "tmcp_recommend_workflows",
    "tmcp-recommend-workflows": "tmcp_recommend_workflows",
    "tmcp_recommend_workflows": "tmcp_recommend_workflows",
    "promote": "tmcp_promote_harvest",
    "promote-harvest": "tmcp_promote_harvest",
    "promote-workflows": "tmcp_promote_harvest",
    "tmcp-promote-harvest": "tmcp_promote_harvest",
    "tmcp_promote_harvest": "tmcp_promote_harvest",
    "compose": "tmcp_compose_packet",
    "compose-packet": "tmcp_compose_packet",
    "tmcp-compose-packet": "tmcp_compose_packet",
    "tmcp_compose_packet": "tmcp_compose_packet",
    "runtime-next": "tmcp_runtime_next",
    "tmcp-runtime-next": "tmcp_runtime_next",
    "tmcp_runtime_next": "tmcp_runtime_next",
    "recompile-packet": "tmcp_runtime_next",
    "tmcp-recompile-packet": "tmcp_runtime_next",
    "record-receipt": "tmcp_record_receipt",
    "tmcp-record-receipt": "tmcp_record_receipt",
    "tmcp_record_receipt": "tmcp_record_receipt",
    "review-plan": "expert_rubric_review_plan",
    "expert-rubric": "expert_rubric_review_plan",
    "expert-rubric-review-plan": "expert_rubric_review_plan",
    "expert-ui-rubric": "expert_rubric_review_plan",
    "expert-ui-review": "expert_rubric_review_plan",
    "expert_rubric_review_plan": "expert_rubric_review_plan",
    "tmcp-expert-ui-rubric": "expert_rubric_review_plan",
    "tmcp-ui-rubric": "expert_rubric_review_plan",
    "ui-rubric": "expert_rubric_review_plan",
}

CLI_COMMAND_DEFAULT_ARGUMENTS = {
    "expert-ui-rubric": {
        "objective": "Use the TMCP expert UI rubric on this project.",
        "adapter": "standalone",
    },
    "expert-ui-review": {
        "objective": "Use the TMCP expert UI rubric on this project.",
        "adapter": "standalone",
    },
    "tmcp-expert-ui-rubric": {
        "objective": "Use the TMCP expert UI rubric on this project.",
        "adapter": "standalone",
    },
    "tmcp-ui-rubric": {
        "objective": "Use the TMCP expert UI rubric on this project.",
        "adapter": "standalone",
    },
    "ui-rubric": {
        "objective": "Use the TMCP expert UI rubric on this project.",
        "adapter": "standalone",
    },
    "recompile-packet": {"output_mode": "full"},
    "tmcp-recompile-packet": {"output_mode": "full"},
}

CLI_HELP_ALIASES: Final[tuple[str, ...]] = ("help", "-h", "--help")
CLI_LIST_TOOLS_ALIASES: Final[tuple[str, ...]] = ("list-tools", "tools", "tools-list")
CLI_CANONICAL_COMMANDS: Final[dict[str, str]] = {
    "tmcp_doctor": "doctor",
    "tmcp_status": "status",
    "tmcp_explain": "explain",
    "tmcp_harvest_skills": "harvest",
    "tmcp_evaluate_skills": "evaluate-skills",
    "tmcp_recommend_workflows": "recommend",
    "tmcp_promote_harvest": "promote-harvest",
    "tmcp_compose_packet": "compose-packet",
    "tmcp_runtime_next": "runtime-next",
    "tmcp_record_receipt": "record-receipt",
    "expert_rubric_review_plan": "review-plan",
}


TOOL_STABILITY: Final[dict[str, ToolStability]] = {
    "tmcp_doctor": "stable",
    "tmcp_status": "stable",
    "tmcp_explain": "stable",
    "tmcp_harvest_skills": "experimental",
    "tmcp_evaluate_skills": "experimental",
    "tmcp_recommend_workflows": "experimental",
    "tmcp_promote_harvest": "experimental",
    "tmcp_compose_packet": "stable",
    "tmcp_runtime_next": "stable",
    "tmcp_record_receipt": "experimental",
    "expert_rubric_review_plan": "experimental",
}

TOOL_STATE_EFFECTS: Final[dict[str, StateEffect]] = {
    "tmcp_doctor": "read_only",
    "tmcp_status": "read_only",
    "tmcp_explain": "read_only",
    "tmcp_harvest_skills": "optional_write",
    "tmcp_evaluate_skills": "optional_write",
    "tmcp_recommend_workflows": "optional_write",
    "tmcp_promote_harvest": "default_write",
    "tmcp_compose_packet": "optional_write",
    "tmcp_runtime_next": "optional_write",
    "tmcp_record_receipt": "default_write",
    "expert_rubric_review_plan": "default_write",
}

TOOL_OUTPUT_SCHEMA_IDS: Final[dict[str, tuple[str, ...]]] = {
    "tmcp_doctor": ("tmcp-doctor-v0.1",),
    "tmcp_status": ("tmcp-status-v0.1",),
    "tmcp_explain": ("tmcp-skill-packet-v0.2", "tmcp-composed-packet-v0.1"),
    "tmcp_harvest_skills": ("tmcp-harvest-result-v0.1",),
    "tmcp_evaluate_skills": (
        "tmcp-skill-evaluation-plan-v0.1",
        "tmcp-skill-evaluation-plan-v0.2",
        "tmcp-skill-evaluation-report-v0.1",
        "tmcp-skill-evaluation-report-v0.2",
    ),
    "tmcp_recommend_workflows": ("tmcp-workflow-recommendation-v1",),
    "tmcp_promote_harvest": ("tmcp-harvest-promotion-v0.1",),
    "tmcp_compose_packet": ("tmcp-composed-packet-v0.1",),
    "tmcp_runtime_next": (
        "tmcp-runtime-next-v0.1",
        "tmcp-recompiled-packet-v0.1",
    ),
    "tmcp_record_receipt": ("tmcp-run-receipt-v0.1",),
    "expert_rubric_review_plan": ("tmcp-review-plan-result-v0.1",),
}


def _aliases_for(name: str) -> tuple[str, ...]:
    return tuple(
        alias for alias, tool_name in CLI_TOOL_ALIASES.items() if tool_name == name
    )


def _defaults_for(name: str) -> dict[str, Mapping[str, object]]:
    return {
        alias: defaults
        for alias, defaults in CLI_COMMAND_DEFAULT_ARGUMENTS.items()
        if CLI_TOOL_ALIASES.get(alias) == name
    }


def _tool_contract(name: str, definition: Mapping[str, object]) -> ToolContract:
    description = definition.get("description")
    input_schema = definition.get("inputSchema")
    if not isinstance(description, str) or not isinstance(input_schema, Mapping):
        raise RuntimeError(f"Invalid canonical tool definition for {name}")
    return ToolContract(
        name=name,
        description=description,
        input_schema=input_schema,
        canonical_cli_command=CLI_CANONICAL_COMMANDS[name],
        cli_aliases=_aliases_for(name),
        cli_defaults=_defaults_for(name),
        output_schema_ids=TOOL_OUTPUT_SCHEMA_IDS[name],
        stability=TOOL_STABILITY[name],
        state_effect=TOOL_STATE_EFFECTS[name],
    )


TOOL_CONTRACTS: Final[tuple[ToolContract, ...]] = tuple(
    _tool_contract(name, definition) for name, definition in TOOLS.items()
)
PUBLIC_TOOL_NAMES: Final[frozenset[str]] = frozenset(TOOLS)


def mcp_server_info() -> dict[str, str]:
    """Return the server identity used by the MCP initialize response."""

    return {"name": VERSION.server_name, "version": VERSION.release}


def mcp_tools() -> list[dict[str, object]]:
    """Return the exact public tool-list payload in stable name order."""

    return [{"name": name, **definition} for name, definition in sorted(TOOLS.items())]


def cli_usage() -> str:
    """Render the canonical CLI help without duplicating command ownership."""

    commands = CLI_CANONICAL_COMMANDS
    return f"""TMCP command surface

Usage:
  node scripts/tmcp_launcher.mjs                         # start MCP stdio server
  node scripts/tmcp_launcher.mjs list-tools
  node scripts/tmcp_launcher.mjs {commands["tmcp_doctor"]} [--client codex]
  node scripts/tmcp_launcher.mjs {commands["tmcp_status"]}
  node scripts/tmcp_launcher.mjs {commands["tmcp_explain"]} \"<objective>\" [--project-path .] [--adapter auto]
  node scripts/tmcp_launcher.mjs {commands["tmcp_harvest_skills"]} [source_path] [--objective \"...\"] [--write-artifacts --output-dir .tmcp/harvest]
  node scripts/tmcp_launcher.mjs {commands["tmcp_evaluate_skills"]} [--skill-paths path/to/SKILL.md] [--task-fixtures '[...]'] [--write-artifacts]
  node scripts/tmcp_launcher.mjs {commands["tmcp_recommend_workflows"]} [source_path] [--candidate-workflows ui_quality] [--write-artifacts]
  node scripts/tmcp_launcher.mjs {commands["tmcp_promote_harvest"]} [source_path] [--selected-workflows workflow_id] [--write-artifacts]
  node scripts/tmcp_launcher.mjs {commands["tmcp_compose_packet"]} \"<objective>\" [--project-path .] [--source-path .] [--session-id run-name --project-path /absolute/project]
  node scripts/tmcp_launcher.mjs {commands["tmcp_runtime_next"]} \"<objective>\" [--current-phase verification] [--files-changed app/page.tsx] [--output-mode full] [--previous-packet '{{...}}' | --session-id run-name --project-path /absolute/project]
  node scripts/tmcp_launcher.mjs recompile-packet \"<objective>\" [--previous-packet '{{...}}' | --session-id run-name --project-path /absolute/project] [--current-phase runtime] [--files-changed app/page.tsx]
  node scripts/tmcp_launcher.mjs {commands["tmcp_record_receipt"]} packet-id [--activated-atoms atom] [--outcome passed]
  node scripts/tmcp_launcher.mjs {commands["expert_rubric_review_plan"]} \"<objective>\" [--project-path .] [--evidence-json '<dimension-mapped JSON>']
  node scripts/tmcp_launcher.mjs expert-ui-rubric [--project-path .] [--evidence-json '<dimension-mapped JSON>']

Options:
  --key value             Set a tool argument. Kebab-case maps to snake_case.
  --flag                  Set a boolean true argument.
  --no-flag               Set a boolean false argument.
  --compact               Print compact JSON.
  --help                  Show this help.

Argument values that look like JSON objects, arrays, numbers, true, false, or null are decoded.
Repeat an option to send a list, for example --include-globs \"**/SKILL.md\" --include-globs \"**/AGENTS.md\".
"""


def canonical_contract_snapshot() -> dict[str, object]:
    """Return stable, JSON-safe public contract data for fixture verification."""

    return {
        "schema": "tmcp-public-contract-v0.4",
        "version": VERSION.release,
        "server": mcp_server_info(),
        "tools": [
            {
                "name": contract.name,
                "description": contract.description,
                "input_schema": contract.input_schema,
                "canonical_cli_command": contract.canonical_cli_command,
                "cli_aliases": list(contract.cli_aliases),
                "cli_defaults": contract.cli_defaults,
                "output_schema_ids": list(contract.output_schema_ids),
                "stability": contract.stability,
                "state_effect": contract.state_effect,
            }
            for contract in TOOL_CONTRACTS
        ],
    }


def _contract_digest(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def canonical_contract_fixture() -> dict[str, object]:
    """Return a compact frozen fixture for every public CLI and MCP contract."""

    return {
        "schema": "tmcp-public-contract-fixture-v0.4",
        "version": VERSION.release,
        "server": mcp_server_info(),
        "mcp_tools_sha256": _contract_digest(mcp_tools()),
        "pseudo_commands": {
            "help": list(CLI_HELP_ALIASES),
            "list_tools": list(CLI_LIST_TOOLS_ALIASES),
            "stdio": "no arguments",
        },
        "tools": [
            {
                "name": contract.name,
                "description_sha256": _contract_digest(contract.description),
                "input_schema_sha256": _contract_digest(contract.input_schema),
                "canonical_cli_command": contract.canonical_cli_command,
                "cli_aliases": list(contract.cli_aliases),
                "cli_defaults": contract.cli_defaults,
                "output_schema_ids": list(contract.output_schema_ids),
                "stability": contract.stability,
                "state_effect": contract.state_effect,
            }
            for contract in TOOL_CONTRACTS
        ],
    }
