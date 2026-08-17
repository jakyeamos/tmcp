from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA = "tmcp-individual-skill-behavior-dispositions-v0.1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        variant = result.get("variant")
        parsed = result.get("parsed_judge")
        if variant not in {"original", "candidate"} or not isinstance(parsed, dict):
            continue
        by_variant[variant].append(result)
    versions: dict[str, Any] = {}
    for variant in ("original", "candidate"):
        cells = by_variant[variant]
        decisions = [cell["parsed_judge"].get("decision") for cell in cells]
        scores = [cell["parsed_judge"].get("overall_weighted_score") for cell in cells]
        versions[variant] = {
            "cell_count": len(cells),
            "pass_count": sum(decision == "pass" for decision in decisions),
            "fail_count": sum(decision == "fail" for decision in decisions),
            "decisions": decisions,
            "mean_score": round(sum(scores) / len(scores), 4) if scores else None,
            "skill_sha256": sorted(
                {
                    skill_sha
                    for cell in cells
                    if isinstance(skill_sha := cell.get("skill_sha256"), str)
                }
            ),
        }
    return {"versions": versions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("admission_registry", type=Path)
    parser.add_argument("disposition_input", type=Path)
    parser.add_argument("--campaign", action="append", type=Path, required=True)
    parser.add_argument(
        "--exclude-case-from",
        action="append",
        default=[],
        metavar="CAMPAIGN=CASE_ID",
        help="ignore a case only from a campaign that used an older case definition",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    excluded_cases: dict[Path, set[str]] = defaultdict(set)
    for value in args.exclude_case_from:
        campaign_text, separator, case_id = value.partition("=")
        if not separator or not campaign_text or not case_id:
            raise ValueError("--exclude-case-from must be CAMPAIGN=CASE_ID")
        excluded_cases[Path(campaign_text).resolve()].add(case_id)

    admission = load(args.admission_registry)
    disposition_input = load(args.disposition_input)
    if admission.get("schema") != "tmcp-individual-skill-admission-v0.1":
        raise ValueError("unexpected admission registry schema")
    if (
        disposition_input.get("schema")
        != "tmcp-individual-skill-behavior-disposition-input-v0.1"
    ):
        raise ValueError("unexpected disposition input schema")

    registry_cases: dict[str, dict[str, Any]] = {}
    for skill in admission.get("skills", []):
        for case in skill.get("cases", []):
            registry_cases[case["case_id"]] = {
                "skill_path": skill["skill_path"],
                "source_sha256": skill["source_sha256"],
                "admission_status": case["admission_status"],
            }

    campaign_cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    campaigns: list[dict[str, Any]] = []
    for campaign_path in args.campaign:
        campaign = load(campaign_path)
        if campaign.get("schema") != "tmcp-mined-skill-fixture-campaign-v0.1":
            raise ValueError(f"unexpected campaign schema: {campaign_path}")
        campaigns.append(
            {
                "report_path": str(campaign_path),
                "report_sha256": sha256(campaign_path),
                "manifest": campaign.get("manifest"),
                "model": campaign.get("model"),
                "reasoning_effort": campaign.get("reasoning_effort"),
                "runner_count": campaign.get("runner_count"),
                "judge_count": campaign.get("judge_count"),
            }
        )
        ignored = excluded_cases.get(campaign_path.resolve(), set())
        for result in campaign.get("results", []):
            if result["case_id"] in ignored:
                continue
            campaign_cases[result["case_id"]].append(result)

    disposition_by_case = {
        item["case_id"]: item for item in disposition_input.get("cases", [])
    }
    if set(disposition_by_case) != set(registry_cases):
        missing = sorted(set(registry_cases) - set(disposition_by_case))
        extra = sorted(set(disposition_by_case) - set(registry_cases))
        raise ValueError(f"disposition case mismatch; missing={missing}, extra={extra}")

    cases: list[dict[str, Any]] = []
    for case_id, registry_case in sorted(registry_cases.items()):
        disposition = disposition_by_case[case_id]
        results = campaign_cases.get(case_id, [])
        case = {
            **registry_case,
            "case_id": case_id,
            "campaign_cell_count": len(results),
            **summarize(results),
            "disposition": disposition["disposition"],
            "observed_skill_failure": disposition["observed_skill_failure"],
            "rewrite_status": disposition["rewrite_status"],
            "rationale": disposition["rationale"],
            "next_action": disposition["next_action"],
        }
        if case["observed_skill_failure"] and case["admission_status"] != "case_ready":
            raise ValueError(
                f"skill failure cannot be claimed for unadmitted case {case_id}"
            )
        cases.append(case)

    output = {
        "schema": SCHEMA,
        "generated_from": {
            "admission_registry": str(args.admission_registry),
            "admission_registry_sha256": sha256(args.admission_registry),
            "disposition_input": str(args.disposition_input),
            "disposition_input_sha256": sha256(args.disposition_input),
            "campaigns": campaigns,
        },
        "policy": {
            "independent_judging_required": True,
            "repeatable_failure_required": True,
            "case_quality_and_runner_boundaries_are_separate": True,
            "automatic_rewrite": False,
        },
        "summary": {
            "case_count": len(cases),
            "campaign_ready_case_count": sum(
                case["campaign_cell_count"] > 0 for case in cases
            ),
            "observed_skill_failure_count": sum(
                case["observed_skill_failure"] for case in cases
            ),
            "rewrite_hold_count": sum(
                case["rewrite_status"] == "hold" for case in cases
            ),
            "no_candidate_delta_count": sum(
                case["rewrite_status"] == "no_candidate_delta" for case in cases
            ),
            "behaviorally_passed_case_count": sum(
                case["disposition"] == "behavioral_baseline_pass" for case in cases
            ),
            "case_or_runner_boundary_count": sum(
                case["disposition"]
                in {"case_boundary_blocked", "runner_boundary_blocked"}
                for case in cases
            ),
        },
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
