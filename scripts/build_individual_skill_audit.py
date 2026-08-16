#!/usr/bin/env python3
"""Build a per-skill audit registry without upgrading static warnings to failures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "tmcp-individual-skill-audit-v0.1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path, help="static corpus audit JSON")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def next_case(warning_ids: list[str]) -> dict[str, Any]:
    if "trigger.overbroad-description" in warning_ids:
        return {
            "case_shape": "paired_trigger_boundary",
            "purpose": "Compare an in-scope request with a nearby unrelated request and observe activation boundaries.",
            "required_bar": "Activate only for the in-scope request, remain inactive for the unrelated control, and answer both tasks directly.",
        }
    if "output.missing-observable-contract" in warning_ids:
        return {
            "case_shape": "concrete_output_contract",
            "purpose": "Give the skill a bounded artifact task with a known condition and a required response structure.",
            "required_bar": "Report the requested result with named sources, verification evidence, skipped-source disclosure, and next actions where applicable.",
        }
    if "reads.buried-required-reads" in warning_ids:
        return {
            "case_shape": "required_read_available_unavailable",
            "purpose": "Test a task where a required source is available and a paired task where it is unavailable.",
            "required_bar": "Name required reads early, disclose unavailable sources, and do not silently proceed as if they were read.",
        }
    if "verification.vague-quality-language" in warning_ids:
        return {
            "case_shape": "exact_verification_condition",
            "purpose": "Give the skill an exact target condition that can be checked with a concrete command or observation.",
            "required_bar": "Run or name an observable check and report a supported pass/fail result.",
        }
    if "host.tool-assumption" in warning_ids:
        return {
            "case_shape": "host_tool_unavailable_control",
            "purpose": "Remove the assumed host-specific tool and provide a portable fallback.",
            "required_bar": "Use an available portable path or explain the precise blocker; do not fail solely because the assumed host tool is absent.",
        }
    return {
        "case_shape": "domain_golden_case_required",
        "purpose": "Admit a task-shaped case from a real source or fixture before making a behavioral claim.",
        "required_bar": "Define a concrete input, evidence boundary, and judgment bar from the skill's output contract; do not invent expected output.",
    }


def build_record(skill: dict[str, Any]) -> dict[str, Any]:
    warnings = skill.get("warnings", [])
    warning_ids = sorted({str(item.get("pattern_id")) for item in warnings})
    has_output_warning = "output.missing-observable-contract" in warning_ids
    return {
        "skill_path": str(skill.get("path", "")),
        "source_sha256": str(skill.get("sha256", "")),
        "bytes": int(skill.get("bytes", 0)),
        "warning_count": int(skill.get("warning_count", 0)),
        "warning_ids": warning_ids,
        "warnings": warnings,
        "static_status": "static_findings" if warning_ids else "no_static_findings",
        "observed_failure_status": "not_established",
        "observed_failure_refs": [],
        "definition_of_done_status": (
            "missing_or_underspecified_output_contract"
            if has_output_warning
            else "not_assessed_by_static_audit"
        ),
        "definition_of_done_note": (
            "The static finding is a hypothesis about observable output structure; a runtime failure still requires a concrete case and independent judgment."
            if has_output_warning
            else "This audit does not infer that a definition of done exists or is absent; admit a behavior case before making that claim."
        ),
        "recommended_next_case": next_case(warning_ids),
        "proposal_status": "reviewable_static_proposal" if warning_ids else "no_static_proposal",
        "promotion_status": "blocked_until_behavioral_evidence",
    }


def main() -> None:
    args = parse_args()
    source = args.audit.resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema") != "tmcp-skill-corpus-audit-v0.1":
        raise SystemExit("audit input has the wrong schema")
    skills = payload.get("skills")
    if not isinstance(skills, list):
        raise SystemExit("audit input has no skills list")
    records = [build_record(skill) for skill in skills]
    counts: dict[str, int] = {}
    for record in records:
        for warning_id in record["warning_ids"]:
            counts[warning_id] = counts.get(warning_id, 0) + 1
    output = {
        "schema": SCHEMA,
        "source_audit": str(source),
        "source_audit_sha256": sha256(source),
        "source_scope": payload.get("scope", []),
        "skill_count": len(records),
        "skills_with_static_findings": sum(record["warning_count"] > 0 for record in records),
        "skills_without_static_findings": sum(record["warning_count"] == 0 for record in records),
        "warning_count": sum(record["warning_count"] for record in records),
        "warning_skill_counts": dict(sorted(counts.items())),
        "policy": {
            "static_findings_are_hypotheses": True,
            "observed_failure_requires_case_and_independent_judge": True,
            "definition_of_done_is_not_inferred": True,
            "automatic_rewrite": False,
        },
        "skills": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA,
        "output": str(args.output.resolve()),
        "skill_count": len(records),
        "warning_count": output["warning_count"],
        "skills_with_static_findings": output["skills_with_static_findings"],
        "skills_without_static_findings": output["skills_without_static_findings"],
    }, indent=2))


if __name__ == "__main__":
    main()
