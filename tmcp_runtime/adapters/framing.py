"""Content-Length framing for the MCP stdio transport."""

from __future__ import annotations

import json
from typing import Any, BinaryIO

MAX_HEADER_BYTES = 8 * 1024
MAX_MESSAGE_BYTES = 16 * 1024 * 1024


class FramingError(ValueError):
    """Raised when an MCP stdio frame cannot be decoded safely."""


def encode_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def read_message(stdin: BinaryIO) -> object | None:
    headers: dict[str, str] = {}
    header_bytes = 0
    while True:
        line = stdin.readline(MAX_HEADER_BYTES + 1)
        if line == b"":
            return None
        if len(line) > MAX_HEADER_BYTES:
            raise FramingError("MCP headers exceed the maximum size.")
        header_bytes += len(line)
        if header_bytes > MAX_HEADER_BYTES:
            raise FramingError("MCP headers exceed the maximum size.")
        if line in {b"\r\n", b"\n"}:
            break
        try:
            decoded = line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise FramingError("MCP headers must be ASCII.") from exc
        key, separator, value = decoded.partition(":")
        if not separator or not key.strip():
            raise FramingError("MCP header is malformed.")
        normalized_key = key.strip().lower()
        if normalized_key in headers:
            raise FramingError(f"Duplicate MCP header: {normalized_key}.")
        headers[normalized_key] = value.strip()
    raw_length = headers.get("content-length")
    if raw_length is None:
        raise FramingError("MCP frame is missing Content-Length.")
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise FramingError("MCP Content-Length must be an integer.") from exc
    if length <= 0:
        raise FramingError("MCP Content-Length must be positive.")
    if length > MAX_MESSAGE_BYTES:
        raise FramingError("MCP message exceeds the maximum size.")
    body = stdin.read(length)
    if len(body) != length:
        raise FramingError("MCP message body is truncated.")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FramingError("MCP message body is not valid UTF-8 JSON.") from exc


def write_message(stdout: BinaryIO, payload: dict[str, Any]) -> None:
    stdout.write(encode_message(payload))
    stdout.flush()
