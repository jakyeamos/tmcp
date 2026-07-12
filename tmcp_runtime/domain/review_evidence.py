"""Deterministic evidence contracts, rubrics, and audit-report policy."""

from __future__ import annotations

import json
from typing import Any

from .review_profiles import (
    PROFILE_COVERAGE_REQUIREMENTS,
    profile_dimensions,
    select_review_profile,
)


RUBRIC_SCHEMA = "tmcp-expert-rubric-v0.1"
AUDIT_REPORT_SCHEMA = "tmcp-expert-audit-report-v0.1"


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def parse_evidence(raw: object) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        parsed = json.loads(raw)
    else:
        parsed = raw
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
        return parsed
    raise ValueError("evidence_json must be a JSON object or array of objects.")


def _rubric_dimensions(rubric: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in _json_list(rubric.get("dimensions")) if isinstance(item, dict)
    ]


def _evidence_starter_template(rubric: dict[str, Any]) -> list[dict[str, Any]]:
    template: list[dict[str, Any]] = []
    for dimension in _rubric_dimensions(rubric):
        dimension_id = str(dimension.get("id") or "")
        if not dimension_id:
            continue
        dimension_name = str(dimension.get("name") or dimension_id)
        expectations = _string_list(dimension.get("evidence_expectations"))
        evidence = [
            f"TODO: cite evidence for {dimension_id}: {expectation}"
            for expectation in expectations[:2]
        ] or [f"TODO: cite concrete evidence for {dimension_id}."]
        template.append(
            {
                "dimension_id": dimension_id,
                "severity": "warning",
                "summary": f"TODO: summarize the {dimension_name} issue or evidence gap.",
                "evidence": evidence,
                "recommended_fix": (
                    f"TODO: state the concrete remediation for {dimension_id}."
                ),
            }
        )
    return template


def evidence_contract(rubric: dict[str, Any]) -> dict[str, Any]:
    dimensions = _rubric_dimensions(rubric)
    dimension_ids = [str(item.get("id")) for item in dimensions if item.get("id")]
    return {
        "schema": "tmcp-evidence-contract-v0.1",
        "required_fields": ["dimension_id", "severity", "summary", "evidence"],
        "optional_fields": ["recommended_fix"],
        "severity_values": ["blocker", "warning", "observation"],
        "dimension_ids": dimension_ids,
        "evidence_requirement": (
            "`evidence` must contain concrete citations such as file paths, artifact paths, "
            "command outputs, screenshots, or named local facts. Empty arrays produce "
            "a starter template instead of findings."
        ),
        "starter_template": _evidence_starter_template(rubric),
        "example": {
            "dimension_id": dimension_ids[0] if dimension_ids else "source_grounding",
            "severity": "warning",
            "summary": "Release verification has not been fully cited.",
            "evidence": [
                "pytest: 162 passed",
                "ruff format --check: failed on generated artifacts",
            ],
            "recommended_fix": "Capture the failing format paths and rerun the release gate.",
        },
    }


def _evidence_item_issues(
    item: dict[str, Any],
    dimension_ids: set[str],
) -> list[str]:
    issues: list[str] = []
    dimension_id = str(item.get("dimension_id") or "")
    if not dimension_id:
        issues.append(
            "Missing `dimension_id`; the item cannot produce a scored finding."
        )
    elif dimension_id not in dimension_ids:
        issues.append(f"Unknown `dimension_id` `{dimension_id}`.")
    severity = str(item.get("severity") or "")
    if not severity:
        issues.append("Missing `severity`; use blocker, warning, or observation.")
    elif severity not in {"blocker", "warning", "observation"}:
        issues.append(
            f"Unknown `severity` `{severity}`; use blocker, warning, or observation."
        )
    if not str(item.get("summary") or "").strip():
        issues.append("Missing `summary`; the item cannot produce a useful finding.")
    if not _string_list(item.get("evidence")):
        issues.append("Missing non-empty `evidence`; findings will not be traceable.")
    if item.get("kind") and not dimension_id:
        issues.append(
            "`kind` is caller metadata only; use `dimension_id` to map evidence to the rubric."
        )
    return issues


def evidence_diagnostics(
    rubric: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> dict[str, Any]:
    dimensions = _rubric_dimensions(rubric)
    dimension_ids = {str(item.get("id")) for item in dimensions if item.get("id")}
    item_issues: list[dict[str, Any]] = []
    mapped_dimension_ids: set[str] = set()
    for index, item in enumerate(evidence_items, start=1):
        dimension_id = str(item.get("dimension_id") or "")
        if dimension_id in dimension_ids:
            mapped_dimension_ids.add(dimension_id)
        issues = _evidence_item_issues(item, dimension_ids)
        if issues:
            item_issues.append({"index": index, "issues": issues})
    missing_dimensions = [
        str(item.get("id"))
        for item in dimensions
        if item.get("id") and str(item.get("id")) not in mapped_dimension_ids
    ]
    return {
        "schema": "tmcp-evidence-diagnostics-v0.1",
        "input_state": "empty" if not evidence_items else "provided",
        "actionable": bool(evidence_items) and not item_issues,
        "item_issues": item_issues,
        "missing_dimensions": missing_dimensions,
        "guidance": (
            "Supply one or more evidence objects per relevant rubric dimension. "
            "Generic records such as `{kind: checks, pytest: ...}` are accepted as JSON "
            "but are not enough for scored, cited findings unless they include "
            "`dimension_id`, `summary`, and non-empty `evidence`."
        ),
    }


def actionable_evidence_items(
    rubric: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    dimensions = _rubric_dimensions(rubric)
    dimension_ids = {str(item.get("id")) for item in dimensions if item.get("id")}
    return [
        item
        for item in evidence_items
        if not _evidence_item_issues(item, dimension_ids)
    ]


def evidence_remediation_contract(
    rubric: dict[str, Any],
    evidence_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    required_dimensions: list[dict[str, Any]] = []
    for dimension in _rubric_dimensions(rubric):
        dimension_id = str(dimension.get("id") or "")
        if not dimension_id:
            continue
        required_dimensions.append(
            {
                "dimension_id": dimension_id,
                "dimension_name": str(dimension.get("name") or dimension_id),
                "evidence_expectations": _string_list(
                    dimension.get("evidence_expectations")
                ),
                "source_nodes": _string_list(dimension.get("source_nodes")),
            }
        )
    return {
        "schema": "tmcp-evidence-remediation-contract-v0.1",
        "status": (
            "missing_evidence"
            if evidence_diagnostics.get("input_state") == "empty"
            else "invalid_evidence_json"
        ),
        "reason": (
            "No evidence_json records were supplied."
            if evidence_diagnostics.get("input_state") == "empty"
            else "One or more evidence_json records did not satisfy the rubric evidence contract."
        ),
        "contract_citations": [
            "rubric.json:dimensions[].id",
            "rubric.json:dimensions[].evidence_expectations",
            "expertise-packet.json:selected_nodes",
        ],
        "required_dimensions": required_dimensions,
        "invalid_items": _json_list(evidence_diagnostics.get("item_issues")),
        "starter_template": _evidence_starter_template(rubric),
        "next_action": (
            "Replace generic records with dimension-mapped evidence_json objects, "
            "then rerun expert_rubric_review_plan."
        ),
    }


def _dimension(
    *,
    dimension: dict[str, Any],
    source_nodes: list[str],
) -> dict[str, Any]:
    return {
        "id": dimension["id"],
        "name": dimension["name"],
        "weight": dimension["weight"],
        "scale": "0-4",
        "pass_threshold": 3,
        "evidence_expectations": dimension["expectations"],
        "review_questions": dimension["questions"],
        "source_nodes": source_nodes or ["@task:agent_workflow"],
    }


def synthesize_rubric(
    packet: dict[str, Any], run_id: str, objective: str
) -> dict[str, Any]:
    source_nodes = _string_list(packet.get("selected_nodes"))
    profile = select_review_profile(objective, packet)
    return {
        "schema": RUBRIC_SCHEMA,
        "run_id": run_id,
        "objective": objective,
        "source_packet": "expertise-packet.json",
        "profile": profile,
        "substance_check": packet.get("substance_check", {}),
        "coverage_requirements": list(PROFILE_COVERAGE_REQUIREMENTS.get(profile, ())),
        "selected_nodes": source_nodes,
        "skipped_nodes": packet.get("skipped_nodes", []),
        "dimensions": [
            _dimension(dimension=dimension, source_nodes=source_nodes)
            for dimension in profile_dimensions(profile)
        ],
    }


def _severity_rank(severity: str) -> int:
    return {"blocker": 0, "warning": 1, "observation": 2}.get(severity, 1)


def _severity_score(severity: str) -> int:
    return {"blocker": 1, "warning": 2, "observation": 3}.get(severity, 2)


def _profile_coverage_gaps(
    rubric: dict[str, Any],
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requirements = [
        item
        for item in _json_list(rubric.get("coverage_requirements"))
        if isinstance(item, dict)
    ]
    if not requirements:
        return []
    text_parts: list[str] = []
    for finding in findings:
        text_parts.extend(
            [
                str(finding.get("summary", "")),
                str(finding.get("recommended_fix", "")),
                " ".join(_string_list(finding.get("evidence"))),
            ]
        )
    finding_text = " ".join(text_parts).lower()
    gaps: list[dict[str, Any]] = []
    for requirement in requirements:
        terms = [term.lower() for term in _string_list(requirement.get("terms"))]
        if not any(term in finding_text for term in terms):
            issue = str(
                requirement.get("issue")
                or requirement.get("label")
                or "Profile evidence coverage is missing."
            )
            gaps.append(
                {
                    "coverage_id": str(requirement.get("id") or "profile_coverage"),
                    "label": str(
                        requirement.get("label")
                        or requirement.get("id")
                        or "profile coverage"
                    ),
                    "gaps": [issue],
                }
            )
    return gaps


def _known_dimension_id(candidate: object, dimensions: list[dict[str, Any]]) -> str:
    ids = [str(dimension["id"]) for dimension in dimensions]
    value = str(candidate or "")
    if value in ids:
        return value
    return ids[0] if ids else "general_review"


def build_audit_report(
    rubric: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    dimensions = [
        item for item in _json_list(rubric.get("dimensions")) if isinstance(item, dict)
    ]
    findings: list[dict[str, Any]] = []
    evidence_by_dimension: dict[str, list[str]] = {}
    for index, item in sorted(
        enumerate(evidence_items, start=1),
        key=lambda indexed: _severity_rank(str(indexed[1].get("severity", "warning"))),
    ):
        dimension_id = _known_dimension_id(item.get("dimension_id"), dimensions)
        severity = str(item.get("severity", "warning"))
        if severity not in {"blocker", "warning", "observation"}:
            severity = "warning"
        evidence = _string_list(item.get("evidence"))
        evidence_by_dimension.setdefault(dimension_id, []).extend(evidence)
        findings.append(
            {
                "id": f"finding-{dimension_id}-{index}",
                "severity": severity,
                "dimension_id": dimension_id,
                "summary": str(item.get("summary", "Evidence item requires review.")),
                "evidence": evidence,
                "recommended_fix": str(
                    item.get("recommended_fix", "Remediate the cited evidence.")
                ),
            }
        )
    scores: list[dict[str, Any]] = []
    coverage_gaps: list[dict[str, Any]] = []
    for dimension in dimensions:
        dimension_id = str(dimension["id"])
        matching = [
            finding for finding in findings if finding["dimension_id"] == dimension_id
        ]
        evidence = evidence_by_dimension.get(dimension_id, [])
        if matching:
            score = min(
                _severity_score(str(finding["severity"])) for finding in matching
            )
            gaps: list[str] = []
            confidence = "high" if evidence else "low"
        else:
            score = 0
            gaps = [f"No evidence supplied for {dimension_id}."]
            confidence = "low"
        scores.append(
            {
                "dimension_id": dimension_id,
                "score": score,
                "confidence": confidence,
                "evidence": evidence,
                "gaps": gaps,
            }
        )
        if gaps:
            coverage_gaps.append(
                {
                    "dimension_id": dimension_id,
                    "dimension_name": str(dimension.get("name", dimension_id)),
                    "gaps": gaps,
                }
            )
    substance = (
        rubric.get("substance_check")
        if isinstance(rubric.get("substance_check"), dict)
        else {}
    )
    deferred_items = [
        gap for score in scores for gap in _string_list(score.get("gaps"))
    ]
    if substance and not bool(substance.get("has_domain_playbook")):
        deferred_items.extend(_string_list(substance.get("issues")))
    coverage_gaps.extend(_profile_coverage_gaps(rubric, findings))
    for item in coverage_gaps:
        deferred_items.extend(_string_list(item.get("gaps")))
    deferred_scope: list[str] = []
    for item in deferred_items:
        if item not in deferred_scope:
            deferred_scope.append(item)
    return {
        "schema": AUDIT_REPORT_SCHEMA,
        "run_id": run_id,
        "rubric": "rubric.json",
        "profile": str(rubric.get("profile") or "general_review"),
        "substance_check": substance,
        "scores": scores,
        "findings": findings,
        "coverage_gaps": coverage_gaps,
        "deferred_scope": deferred_scope,
    }
