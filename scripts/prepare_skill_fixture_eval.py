#!/usr/bin/env python3
"""Prepare no-call TMCP evaluation plans for selected skill fixture versions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.tmcp_skill_evaluate import build_evaluation_plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--skill-id", required=True)
    parser.add_argument("--version", action="append", choices=["original", "candidate"], default=[])
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill = next((item for item in manifest.get("skills", []) if item.get("skill_id") == args.skill_id), None)
    if skill is None:
        raise SystemExit(f"unknown skill_id: {args.skill_id}")
    cases = skill.get("cases") or []
    if not cases:
        raise SystemExit(
            f"{args.skill_id} has no golden case and bar; refusing to invent evaluation input"
        )
    versions = args.version or ["original", "candidate"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    for version in versions:
        version_info = skill["versions"][version]
        skill_path = (manifest_path.parent / version_info["path"]).resolve()
        if not skill_path.is_file() or skill_path.name != "SKILL.md":
            raise SystemExit(f"{args.skill_id}/{version} is not an included skill body")
        task_fixtures = [
            {
                "id": case["case_id"],
                "prompt": case["prompt"],
                "expected_observables": case.get("observables", []),
            }
            for case in cases
        ]
        plan = build_evaluation_plan({
            "skill_paths": [str(skill_path)],
            "task_fixtures": task_fixtures,
            "variants": ["baseline", version, "negative_control"],
        })
        output = args.output_dir / f"{args.skill_id}--{version}.json"
        output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        outputs.append(str(output))
    print(json.dumps({
        "schema": "tmcp-skill-fixture-eval-preparation-v0.1",
        "skill_id": args.skill_id,
        "versions": versions,
        "case_count": len(cases),
        "plans": outputs,
        "model_calls": 0,
        "golden_bar_included_in_plan": False,
        "candidate_proposals": {
            "bundle_sha256": skill["versions"]["candidate"].get("proposal_bundle_sha256"),
            "application_mode": skill["versions"]["candidate"].get("proposal_application_mode"),
            "applied_proposal_ids": skill["versions"]["candidate"].get("applied_proposal_ids", []),
            "skipped_proposal_ids": skill["versions"]["candidate"].get("skipped_proposal_ids", []),
        },
        "note": "The plan carries the case prompt; judges must receive the bar separately and never the expected outcome.",
    }, indent=2))


if __name__ == "__main__":
    main()
