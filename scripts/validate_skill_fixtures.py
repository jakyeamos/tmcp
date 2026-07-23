#!/usr/bin/env python3
"""Fail-closed validation for generated skill fixture versions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


VARIANTS = {"baseline", "original", "negative_control", "candidate"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--ready-only", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    issues: list[str] = []
    if payload.get("schema") != "tmcp-skill-fixture-manifest-v0.1":
        issues.append("manifest schema is invalid")
    policy = payload.get("policy") or {}
    if policy != {
        "blind": True,
        "requires_golden_case": True,
        "requires_bar": True,
        "auto_rewrite": False,
    }:
        issues.append("manifest policy weakens the blind/bar/auto-rewrite contract")
    skills = payload.get("skills")
    if not isinstance(skills, list) or not skills:
        issues.append("manifest has no skills")
        skills = []
    ids: set[str] = set()
    ready = 0
    for index, skill in enumerate(skills):
        prefix = f"skills[{index}]"
        skill_id = skill.get("skill_id")
        if not isinstance(skill_id, str) or skill_id in ids:
            issues.append(f"{prefix} has a duplicate or invalid skill_id")
        ids.add(str(skill_id))
        source = Path(str(skill.get("source_path", ""))).resolve()
        source_hash = skill.get("source_sha256")
        if not source.is_file():
            issues.append(f"{prefix} source is missing: {source}")
        elif digest(source) != source_hash:
            issues.append(f"{prefix} source digest changed: {source}")
        versions = skill.get("versions")
        if not isinstance(versions, dict) or set(versions) != VARIANTS:
            issues.append(f"{prefix} must contain exactly {sorted(VARIANTS)} versions")
            versions = {}
        skill_root = manifest_path.parent / "skills" / str(skill_id)
        for variant in VARIANTS:
            item = versions.get(variant) or {}
            if item.get("kind") != variant or item.get("parent_sha256") != source_hash:
                issues.append(f"{prefix}.{variant} has invalid lineage")
            target = (manifest_path.parent / str(item.get("path", ""))).resolve()
            if manifest_path.parent not in target.parents:
                issues.append(f"{prefix}.{variant} escapes fixture root")
            if not target.is_file():
                issues.append(f"{prefix}.{variant} target is missing: {target}")
            if target.is_file() and digest(target) != item.get("content_sha256"):
                issues.append(f"{prefix}.{variant} content digest is wrong")
            if variant == "original" and target.is_file() and digest(target) != source_hash:
                issues.append(f"{prefix}.original does not match source digest")
            if variant == "baseline" and item.get("selection") != "omitted":
                issues.append(f"{prefix}.baseline must be omitted")
        cases = skill.get("cases") or []
        if cases:
            ready += 1
            for case in cases:
                if not all(isinstance(case.get(field), str) and case[field].strip() for field in ("case_id", "prompt", "bar")):
                    issues.append(f"{prefix} has a case missing case_id, prompt, or bar")
        elif skill.get("readiness") != "needs_golden_case_and_bar":
            issues.append(f"{prefix} without cases must require a golden case and bar")
    if args.ready_only and ready == 0:
        issues.append("no ready fixtures are available")
    report = {
        "schema": "tmcp-skill-fixture-validation-v0.1",
        "manifest": str(manifest_path),
        "skill_count": len(skills),
        "ready_count": ready,
        "issues": issues,
        "passed": not issues,
    }
    print(json.dumps(report, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
