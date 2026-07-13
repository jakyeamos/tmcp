"""MCP JSON-RPC transport adapter over an injected tool handler."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, BinaryIO

from tmcp_runtime.adapters.framing import read_message, write_message


ToolHandler = Callable[[str, dict[str, Any]], dict[str, Any]]
ServerInfoProvider = Callable[[], dict[str, Any]]
ToolListProvider = Callable[[], list[dict[str, Any]]]


def tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}
        ],
        "structuredContent": payload,
        "isError": not bool(payload.get("ok", True)),
    }


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle_message(
    request: dict[str, Any],
    *,
    call_tool: ToolHandler,
    server_info: ServerInfoProvider,
    tools: ToolListProvider,
) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "serverInfo": server_info(),
                "capabilities": {"tools": {}},
            },
        )
    if method == "tools/list":
        return _result(request_id, {"tools": tools()})
    if method in {"resources/list", "prompts/list"}:
        key = "resources" if method == "resources/list" else "prompts"
        return _result(request_id, {key: []})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "Tool arguments must be an object.")
        try:
            return _result(request_id, tool_result(call_tool(name, arguments)))
        except Exception as exc:
            return _error(request_id, -32000, str(exc))
    if method in {"notifications/initialized", "ping"}:
        if request_id is not None:
            return _result(request_id, {})
        return None
    if request_id is not None:
        return _error(request_id, -32601, f"Unsupported method: {method}")
    return None


def run_stdio(
    stdin: BinaryIO,
    stdout: BinaryIO,
    *,
    call_tool: ToolHandler,
    server_info: ServerInfoProvider,
    tools: ToolListProvider,
) -> None:
    while True:
        message = read_message(stdin)
        if message is None:
            return
        response = handle_message(
            message,
            call_tool=call_tool,
            server_info=server_info,
            tools=tools,
        )
        if response is not None:
            write_message(stdout, response)
