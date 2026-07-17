"""CLI transport adapter over canonical parsing and typed runtime dispatch."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any, TextIO

from tmcp_runtime.adapters.dispatch import ToolDispatcher, ToolRequest, ToolResult
from tmcp_runtime.api.cli import parse_cli_arguments
from tmcp_runtime.api.registry import VERSION, cli_usage, mcp_tools


LegacyToolHandler = Callable[[str, dict[str, Any]], dict[str, Any]]


def _dispatch(
    request: ToolRequest,
    *,
    dispatcher: ToolDispatcher | None,
    call_tool: LegacyToolHandler | None,
) -> ToolResult:
    if dispatcher is not None:
        return dispatcher.dispatch(request)
    if call_tool is not None:
        return ToolResult.from_payload(call_tool(request.name, request.arguments))
    raise RuntimeError("CLI adapter has no tool dispatcher.")


def run_cli(
    argv: list[str],
    *,
    dispatcher: ToolDispatcher | None = None,
    call_tool: LegacyToolHandler | None = None,
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
        if command == "version":
            print(VERSION.release, file=output)
            return 0
        if command == "list-tools":
            payload: dict[str, Any] = {
                "ok": True,
                "schema": "tmcp-cli-tools-v0.1",
                "tools": mcp_tools(),
            }
        else:
            payload = _dispatch(
                ToolRequest.from_parts(command, arguments),
                dispatcher=dispatcher,
                call_tool=call_tool,
            ).to_payload()
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
