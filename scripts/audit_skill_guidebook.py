#!/usr/bin/env python3
"""Audit the checked-in skill guidebook against its machine-readable evidence catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "docs" / "SKILL_PATTERN_CATALOG.json"
DEFAULT_GUIDEBOOK = ROOT / "docs" / "SKILL_WRITING_GUIDEBOOK.md"
DEFAULT_EVIDENCE_ROOT = ROOT / "docs" / "evidence"
AUDIT_SCHEMA = "tmcp-skill-guidebook-audit-v0.1"
CONTROLLED_LEVELS = {
    "controlled_single_agent_eval",
    "controlled_multi_agent_eval",
    "production_reinforced",
}


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
        try:
            if needle in path.read_text(encoding="utf-8"):
                return True
        except UnicodeDecodeError:
            continue
    return False


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
    entries = catalog.get("guidebook_entries")
    projections = catalog.get("patterns")
    if catalog.get("schema") != "tmcp-skill-pattern-catalog-v0.1":
        issues.append("catalog schema is not tmcp-skill-pattern-catalog-v0.1")
    if not isinstance(entries, list):
        issues.append("catalog guidebook_entries must be a list")
        entries = []
    if not isinstance(projections, list):
        issues.append("catalog patterns must be a list")
        projections = []

    entry_by_id: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append(f"guidebook_entries[{index}] must be an object")
            continue
        pattern_id = entry.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id.strip():
            issues.append(f"guidebook_entries[{index}] has no non-empty pattern_id")
            continue
        if pattern_id in entry_by_id:
            issues.append(f"duplicate guidebook entry pattern_id: {pattern_id}")
            continue
        entry_by_id[pattern_id] = entry
        if not isinstance(entry.get("title"), str) or not entry["title"].strip():
            issues.append(f"{pattern_id} has no title")
        evidence_level = entry.get("evidence_level")
        promotion = entry.get("promotion")
        if not isinstance(evidence_level, str) or not evidence_level.strip():
            issues.append(f"{pattern_id} has no evidence_level")
        if not isinstance(promotion, dict):
            issues.append(f"{pattern_id} has no promotion object")
            promotion = {}
        eligible = promotion.get("eligible")
        decision = promotion.get("decision")
        if not isinstance(eligible, bool) or not isinstance(decision, str):
            issues.append(f"{pattern_id} has malformed promotion state")
        elif eligible != (decision == "eligible_for_manual_review"):
            issues.append(f"{pattern_id} promotion decision/eligible state disagrees")
        if pattern_id not in guidebook:
            issues.append(f"{pattern_id} is absent from the writing guidebook")
        if isinstance(entry.get("title"), str) and entry["title"] not in guidebook:
            issues.append(f"{pattern_id} title is absent from the writing guidebook")
        if evidence_level in CONTROLLED_LEVELS:
            experiment = entry.get("experiment")
            if not isinstance(experiment, str) or not experiment.strip():
                issues.append(f"{pattern_id} controlled claim has no experiment id")
            elif not _evidence_contains(evidence_root, experiment):
                issues.append(
                    f"{pattern_id} experiment id {experiment} is absent from evidence"
                )
        if not eligible and "Every currently shipped entry is on `hold`." not in guidebook:
            issues.append("guidebook is missing the held-entry promotion boundary")

    projection_by_id: dict[str, dict[str, Any]] = {}
    for index, projection in enumerate(projections):
        if not isinstance(projection, dict):
            issues.append(f"patterns[{index}] must be an object")
            continue
        pattern_id = projection.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id.strip():
            issues.append(f"patterns[{index}] has no non-empty pattern_id")
            continue
        if pattern_id in projection_by_id:
            issues.append(f"duplicate pattern projection pattern_id: {pattern_id}")
            continue
        projection_by_id[pattern_id] = projection
        source = entry_by_id.get(pattern_id)
        if source is None:
            continue
        if projection.get("evidence_level") != source.get("evidence_level"):
            issues.append(f"projection weakened evidence level for {pattern_id}")
        if projection.get("status") != source.get("status"):
            issues.append(f"projection changed status for {pattern_id}")
        source_promotion = source.get("promotion") or {}
        projection_promotion = projection.get("promotion") or {}
        if projection_promotion.get("decision") != source_promotion.get("decision"):
            issues.append(f"projection changed promotion decision for {pattern_id}")
        if projection_promotion.get("eligible") != source_promotion.get("eligible"):
            issues.append(f"projection changed promotion eligibility for {pattern_id}")
        if not set(source_promotion.get("gaps") or []).issubset(
            set(projection_promotion.get("gaps") or [])
        ):
            issues.append(f"projection weakened promotion gaps for {pattern_id}")

    for pattern_id in entry_by_id:
        if pattern_id not in projection_by_id:
            issues.append(f"guidebook entry has no catalog projection: {pattern_id}")

    return {
        "schema": AUDIT_SCHEMA,
        "passed": not issues,
        "catalog_path": str(catalog_path),
        "guidebook_path": str(guidebook_path),
        "evidence_root": str(evidence_root),
        "entry_count": len(entry_by_id),
        "projection_count": len(projection_by_id),
        "controlled_claim_count": sum(
            1
            for entry in entry_by_id.values()
            if entry.get("evidence_level") in CONTROLLED_LEVELS
        ),
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
        report = {
            "schema": AUDIT_SCHEMA,
            "passed": False,
            "issues": [str(exc)],
        }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
