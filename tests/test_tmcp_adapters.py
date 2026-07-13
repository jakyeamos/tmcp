from __future__ import annotations

import ast
import io
import json
import unittest
from pathlib import Path

from tmcp_runtime.adapters.cli import run_cli
from tmcp_runtime.adapters.dispatch import ToolDispatcher, ToolRequest
from tmcp_runtime.adapters.framing import encode_message, read_message
from tmcp_runtime.adapters.mcp import handle_message, run_stdio
from tmcp_runtime.api.registry import PUBLIC_TOOL_NAMES


class RuntimeAdapterTests(unittest.TestCase):
    @staticmethod
    def _call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "name": name, "arguments": arguments}

    @staticmethod
    def _server_info() -> dict[str, str]:
        return {"name": "tmcp", "version": "test"}

    @staticmethod
    def _tools() -> list[dict[str, object]]:
        return [{"name": "echo"}]

    @staticmethod
    def _typed_handler(arguments: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "arguments": arguments}

    def test_typed_dispatch_validates_requests_and_results(self) -> None:
        dispatcher = ToolDispatcher(
            {"echo": self._typed_handler},
            allowed_names={"echo"},
        )
        result = dispatcher.dispatch(
            ToolRequest.from_parts("echo", {"value": "ok"})
        )

        self.assertEqual(result.to_payload()["arguments"], {"value": "ok"})
        with self.assertRaises(TypeError):
            ToolRequest.from_parts("echo", [])  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            dispatcher.dispatch(ToolRequest.from_parts("missing", {}))

    def test_default_dispatch_registry_requires_every_public_tool(self) -> None:
        handlers = {
            name: self._typed_handler
            for name in PUBLIC_TOOL_NAMES
        }
        dispatcher = ToolDispatcher(handlers)

        self.assertEqual(dispatcher.tool_names, PUBLIC_TOOL_NAMES)
        with self.assertRaises(ValueError):
            ToolDispatcher({"echo": self._typed_handler})

    def test_mcp_adapter_accepts_typed_dispatcher(self) -> None:
        dispatcher = ToolDispatcher(
            {"echo": self._typed_handler},
            allowed_names={"echo"},
        )
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"value": "ok"}},
            },
            dispatcher=dispatcher,
            server_info=self._server_info,
            tools=self._tools,
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(
            response["result"]["structuredContent"]["arguments"],
            {"value": "ok"},
        )

    def test_mcp_message_adapter_preserves_tool_result_contract(self) -> None:
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"value": "ok"}},
            },
            call_tool=self._call_tool,
            server_info=self._server_info,
            tools=self._tools,
        )

        self.assertIsNotNone(response)
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["name"], "echo")
        self.assertFalse(response["result"]["isError"])

    def test_mcp_stdio_adapter_round_trips_framed_messages(self) -> None:
        incoming = io.BytesIO(
            encode_message({"jsonrpc": "2.0", "id": 1, "method": "ping"})
            + encode_message({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})
        )
        outgoing = io.BytesIO()

        run_stdio(
            incoming,
            outgoing,
            call_tool=self._call_tool,
            server_info=self._server_info,
            tools=self._tools,
        )

        outgoing.seek(0)
        self.assertEqual(read_message(outgoing), {"jsonrpc": "2.0", "id": 1, "result": {}})
        self.assertEqual(
            read_message(outgoing),
            {"jsonrpc": "2.0", "id": 2, "result": {"resources": []}},
        )

    def test_cli_adapter_uses_injected_tool_handler(self) -> None:
        output = io.StringIO()
        status = run_cli(
            ["compose", "Build a packet", "--compact"],
            call_tool=self._call_tool,
            stdout=output,
        )

        self.assertEqual(status, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["name"], "tmcp_compose_packet")
        self.assertEqual(payload["arguments"]["objective"], "Build a packet")

    def test_adapters_do_not_import_legacy_scripts(self) -> None:
        adapters_root = Path(__file__).resolve().parents[1] / "tmcp_runtime" / "adapters"
        imported_modules: set[str] = set()
        for path in adapters_root.glob("*.py"):
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
        self.assertFalse(any(module.startswith("scripts") for module in imported_modules))


if __name__ == "__main__":
    unittest.main()
