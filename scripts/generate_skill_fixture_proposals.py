#!/usr/bin/env python3
"""Generate review-only proposal bundles from TMCP static guidebook findings."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tmcp_runtime.services.evaluation_catalog import EFFECTIVE_PATTERNS, V01_ANTI_PATTERNS
from tmcp_runtime.services.evaluation_policy import (
    _variant_payload,
    decompose_skill,
    static_review,
)


SCHEMA = "tmcp-skill-fixture-proposals-v0.1"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def proposal_for_skill(skill: dict[str, Any], manifest_root: Path) -> dict[str, Any]:
    skill_id = str(skill["skill_id"])
    original = (manifest_root / str(skill["versions"]["original"]["path"])).resolve()
    if not original.is_file() or original.name != "SKILL.md" or manifest_root not in original.parents:
        raise SystemExit(f"{skill_id}: original fixture is missing or escapes fixture root")
    source_sha256 = str(skill["source_sha256"])
    content = original.read_text(encoding="utf-8")
    if digest(original) != source_sha256:
        raise SystemExit(f"{skill_id}: original fixture digest does not match manifest")
    decomposition = decompose_skill(str(original), content)
    findings = static_review(
        decomposition,
        content,
        anti_patterns=V01_ANTI_PATTERNS,
        effective_patterns=EFFECTIVE_PATTERNS,
    )
    anti_findings = [item for item in findings if item.get("classification") == "anti_pattern"]
    proposals: list[dict[str, Any]] = []
    if anti_findings:
        replacement = str(_variant_payload("rewritten", decomposition, content)["content"])
        if replacement != content:
            replacement_sha256 = digest_bytes(replacement.encode("utf-8"))
            pattern_ids = sorted({str(item["pattern_id"]) for item in anti_findings})
            proposals.append({
                "proposal_id": "guidebook-rewrite-v0.1",
                "status": "proposed",
                "target": "SKILL.md",
                "reason": (
                    "Review-only guidebook rewrite for static findings: "
                    + ", ".join(pattern_ids)
                ),
                "before_sha256": source_sha256,
                "after_sha256": replacement_sha256,
                "replacement": replacement,
            })
    return {
        "schema": SCHEMA,
        "skill_id": skill_id,
        "source_sha256": source_sha256,
        "proposals": proposals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    skills = payload.get("skills")
    if not isinstance(skills, list) or not skills:
        raise SystemExit("manifest has no skills")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for skill in skills:
        bundle = proposal_for_skill(skill, manifest_path.parent)
        path = output / f"{bundle['skill_id']}.json"
        path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
        results.append({
            "skill_id": bundle["skill_id"],
            "path": str(path),
            "proposal_count": len(bundle["proposals"]),
            "review_status": "proposed",
        })
    print(json.dumps({
        "schema": "tmcp-skill-fixture-proposal-generation-v0.1",
        "manifest": str(manifest_path),
        "skill_count": len(results),
        "skills_with_proposals": sum(item["proposal_count"] > 0 for item in results),
        "proposal_count": sum(item["proposal_count"] for item in results),
        "review_status": "proposed",
        "bundles": results,
    }, indent=2))


if __name__ == "__main__":
    main()
