"""MCP JSON-RPC transport adapter over typed runtime dispatch."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, BinaryIO

from tmcp_runtime.adapters.dispatch import (
    ToolDispatcher,
    ToolRequest,
    ToolResult,
)
from tmcp_runtime.adapters.framing import FramingError, read_message, write_message


LegacyToolHandler = Callable[[str, dict[str, Any]], dict[str, Any]]
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


def _response_or_none(
    request_id: Any, result: dict[str, Any]
) -> dict[str, Any] | None:
    if request_id is None:
        return None
    return _result(request_id, result)


def _error_or_none(
    request_id: Any, code: int, message: str
) -> dict[str, Any] | None:
    if request_id is None:
        return None
    return _error(request_id, code, message)


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
    raise RuntimeError("MCP adapter has no tool dispatcher.")


def handle_message(
    request: object,
    *,
    dispatcher: ToolDispatcher | None = None,
    call_tool: LegacyToolHandler | None = None,
    server_info: ServerInfoProvider,
    tools: ToolListProvider,
) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return _error(None, -32600, "Invalid JSON-RPC request.")
    request_id = request.get("id")
    if request.get("jsonrpc") != "2.0":
        return _error(request_id, -32600, "Invalid JSON-RPC request.")
    method = request.get("method")
    if not isinstance(method, str):
        return _error(request_id, -32600, "JSON-RPC method must be a string.")
    params = request.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error_or_none(
            request_id,
            -32602,
            "JSON-RPC params must be an object.",
        )
    if method == "initialize":
        return _response_or_none(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "serverInfo": server_info(),
                "capabilities": {"tools": {}},
            },
        )
    if method == "tools/list":
        return _response_or_none(request_id, {"tools": tools()})
    if method in {"resources/list", "prompts/list"}:
        key = "resources" if method == "resources/list" else "prompts"
        return _response_or_none(request_id, {key: []})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _error_or_none(
                request_id, -32602, "Tool arguments must be an object."
            )
        try:
            tool_request = ToolRequest.from_parts(name, arguments)
            tool_payload = _dispatch(
                tool_request,
                dispatcher=dispatcher,
                call_tool=call_tool,
            ).to_payload()
            return _response_or_none(request_id, tool_result(tool_payload))
        except Exception as exc:
            return _error_or_none(request_id, -32000, str(exc))
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
    dispatcher: ToolDispatcher | None = None,
    call_tool: LegacyToolHandler | None = None,
    server_info: ServerInfoProvider,
    tools: ToolListProvider,
) -> None:
    while True:
        try:
            message = read_message(stdin)
        except FramingError as exc:
            write_message(stdout, _error(None, -32700, str(exc)))
            return
        if message is None:
            return
        response = handle_message(
            message,
            dispatcher=dispatcher,
            call_tool=call_tool,
            server_info=server_info,
            tools=tools,
        )
        if response is not None:
            write_message(stdout, response)
