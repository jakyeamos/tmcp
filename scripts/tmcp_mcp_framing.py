"""Compatibility facade for runtime-owned MCP framing."""

from tmcp_runtime.adapters.framing import encode_message, read_message, write_message

__all__ = ["encode_message", "read_message", "write_message"]
