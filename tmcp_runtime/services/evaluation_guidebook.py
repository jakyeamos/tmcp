"""Guidebook claim projection from static findings and behavioral evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.services.evaluation_catalog import EVIDENCE_RANK


def _portable_source_skill_path(value: object) -> str:
    """Keep published guidebook provenance portable across local home directories."""

    source = str(value).replace("\\", "/")
    for home_prefix in ("/Users/", "/home/"):
        if source.startswith(home_prefix):
            parts = source.split("/")
            if len(parts) >= 4:
                return f"~/{'/'.join(parts[3:])}"
    return source


def guidebook_entries(
    *,
    static_findings: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    effective_patterns: Sequence[Mapping[str, Any]],
    anti_pattern_catalog: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build claim-bearing entries without turning hypotheses into recommendations."""

    catalog = {
        str(pattern.get("pattern_id")): dict(pattern)
        for pattern in (*effective_patterns, *anti_pattern_catalog)
    }
    findings_by_pattern: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for finding in static_findings:
        pattern_id = str(finding.get("pattern_id") or "")
        if pattern_id:
            findings_by_pattern[pattern_id].append(finding)
    claims_by_pattern = {
        str(claim.get("pattern_id")): claim
        for claim in claims
        if str(claim.get("pattern_id") or "")
    }
    pattern_ids = sorted(set(findings_by_pattern) | set(claims_by_pattern))
    entries: list[dict[str, Any]] = []
    for pattern_id in pattern_ids:
        pattern = catalog.get(pattern_id)
        if pattern is None:
            continue
        claim = claims_by_pattern.get(pattern_id)
        classification = str(pattern.get("classification") or "effective_pattern")
        evidence_level = str(claim.get("evidence_level")) if claim else "hypothesis"
        if (
            findings_by_pattern.get(pattern_id)
            and EVIDENCE_RANK.get(evidence_level, 0) < EVIDENCE_RANK["static_review"]
        ):
            evidence_level = "static_review"
        chosen_summary = (
            claim.get("controlled_summary")
            if claim
            and EVIDENCE_RANK.get(evidence_level, 0)
            >= EVIDENCE_RANK["controlled_single_agent_eval"]
            else claim.get("observed_summary")
            if claim
            else None
        )
        lift = (
            chosen_summary.get("absolute_lift")
            if isinstance(chosen_summary, Mapping)
            else None
        )
        if claim and claim.get("promotion_eligible"):
            status = "promotion_candidate"
        elif claim and lift is not None and evidence_level != "static_review":
            direction = str(claim.get("expected_effect_direction") or "positive")
            aligned = -float(lift) if direction == "negative" else float(lift)
            status = "supported" if aligned > 0 else "not_supported"
        elif classification == "anti_pattern":
            status = "suspected"
        else:
            status = "candidate"
        entries.append(
            {
                "pattern_id": pattern_id,
                "title": pattern.get("label") or pattern_id,
                "classification": classification,
                "status": status,
                "evidence_level": evidence_level,
                "applies_to": list(pattern.get("applies_to") or ["skill_writing"]),
                "internal_atoms": list(pattern.get("internal_atoms") or []),
                "prefer": pattern.get("good_example") or "",
                "avoid": pattern.get("weak_example") or "",
                "source_skills": sorted(
                    {
                        _portable_source_skill_path(finding.get("skill_path"))
                        for finding in findings_by_pattern.get(pattern_id, [])
                        if finding.get("skill_path")
                    }
                ),
                "effect": (
                    {
                        "absolute_lift": lift,
                        "expected_direction": claim.get(
                            "expected_effect_direction", "positive"
                        ),
                    }
                    if claim
                    else None
                ),
                "sample": dict(chosen_summary)
                if isinstance(chosen_summary, Mapping)
                else None,
                "promotion": (
                    {
                        "eligible": bool(claim.get("promotion_eligible")),
                        "decision": claim.get("promotion_decision"),
                        "gaps": list(claim.get("promotion_gaps") or []),
                    }
                    if claim
                    else {
                        "eligible": False,
                        "decision": "hold",
                        "gaps": ["no behaviorally judged contrast"],
                    }
                ),
            }
        )
    if entries:
        return entries
    return [
        {
            "pattern_id": "evidence.claim-labeling",
            "title": "Evidence levels and confidence",
            "classification": "informational",
            "status": "informational",
            "evidence_level": "hypothesis",
            "applies_to": ["skill_writing"],
            "internal_atoms": [],
            "prefer": "Label guidebook claims with evidence levels.",
            "avoid": "Claim a pattern is production-proven after one static review.",
            "source_skills": [],
            "effect": None,
            "sample": None,
            "promotion": {
                "eligible": False,
                "decision": "hold",
                "gaps": ["no evaluated pattern claims"],
            },
        }
    ]
