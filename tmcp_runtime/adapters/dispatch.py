"""Typed request/result dispatch for the public TMCP tool registry."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Any

from tmcp_runtime.api.registry import PUBLIC_TOOL_NAMES


@dataclass(frozen=True)
class ToolRequest:
    """A validated tool invocation crossing a transport boundary."""

    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_parts(cls, name: str, arguments: Mapping[str, Any]) -> "ToolRequest":
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Tool name must be a non-empty string.")
        if not isinstance(arguments, Mapping):
            raise TypeError("Tool arguments must be an object.")
        return cls(name=name.strip(), arguments=dict(arguments))


@dataclass(frozen=True)
class ToolResult:
    """A normalized mapping returned by a tool handler."""

    payload: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ToolResult":
        if not isinstance(payload, Mapping):
            raise TypeError("Tool result must be an object.")
        return cls(payload=dict(payload))

    def to_payload(self) -> dict[str, Any]:
        return dict(self.payload)


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


class ToolDispatcher:
    """Dispatch validated requests through one canonical tool registry."""

    def __init__(
        self,
        handlers: Mapping[str, ToolHandler],
        *,
        allowed_names: Collection[str] | None = None,
    ) -> None:
        self._handlers = dict(handlers)
        self._allowed_names = frozenset(
            PUBLIC_TOOL_NAMES if allowed_names is None else allowed_names
        )
        unknown_handlers = set(self._handlers) - self._allowed_names
        if unknown_handlers:
            names = ", ".join(sorted(unknown_handlers))
            raise ValueError(f"Handlers are not public TMCP tools: {names}")
        missing_handlers = self._allowed_names - set(self._handlers)
        if missing_handlers:
            names = ", ".join(sorted(missing_handlers))
            raise ValueError(f"Missing handlers for public TMCP tools: {names}")

    @property
    def tool_names(self) -> frozenset[str]:
        return self._allowed_names

    def dispatch(self, request: ToolRequest) -> ToolResult:
        if request.name not in self._allowed_names:
            raise ValueError(f"Unknown TMCP tool: {request.name}")
        handler = self._handlers.get(request.name)
        if handler is None:
            raise RuntimeError(f"No handler registered for TMCP tool: {request.name}")
        return ToolResult.from_payload(handler(dict(request.arguments)))
