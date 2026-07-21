#!/usr/bin/env python3
"""Audit the checked-in skill guidebook against its evidence catalog.

The audit is intentionally read-only.  It verifies that machine-readable
patterns and the human guidebook describe the same entries, that projections
cannot strengthen claims, and that controlled claims point at source-only
evidence before they can become promotion candidates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "docs" / "SKILL_PATTERN_CATALOG.json"
DEFAULT_GUIDEBOOK = ROOT / "docs" / "SKILL_WRITING_GUIDEBOOK.md"
DEFAULT_EVIDENCE_ROOT = ROOT / "docs" / "evidence"
AUDIT_SCHEMA = "tmcp-skill-guidebook-audit-v0.2"
EVIDENCE_LEVELS = {
    "hypothesis",
    "static_review",
    "dogfooded",
    "controlled_single_agent_eval",
    "controlled_multi_agent_eval",
    "production_reinforced",
    "deprecated",
}
CONTROLLED_LEVELS = {
    "controlled_single_agent_eval",
    "controlled_multi_agent_eval",
    "production_reinforced",
}
HELD_BOUNDARY = "Every currently shipped entry is on `hold`."


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _text_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return ()
    return (
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt", ".jsonl"}
    )


def _evidence_contains(root: Path, needle: str) -> bool:
    for path in _text_files(root):
        content = _read_text_safely(path)
        if content is not None and needle in content:
            return True
    return False


def _read_text_safely(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _index_objects(
    values: Any,
    *,
    field: str,
    issues: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(values, list):
        issues.append(f"catalog {field} must be a list")
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            issues.append(f"{field}[{index}] must be an object")
            continue
        pattern_id = value.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id.strip():
            issues.append(f"{field}[{index}] has no non-empty pattern_id")
            continue
        if pattern_id in indexed:
            issues.append(f"duplicate {field} pattern_id: {pattern_id}")
            continue
        indexed[pattern_id] = value
    return indexed


def _audit_entry(
    pattern_id: str,
    entry: dict[str, Any],
    *,
    guidebook: str,
    evidence_root: Path,
    issues: list[str],
) -> None:
    title = entry.get("title")
    if not isinstance(title, str) or not title.strip():
        issues.append(f"{pattern_id} has no title")
    elif title not in guidebook:
        issues.append(f"{pattern_id} title is absent from the writing guidebook")

    evidence_level = entry.get("evidence_level")
    if evidence_level not in EVIDENCE_LEVELS:
        issues.append(f"{pattern_id} has unknown evidence_level: {evidence_level!r}")

    promotion = entry.get("promotion")
    if not isinstance(promotion, dict):
        issues.append(f"{pattern_id} has no promotion object")
        promotion = {}
    eligible = promotion.get("eligible")
    decision = promotion.get("decision")
    if not isinstance(eligible, bool) or not isinstance(decision, str):
        issues.append(f"{pattern_id} has malformed promotion state")
    elif eligible != (decision == "eligible_for_manual_review"):
        issues.append(f"{pattern_id} promotion decision/eligible state disagrees")
    if evidence_level in CONTROLLED_LEVELS:
        experiment = entry.get("experiment")
        if not isinstance(experiment, str) or not experiment.strip():
            issues.append(f"{pattern_id} controlled claim has no experiment id")
        elif not _evidence_contains(evidence_root, experiment):
            issues.append(
                f"{pattern_id} experiment id {experiment} is absent from evidence"
            )
    if not eligible and HELD_BOUNDARY not in guidebook:
        issues.append("guidebook is missing the held-entry promotion boundary")


def audit_guidebook(
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    guidebook_path: Path = DEFAULT_GUIDEBOOK,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
) -> dict[str, Any]:
    """Return a fail-closed audit report without mutating any input."""

    catalog = _read_json(catalog_path)
    guidebook = guidebook_path.read_text(encoding="utf-8")
    issues: list[str] = []
    if catalog.get("schema") != "tmcp-skill-pattern-catalog-v0.1":
        issues.append("catalog schema is not tmcp-skill-pattern-catalog-v0.1")

    entries = _index_objects(
        catalog.get("guidebook_entries"), field="guidebook_entries", issues=issues
    )
    projections = _index_objects(
        catalog.get("patterns"), field="patterns", issues=issues
    )
    if not entries:
        issues.append("catalog guidebook_entries must contain at least one entry")
    if not projections:
        issues.append("catalog patterns must contain at least one projection")

    for pattern_id, entry in entries.items():
        if pattern_id not in guidebook:
            issues.append(f"{pattern_id} is absent from the writing guidebook")
        _audit_entry(
            pattern_id,
            entry,
            guidebook=guidebook,
            evidence_root=evidence_root,
            issues=issues,
        )

    for pattern_id, projection in projections.items():
        source = entries.get(pattern_id)
        if source is None:
            issues.append(f"catalog projection has no guidebook entry: {pattern_id}")
            continue
        for field in ("evidence_level", "status"):
            if projection.get(field) != source.get(field):
                issues.append(f"projection changed {field} for {pattern_id}")
        source_promotion = source.get("promotion") or {}
        projection_promotion = projection.get("promotion") or {}
        for field in ("decision", "eligible"):
            if projection_promotion.get(field) != source_promotion.get(field):
                issues.append(f"projection changed promotion {field} for {pattern_id}")
        if not set(source_promotion.get("gaps") or []).issubset(
            set(projection_promotion.get("gaps") or [])
        ):
            issues.append(f"projection weakened promotion gaps for {pattern_id}")

    for pattern_id in entries:
        if pattern_id not in projections:
            issues.append(f"guidebook entry has no catalog projection: {pattern_id}")

    controlled_claims = sum(
        1
        for entry in entries.values()
        if entry.get("evidence_level") in CONTROLLED_LEVELS
    )
    return {
        "schema": AUDIT_SCHEMA,
        "passed": not issues,
        "catalog_path": str(catalog_path),
        "guidebook_path": str(guidebook_path),
        "evidence_root": str(evidence_root),
        "entry_count": len(entries),
        "projection_count": len(projections),
        "controlled_claim_count": controlled_claims,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--guidebook", type=Path, default=DEFAULT_GUIDEBOOK)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit_guidebook(
            catalog_path=args.catalog,
            guidebook_path=args.guidebook,
            evidence_root=args.evidence_root,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"schema": AUDIT_SCHEMA, "passed": False, "issues": [str(exc)]}
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
