"""Pure CLI argument parsing shared by TMCP command transports."""

from __future__ import annotations

import json
import re
from typing import Any

from tmcp_runtime.api.registry import (
    CLI_COMMAND_DEFAULT_ARGUMENTS,
    CLI_HELP_ALIASES,
    CLI_LIST_TOOLS_ALIASES,
    CLI_VERSION_ALIASES,
    CLI_TOOL_ALIASES,
)
from tmcp_runtime.api.tool_schemas import TOOLS


def decode_cli_value(value: str) -> Any:
    """Decode the documented scalar and JSON CLI value forms."""

    stripped = value.strip()
    if stripped in {"true", "false", "null"}:
        return json.loads(stripped)
    if stripped.startswith(("{", "[")):
        return json.loads(stripped)
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)
    return value


def set_cli_argument(arguments: dict[str, Any], key: str, value: Any) -> None:
    """Set a kebab-case CLI argument, preserving repeated values as lists."""

    normalized = key.replace("-", "_")
    if normalized in arguments:
        existing = arguments[normalized]
        if isinstance(existing, list):
            existing.append(value)
        else:
            arguments[normalized] = [existing, value]
        return
    arguments[normalized] = value


def parse_cli_arguments(argv: list[str]) -> tuple[str, dict[str, Any], bool]:
    """Map CLI tokens to the canonical tool name, arguments, and output mode."""

    if not argv or argv[0] in CLI_HELP_ALIASES:
        return "help", {}, False
    if argv[0] in CLI_LIST_TOOLS_ALIASES:
        return "list-tools", {}, False
    if argv[0] in CLI_VERSION_ALIASES:
        return "version", {}, False

    command = argv[0]
    tool_name = CLI_TOOL_ALIASES.get(command)
    if not tool_name:
        raise ValueError(f"Unknown TMCP command: {command}")

    compact = False
    positionals: list[str] = []
    arguments: dict[str, Any] = {}
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--compact":
            compact = True
            index += 1
            continue
        if token in {"-h", "--help"}:
            return "help", {}, compact
        if token.startswith("--no-"):
            set_cli_argument(arguments, token[5:], False)
            index += 1
            continue
        if token.startswith("--"):
            key = token[2:]
            next_index = index + 1
            if next_index >= len(argv) or argv[next_index].startswith("--"):
                set_cli_argument(arguments, key, True)
                index += 1
                continue
            value = (
                argv[next_index]
                if key.replace("-", "_") == "session_id"
                else decode_cli_value(argv[next_index])
            )
            set_cli_argument(arguments, key, value)
            index += 2
            continue
        positionals.append(token)
        index += 1

    if positionals:
        if tool_name in {"tmcp_explain", "expert_rubric_review_plan"}:
            arguments.setdefault("objective", positionals[0])
        elif tool_name in {"tmcp_compose_packet", "tmcp_runtime_next"}:
            arguments.setdefault("objective", positionals[0])
        elif tool_name == "tmcp_record_receipt":
            arguments.setdefault("packet_id", positionals[0])
        elif tool_name in {
            "tmcp_harvest_skills",
            "tmcp_recommend_workflows",
            "tmcp_promote_harvest",
            "tmcp_evaluate_skills",
        }:
            arguments.setdefault("source_path", positionals[0])
            if len(positionals) > 1:
                arguments.setdefault("objective", positionals[1])
        elif tool_name == "tmcp_doctor":
            arguments.setdefault("client", positionals[0])

    for key, value in CLI_COMMAND_DEFAULT_ARGUMENTS.get(command, {}).items():
        arguments.setdefault(key, value)

    normalize_cli_arguments(tool_name, arguments)
    return tool_name, arguments, compact


def normalize_cli_arguments(tool_name: str, arguments: dict[str, Any]) -> None:
    """Coerce scalar flags to arrays when the canonical tool schema requires it."""

    schema = TOOLS.get(tool_name, {}).get("inputSchema", {})
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if not isinstance(properties, dict):
        return
    for key, value in list(arguments.items()):
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict):
            option = f"--{key.replace('_', '-')}"
            raise ValueError(f"Unknown TMCP option for {tool_name}: {option}")
        if property_schema.get("type") == "array" and not isinstance(value, list):
            arguments[key] = [value]
