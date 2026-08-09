"""Checksum-context recognition for the release-package policy."""

from __future__ import annotations

import re


def is_documented_checksum(text: str, match: re.Match[str]) -> bool:
    """Return whether a hexadecimal value is documented source evidence."""

    value = match.group(0)
    if not re.fullmatch(r"[A-Fa-f0-9]+", value):
        return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    prefix = text[line_start : match.start()]
    if (
        re.search(
            r"\b(?:current\s+HEAD|declared\s+base)\b\s*[\"'`]?\s*$",
            prefix,
            flags=re.IGNORECASE,
        )
        is not None
    ):
        return True
    if (
        re.search(
            r"\bexact\s+(?:base|HEAD)\b\s*(?:(?:remains|is)\s*)?[\"'`]?\s*$",
            prefix,
            flags=re.IGNORECASE,
        )
        is not None
    ):
        return True
    if len(value) == 40:
        if (
            re.search(
                r"(?i)\b(?:git[_ -])?(?:base[_ -])?commit(?:[_ -](?:sha|id))?"
                r"\s*[:=]\s*[\"'`]?\s*$",
                prefix,
            )
            is not None
        ):
            return True
        if (
            re.search(
                r"(?i)\bexact\s+base(?:\s+commit)?\s*[:=]\s*[\"'`]?\s*$",
                prefix,
            )
            is not None
        ):
            return True
        known_base_field = re.search(
            r"(?i)^\s*[\"'](?:commit|head_commit|declared_h2_base_commit|base_commit)"
            r"[\"']\s*:\s*[\"']?\s*$",
            prefix,
        )
        if known_base_field is None:
            return False
        prior_lines = text[:line_start].splitlines()
        field_indent = len(prefix) - len(prefix.lstrip())
        for offset, prior_line in enumerate(reversed(prior_lines)):
            base_match = re.fullmatch(
                r"(\s*)[\"']base[\"']\s*:\s*\{\s*",
                prior_line,
                flags=re.IGNORECASE,
            )
            if base_match is None:
                continue
            base_indent = len(base_match.group(1))
            if base_indent >= field_indent:
                break
            base_index = len(prior_lines) - 1 - offset
            base_closed = any(
                len(candidate) - len(candidate.lstrip()) <= base_indent
                and re.fullmatch(r"\s*}[,]?\s*", candidate) is not None
                for candidate in prior_lines[base_index + 1 :]
            )
            if not base_closed:
                return True
            break
        source_evidence_field = re.search(
            r"(?i)^\s*[\"']base_commit[\"']\s*:\s*[\"']?\s*$",
            prefix,
        )
        if source_evidence_field is None:
            return False
        for offset, prior_line in enumerate(reversed(prior_lines)):
            evidence_match = re.fullmatch(
                r"(\s*)[\"']source_evidence[\"']\s*:\s*\{\s*",
                prior_line,
                flags=re.IGNORECASE,
            )
            if evidence_match is None:
                continue
            evidence_indent = len(evidence_match.group(1))
            if evidence_indent >= field_indent:
                break
            evidence_index = len(prior_lines) - 1 - offset
            evidence_closed = any(
                len(candidate) - len(candidate.lstrip()) <= evidence_indent
                and re.fullmatch(r"\s*}[,]?\s*", candidate) is not None
                for candidate in prior_lines[evidence_index + 1 :]
            )
            if not evidence_closed:
                return True
            break
        parent_line = text[:line_start].rstrip("\n").rsplit("\n", 1)[-1].strip()
        return (
            re.search(
                r"(?i)^\s*[\"']commit[\"']\s*:\s*[\"']?\s*$",
                prefix,
            )
            is not None
            and re.fullmatch(r"(?i)[\"']base[\"']\s*:\s*\{", parent_line) is not None
        )
    if len(value) not in {64, 96, 128}:
        return False
    current_line_prefix = text[line_start : match.start()]
    previous_line = text[:line_start].rstrip("\n").rsplit("\n", 1)[-1]
    if (
        current_line_prefix.strip().startswith(("`", "\"", "'"))
        and re.search(
            r"\b(?:sha-?(?:1|224|256|384|512)|hash|digest|checksum)\b\s+is\s*[\"'`]?\s*$",
            previous_line,
            flags=re.IGNORECASE,
        )
        is not None
    ):
        return True
    if (
        re.search(
            r"(?:\|\s*`[^`\r\n]+`\s*\|\s*`?|\|\s*[\"'][^\"'\r\n]+[\"']\s*\|\s*[\"']?)$",
            prefix,
        )
        is not None
    ):
        return True
    if (
        re.search(
            r"(?i)(?:^|[\"'])\s*_?(?:source|decision)[_-]sha-?"
            r"(?:1|224|256|384|512)?\s*[\"']?\s*[:=]\s*[\"']?\s*$",
            prefix,
        )
        is not None
    ):
        return True
    if (
        re.search(
            r"[\"']?\s*\b(?:sha-?(?:1|224|256|384|512)?|checksum|digest|hash|commit|manifest)\b"
            r"[\"']?(?:\s+(?:hash|digest))?\s*[:=]\s*[\"']?\s*$",
            prefix,
            flags=re.IGNORECASE,
        )
        is not None
    ):
        return True
    if (
        re.search(
            r"\b(?:sha-?(?:1|224|256|384|512)|hash|digest|checksum)\b\s+is\s*[\"'`]?\s*$",
            prefix,
            flags=re.IGNORECASE,
        )
        is not None
    ):
        return True
    if (
        re.search(
            r"\b(?:current\s+HEAD|declared\s+base)\b\s*[\"'`]?\s*$",
            prefix,
            flags=re.IGNORECASE,
        )
        is not None
    ):
        return True
    if (
        re.search(
            r"[\"'][A-Za-z0-9_./-]+\.(?:md|json|py|mjs|ts|tsx|yaml|yml|toml|txt)"
            r"[\"']\s*:\s*[\"']\s*$",
            prefix,
        )
        is not None
    ):
        return True
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    suffix = text[match.end() : line_end]
    if not re.fullmatch(r"\s*[\"']\s*", suffix):
        return False
    prior_lines = text[:line_start].splitlines()
    for prior_line in reversed(prior_lines):
        if not prior_line.strip():
            continue
        return (
            re.fullmatch(
                r"\s*-\s*[\"'][^\"']+\.(?:md|json|py|mjs|ts|tsx|yaml|yml|toml|txt)"
                r"[\"']\s*:\s*",
                prior_line,
                flags=re.IGNORECASE,
            )
            is not None
        )
    return False
