"""Pure evaluator rendering and advisory formatting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def render_guidebook_markdown(
    entries: list[dict[str, Any]],
    *,
    evidence_levels: Sequence[str],
) -> str:
    """Render guidebook entries without reading files or choosing output paths."""

    lines = [
        "# TMCP Skill Writing Guidebook",
        "",
        "Experimental v0.1 artifact generated from skill evaluation findings.",
        "",
        "## Evidence levels",
        "",
        "Every pattern claim should carry an evidence level:",
        "",
    ]
    lines.extend(f"- `{level}`" for level in evidence_levels)
    lines.extend(["", "## Patterns", ""])
    for entry in entries:
        lines.extend(
            [
                f"### {entry['title']}",
                "",
                f"**Status:** {entry['status']}",
                f"**Evidence level:** {entry['evidence_level']}",
                f"**Applies to:** {', '.join(entry.get('applies_to') or []) or 'skill_writing'}",
                f"**Internal atoms:** {', '.join(entry.get('internal_atoms') or []) or 'none'}",
                "",
                "Prefer:",
                "",
                f"> {entry['prefer']}",
                "",
                "Avoid:",
                "",
                f"> {entry['avoid']}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def build_pattern_catalog(
    entries: list[dict[str, Any]],
    *,
    patterns: Sequence[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    """Build the serializable pattern catalog from supplied pattern data."""

    entry_by_id = {
        str(entry.get("pattern_id")): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("pattern_id")
    }
    projected_patterns: list[dict[str, Any]] = []
    for pattern in patterns:
        pattern_id = str(pattern["pattern_id"])
        entry = entry_by_id.get(pattern_id, {})
        projection = {
            "pattern_id": pattern_id,
            "label": pattern["label"],
            "classification": pattern["classification"],
            "evidence_level": entry.get(
                "evidence_level", pattern.get("evidence_level", "static_review")
            ),
            "internal_atoms": list(pattern["internal_atoms"]),
            "good_example": pattern.get("good_example"),
            "weak_example": pattern.get("weak_example"),
            "detection_terms": list(pattern.get("detection_terms") or ()),
        }
        for field in ("status", "promotion"):
            if field in entry:
                projection[field] = entry[field]
        projected_patterns.append(projection)
    return {
        "schema": "tmcp-skill-pattern-catalog-v0.1",
        "created_at": created_at,
        "patterns": projected_patterns,
        "guidebook_entries": entries,
    }


def merge_pattern_catalog(
    builtins: Sequence[dict[str, Any]],
    discovered: Sequence[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge safe built-ins with an already-decoded catalog payload."""

    patterns = {str(item["pattern_id"]): dict(item) for item in builtins}
    for item in discovered:
        if not isinstance(item, dict):
            continue
        pattern_id = str(item.get("pattern_id") or "")
        if not pattern_id:
            continue
        merged = dict(patterns.get(pattern_id, {}))
        merged.update(item)
        patterns[pattern_id] = merged
    return patterns


def matched_term(finding: dict[str, Any], pattern: dict[str, Any]) -> str:
    """Find the first catalog term visible in the finding excerpt."""

    excerpt = str((finding.get("location") or {}).get("excerpt") or "").lower()
    for term in pattern.get("detection_terms") or ():
        if str(term).lower() in excerpt:
            return str(term)
    return str(pattern.get("weak_example") or pattern.get("label") or "pattern")


def format_harvest_warning(
    finding: dict[str, Any],
    pattern: dict[str, Any],
) -> str:
    """Format one advisory warning from safe finding and catalog data."""

    pattern_id = str(pattern.get("pattern_id") or "")
    matched = matched_term(finding, pattern)
    if pattern_id == "verification.vague-quality-language":
        return (
            f"Skill may contain a verification no-op: '{matched}' has no concrete "
            f"command or observable gate ({finding.get('skill_path')})."
        )
    return (
        f"Skill may contain {str(pattern.get('label') or 'an anti-pattern').lower()}: "
        f"{pattern.get('suggested_harvest_warning') or finding.get('message')} "
        f"({finding.get('skill_path')})."
    )


def build_harvest_advisories(
    findings: Sequence[dict[str, Any]],
    patterns: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build safe-to-emit harvest warnings from supplied findings and patterns."""

    advisories: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("classification") != "anti_pattern":
            continue
        pattern = patterns.get(str(finding.get("pattern_id") or ""))
        if not pattern or not pattern.get("safe_to_auto_warn", True):
            continue
        advisories.append(
            {
                "pattern_id": finding["pattern_id"],
                "classification": finding["classification"],
                "warning": format_harvest_warning(finding, pattern),
                "suggested_harvest_warning": pattern.get("suggested_harvest_warning"),
                "suggested_detection_terms": list(pattern.get("detection_terms") or ()),
                "internal_atoms": list(
                    finding.get("internal_atoms") or pattern.get("internal_atoms") or ()
                ),
                "safe_to_auto_warn": True,
                "safe_to_auto_rewrite": False,
                "evidence_level": finding.get("evidence_level", "static_review"),
            }
        )
    return advisories
