"""Standalone explain orchestration over runtime packet and compose callbacks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from tmcp_runtime.domain.standalone_packets import compile_standalone_packet

ComposeCallback = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ExplainServiceContext:
    """Runtime packet capabilities supplied by the transport adapter."""

    compose_packet: ComposeCallback


class ExplainService:
    """Build explain responses without making transport or redaction decisions."""

    def __init__(self, context: ExplainServiceContext) -> None:
        self._context = context

    def standalone(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Build a standalone packet and optional composed packet preview."""

        result: dict[str, Any] = {
            "ok": True,
            "adapter": "standalone",
            "command": "tmcp-explain",
            "data_status": "compiled",
            "packet": compile_standalone_packet(
                objective=str(arguments["objective"]),
                project_path=str(arguments.get("project_path") or "."),
                phase=str(arguments.get("phase") or "") or None,
                domain=str(arguments.get("domain") or "") or None,
            ),
        }
        if bool(arguments.get("compose", False)):
            result["composed_packet"] = self._context.compose_packet(
                {
                    "objective": arguments["objective"],
                    "project_path": arguments.get("project_path") or ".",
                    "source_path": arguments.get("source_path")
                    or arguments.get("project_path")
                    or ".",
                    "phase": arguments.get("phase") or "start",
                    "cache_policy": arguments.get("cache_policy") or "none",
                }
            )
        return result
