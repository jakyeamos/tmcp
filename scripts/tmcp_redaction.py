"""Compatibility facade for the runtime-owned redaction primitives."""

from tmcp_runtime.safety.redaction import (
    SECRET_PATTERNS,
    looks_high_entropy,
    merge_redactions,
    redact_sensitive_text,
)

__all__ = [
    "SECRET_PATTERNS",
    "looks_high_entropy",
    "merge_redactions",
    "redact_sensitive_text",
]
