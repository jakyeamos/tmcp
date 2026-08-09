"""Sensitive-text redaction primitives owned by the runtime safety boundary."""

from __future__ import annotations

import re


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    (
        "github_fine_grained_token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    ("aws_access_key", re.compile(r"\bA(?:KIA|SIA)[A-Z0-9]{16}\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd|private[_-]?key|client[_-]?secret)\b"
            r"(\s*[:=]\s*)([\"']?)[^\s\"'`]{8,}\3"
        ),
    ),
    ("long_high_entropy", re.compile(r"\b[A-Za-z0-9+/=_-]{40,}\b")),
)


def looks_high_entropy(value: str) -> bool:
    if len(set(value)) < 8:
        return False
    if not re.search(r"[0-9+/=_-]", value):
        return False
    if (
        re.fullmatch(r"_?[A-Z]+(?:_[A-Z]+)+", value)
        or re.fullmatch(
            r"_?[a-z][a-z0-9]*(?:[_/-][a-z0-9]+)+(?:=_?[a-z][a-z0-9]*(?:[_-][a-z0-9]+)+)?",
            value,
        )
        or re.fullmatch(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+){1,}", value)
        or re.fullmatch(r"[a-z][a-z0-9_]*=[A-Z][A-Z0-9_]*", value)
    ):
        return False
    return True


def redact_sensitive_text(
    text: str, *, enabled: bool = True
) -> tuple[str, dict[str, int]]:
    if not enabled:
        return text, {}
    redactions: dict[str, int] = {}
    redacted = text
    for label, pattern in SECRET_PATTERNS:

        def replace(match: re.Match[str], redaction_label: str = label) -> str:
            if redaction_label == "long_high_entropy" and not looks_high_entropy(
                match.group(0)
            ):
                return match.group(0)
            redactions[redaction_label] = redactions.get(redaction_label, 0) + 1
            if redaction_label == "secret_assignment" and len(match.groups()) >= 2:
                return f"{match.group(1)}{match.group(2)}[REDACTED:{redaction_label}]"
            return f"[REDACTED:{redaction_label}]"

        redacted = pattern.sub(replace, redacted)
    return redacted, redactions


def merge_redactions(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value
