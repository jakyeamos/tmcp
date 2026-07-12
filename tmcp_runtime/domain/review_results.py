"""Deterministic review remediation, handoff, validation, and Markdown policy."""

from __future__ import annotations

from typing import Any

from .standalone_packets import TMCP_PACKET_SCHEMA


REMEDIATION_PLAN_SCHEMA = "tmcp-expert-remediation-plan-v0.1"
IMPLEMENTATION_HANDOFF_SCHEMA = "tmcp-expert-implementation-handoff-v0.1"


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def build_remediation_plan(
    audit_report: dict[str, Any],
    run_id: str,
    evidence_remediation_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slices: list[dict[str, Any]] = []
    for index, finding in enumerate(_json_list(audit_report.get("findings")), start=1):
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("id", f"finding-{index}"))
        evidence = _string_list(finding.get("evidence"))
        slices.append(
            {
                "id": f"slice-{index}",
                "title": str(finding.get("summary", finding_id))[:80],
                "scope": evidence,
                "rationale": str(finding.get("summary", "")),
                "expected_impact": str(finding.get("recommended_fix", "")),
                "risk": "Review scope is limited to cited evidence; inspect neighboring surfaces before editing.",
                "verification": ["Run targeted checks covering the cited evidence."],
                "follow_up_workflow": "implementation-delivery",
                "source_findings": [finding_id],
            }
        )
    coverage_gaps = [
        item
        for item in _json_list(audit_report.get("coverage_gaps"))
        if isinstance(item, dict)
    ]
    if coverage_gaps and _json_list(audit_report.get("findings")):
        profile = str(audit_report.get("profile") or "general_review")
        missing_dimensions = [
            str(
                item.get("dimension_name")
                or item.get("dimension_id")
                or item.get("label")
                or item.get("coverage_id")
            )
            for item in coverage_gaps
            if item.get("dimension_name")
            or item.get("dimension_id")
            or item.get("label")
            or item.get("coverage_id")
        ]
        gap_details = [
            gap for item in coverage_gaps for gap in _string_list(item.get("gaps"))
        ]
        slices.append(
            {
                "id": f"slice-{len(slices) + 1}-profile-coverage",
                "title": "Capture missing profile evidence coverage",
                "scope": [*missing_dimensions, *gap_details],
                "rationale": f"The `{profile}` rubric has required coverage without evidence, so the audit is only partially grounded.",
                "expected_impact": (
                    "Completes profile-specific evidence coverage before remediation is prioritized, so TMCP cannot "
                    "present generic findings as a complete expert review."
                ),
                "risk": "Do not over-rank remediation from partial or off-profile evidence.",
                "verification": [
                    "Capture concrete evidence for every uncovered rubric dimension and profile coverage requirement.",
                    "Re-run the expert rubric review and confirm profile evidence coverage passes.",
                ],
                "follow_up_workflow": "expert-rubric-evidence-audit",
                "source_findings": [],
            }
        )
    if not slices and audit_report.get("deferred_scope"):
        contract_dimensions = _json_list(
            (evidence_remediation_contract or {}).get("required_dimensions")
        )
        contract_scope = [
            (
                f"{item.get('dimension_id')}: "
                f"{'; '.join(_string_list(item.get('evidence_expectations')))}"
            )
            for item in contract_dimensions
            if isinstance(item, dict) and item.get("dimension_id")
        ]
        slices.append(
            {
                "id": "slice-1",
                "title": "Populate dimension-mapped evidence before remediation",
                "scope": contract_scope,
                "rationale": (
                    str(
                        (evidence_remediation_contract or {}).get(
                            "reason",
                            "The rubric could be synthesized, but no actionable evidence was supplied.",
                        )
                    )
                ),
                "expected_impact": (
                    "Produces scored, cited findings and prevents generic evidence records from "
                    "becoming low-value remediation work."
                ),
                "risk": "Do not implement from an evidence-free or contract-invalid rubric.",
                "verification": [
                    "Fill evidence_json from evidence_contract.starter_template.",
                    "Each item must include dimension_id, severity, summary, and non-empty evidence citations.",
                    "Re-run expert_rubric_review_plan and confirm evidence_json_actionable passes.",
                ],
                "follow_up_workflow": "expert-rubric-evidence-audit",
                "source_findings": [],
            }
        )
    return {
        "schema": REMEDIATION_PLAN_SCHEMA,
        "run_id": run_id,
        "slices": slices,
        "coverage_gaps": coverage_gaps,
        "deferred_scope": _string_list(audit_report.get("deferred_scope")),
        "evidence_remediation_contract": evidence_remediation_contract or {},
    }


def build_implementation_handoff(
    remediation_plan: dict[str, Any],
    run_id: str,
    selected_slice_id: str | None,
) -> dict[str, Any]:
    slices = [
        item
        for item in _json_list(remediation_plan.get("slices"))
        if isinstance(item, dict)
    ]
    selected = next(
        (
            item
            for item in slices
            if selected_slice_id and item.get("id") == selected_slice_id
        ),
        slices[0] if slices else {},
    )
    return {
        "schema": IMPLEMENTATION_HANDOFF_SCHEMA,
        "run_id": run_id,
        "remediation_plan": "remediation-plan.json",
        "selected_slice_id": selected.get("id") if selected else selected_slice_id,
        "selected_slice": selected,
        "requires_user_approval": True,
        "follow_up_workflow": str(
            selected.get("follow_up_workflow") or "implementation-delivery"
        )
        if selected
        else "implementation-delivery",
        "artifact_inputs": [
            "expertise-packet.json",
            "rubric.json",
            "audit-report.json",
            "remediation-plan.json",
        ],
        "target_files": _string_list(selected.get("scope")) if selected else [],
        "acceptance_criteria": _string_list(selected.get("verification"))
        if selected
        else [],
        "known_risks": [str(selected.get("risk"))]
        if selected and selected.get("risk")
        else [],
    }


def review_validations(
    packet: dict[str, Any],
    rubric: dict[str, Any],
    audit_report: dict[str, Any],
    remediation_plan: dict[str, Any],
    evidence_diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    coverage_gaps = [
        item
        for item in _json_list(audit_report.get("coverage_gaps"))
        if isinstance(item, dict)
    ]
    profile = str(rubric.get("profile") or "general_review")
    coverage_issues = [
        f"{profile} coverage missing for {item.get('dimension_name') or item.get('dimension_id') or item.get('label') or item.get('coverage_id')}: {'; '.join(_string_list(item.get('gaps')))}"
        for item in coverage_gaps
    ]
    return [
        {
            "validation_key": "tmcp_packet_compiled",
            "passed": packet.get("schema") == TMCP_PACKET_SCHEMA
            and bool(packet.get("selected_nodes")),
            "issues": [],
        },
        {
            "validation_key": "domain_playbook_available",
            "passed": bool(
                isinstance(packet.get("substance_check"), dict)
                and packet["substance_check"].get("has_domain_playbook")
            ),
            "issues": _string_list(
                packet.get("substance_check", {}).get("issues")
                if isinstance(packet.get("substance_check"), dict)
                else ["Packet substance check missing."]
            ),
        },
        {
            "validation_key": "rubric_dimensions_present",
            "passed": bool(rubric.get("dimensions")),
            "issues": [] if rubric.get("dimensions") else ["Rubric has no dimensions."],
        },
        {
            "validation_key": "evidence_json_actionable",
            "passed": bool(
                not evidence_diagnostics
                or not _json_list(evidence_diagnostics.get("item_issues"))
            ),
            "issues": [
                f"evidence[{item.get('index')}]: {'; '.join(_string_list(item.get('issues')))}"
                for item in _json_list((evidence_diagnostics or {}).get("item_issues"))
                if isinstance(item, dict)
            ],
        },
        {
            "validation_key": "profile_evidence_coverage",
            "passed": not coverage_gaps,
            "issues": coverage_issues,
        },
        {
            "validation_key": "findings_have_evidence",
            "passed": all(
                _string_list(item.get("evidence"))
                for item in _json_list(audit_report.get("findings"))
            ),
            "issues": [
                str(item.get("id", "finding"))
                for item in _json_list(audit_report.get("findings"))
                if isinstance(item, dict) and not _string_list(item.get("evidence"))
            ],
        },
        {
            "validation_key": "remediation_has_verification",
            "passed": all(
                _string_list(item.get("verification"))
                for item in _json_list(remediation_plan.get("slices"))
                if isinstance(item, dict)
            ),
            "issues": [],
        },
    ]


def render_rubric_markdown(rubric: dict[str, Any]) -> str:
    lines = [
        f"# Expert Rubric: {rubric['objective']}",
        "",
        f"Profile: `{rubric['profile']}`",
        "",
    ]
    substance = rubric.get("substance_check")
    if isinstance(substance, dict):
        lines.extend(
            [
                "## Packet Substance",
                "",
                f"- Level: `{substance.get('level', 'unknown')}`",
                f"- Fallback policy: {substance.get('fallback_policy', '')}",
                "",
            ]
        )
    for dimension in rubric["dimensions"]:
        lines.extend(
            [
                f"## {dimension['name']}",
                "",
                f"- ID: `{dimension['id']}`",
                f"- Weight: {dimension['weight']}",
                f"- Pass threshold: {dimension['pass_threshold']}/4",
                f"- Source nodes: {', '.join(dimension['source_nodes'])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_audit_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Expert Audit Report: {report['run_id']}", "", "## Scores"]
    for score in report.get("scores", []):
        lines.append(
            f"- `{score['dimension_id']}`: {score['score']}/4 ({score['confidence']} confidence)"
        )
    lines.extend(["", "## Findings"])
    if not report.get("findings"):
        lines.append("- No evidence-backed findings were supplied. See deferred scope.")
    for finding in report.get("findings", []):
        lines.append(
            f"- [{finding['severity']}] {finding['summary']} Evidence: {', '.join(_string_list(finding.get('evidence')))}"
        )
    if report.get("deferred_scope"):
        lines.extend(["", "## Deferred Scope"])
        for item in report["deferred_scope"]:
            lines.append(f"- {item}")
    substance = report.get("substance_check")
    if isinstance(substance, dict):
        lines.extend(["", "## TMCP Substance Check"])
        lines.append(f"- Level: `{substance.get('level', 'unknown')}`")
        lines.append(f"- Fallback policy: {substance.get('fallback_policy', '')}")
    return "\n".join(lines).rstrip() + "\n"


def render_remediation_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [f"# Remediation Plan: {plan['run_id']}", ""]
    for item in plan.get("slices", []):
        lines.extend(
            [
                f"## {item['id']}: {item['title']}",
                "",
                f"- Scope: {', '.join(_string_list(item.get('scope')))}",
                f"- Rationale: {item['rationale']}",
                f"- Expected impact: {item['expected_impact']}",
                f"- Risk: {item['risk']}",
                f"- Verification: {', '.join(_string_list(item.get('verification')))}",
                f"- Follow-up workflow: `{item['follow_up_workflow']}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
