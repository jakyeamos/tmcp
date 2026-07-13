"""CLI transport adapter over canonical parsing and an injected tool handler."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any, TextIO

from tmcp_runtime.api.cli import parse_cli_arguments
from tmcp_runtime.api.registry import cli_usage, mcp_tools


ToolHandler = Callable[[str, dict[str, Any]], dict[str, Any]]


def run_cli(
    argv: list[str],
    *,
    call_tool: ToolHandler,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    try:
        command, arguments, compact = parse_cli_arguments(argv)
        if command == "help":
            print(cli_usage(), file=output)
            return 0
        if command == "list-tools":
            payload: dict[str, Any] = {
                "ok": True,
                "schema": "tmcp-cli-tools-v0.1",
                "tools": mcp_tools(),
            }
        else:
            payload = call_tool(command, arguments)
        print(
            json.dumps(
                payload,
                separators=(",", ":") if compact else None,
                indent=None if compact else 2,
                sort_keys=True,
            ),
            file=output,
        )
        return 0 if bool(payload.get("ok", True)) else 1
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True),
            file=errors,
        )
        return 2
