#!/usr/bin/env python3
"""Audit discovered skill fixtures for explicit golden-case coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "tmcp-skill-fixture-coverage-audit-v0.1"


def audit_manifest(
    manifest: Mapping[str, object], *, manifest_bytes: bytes | None = None
) -> dict[str, Any]:
    skills = manifest.get("skills")
    errors: list[str] = []
    if not isinstance(skills, list):
        return {
            "schema": SCHEMA,
            "manifest_schema": manifest.get("schema"),
            "errors": ["manifest skills must be a list"],
            "manifest_integrity_pass": False,
            "corpus_promotion_ready": False,
        }

    readiness = Counter()
    case_ids: list[str] = []
    skills_with_cases: list[str] = []
    ready_without_cases: list[str] = []
    for index, skill in enumerate(skills):
        if not isinstance(skill, dict):
            errors.append(f"skills[{index}] is not an object")
            continue
        skill_id = skill.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id:
            errors.append(f"skills[{index}] has no skill_id")
            skill_id = f"skills[{index}]"
        status = skill.get("readiness")
        if not isinstance(status, str):
            errors.append(f"{skill_id}: readiness is missing")
            status = "unknown"
        readiness[status] += 1
        cases = skill.get("cases", [])
        if not isinstance(cases, list):
            errors.append(f"{skill_id}: cases must be a list")
            cases = []
        if cases:
            skills_with_cases.append(skill_id)
        if status == "ready" and not cases:
            ready_without_cases.append(skill_id)
        for case_index, case in enumerate(cases):
            if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
                errors.append(f"{skill_id}: cases[{case_index}] has no case_id")
                continue
            case_ids.append(case["case_id"])

    duplicate_case_ids = sorted(
        case_id for case_id, count in Counter(case_ids).items() if count > 1
    )
    if duplicate_case_ids:
        errors.append(f"duplicate case_id values: {', '.join(duplicate_case_ids)}")
    unready_count = sum(
        count for status, count in readiness.items() if status != "ready"
    )
    return {
        "schema": SCHEMA,
        "manifest_schema": manifest.get("schema"),
        "fixture_set_id": manifest.get("fixture_set_id"),
        "skill_count": len(skills),
        "readiness_counts": dict(sorted(readiness.items())),
        "ready_skill_count": readiness.get("ready", 0),
        "skills_with_cases_count": len(skills_with_cases),
        "case_count": len(case_ids),
        "case_id_count": len(set(case_ids)),
        "duplicate_case_ids": duplicate_case_ids,
        "ready_without_cases": ready_without_cases,
        "needs_case_or_bar_count": unready_count,
        "coverage_rate": (len(skills_with_cases) / len(skills)) if skills else 0.0,
        "manifest_integrity_pass": not errors,
        "corpus_promotion_ready": not errors
        and not ready_without_cases
        and unready_count == 0,
        "errors": errors,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest()
        if manifest_bytes is not None
        else None,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise SystemExit("manifest must contain a JSON object")
    report = audit_manifest(manifest, manifest_bytes=manifest_bytes)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["manifest_integrity_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
