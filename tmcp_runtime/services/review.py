"""In-memory standalone review-plan assembly without persistence authority."""

from __future__ import annotations

from typing import Any

from tmcp_runtime.domain.harvest_nodes import json_list
from tmcp_runtime.domain.review_evidence import (
    actionable_evidence_items,
    build_audit_report,
    evidence_contract,
    evidence_diagnostics,
    evidence_remediation_contract,
    synthesize_rubric,
)
from tmcp_runtime.domain.review_results import (
    build_implementation_handoff,
    build_remediation_plan,
    review_validations,
)
from tmcp_runtime.domain.standalone_packets import compile_standalone_packet


def build_review_plan(
    *,
    objective: str,
    project_path: str,
    run_id: str,
    evidence_items: list[dict[str, Any]],
    harvested_nodes: list[dict[str, Any]],
    harvest_warnings: list[str],
    selected_slice_id: str | None,
) -> dict[str, Any]:
    """Assemble a review result from already-read, in-memory inputs."""

    packet = compile_standalone_packet(
        objective=objective,
        project_path=project_path,
        phase="planning",
        harvested_nodes=harvested_nodes,
    )
    rubric = synthesize_rubric(packet, run_id, objective)
    review_evidence_contract = evidence_contract(rubric)
    diagnostics = evidence_diagnostics(rubric, evidence_items)
    actionable_items = actionable_evidence_items(rubric, evidence_items)
    remediation_contract = (
        evidence_remediation_contract(rubric, diagnostics)
        if not evidence_items or bool(json_list(diagnostics.get("item_issues")))
        else {}
    )
    audit_report = build_audit_report(rubric, actionable_items, run_id)
    remediation_plan = build_remediation_plan(
        audit_report,
        run_id,
        remediation_contract or None,
    )
    handoff = build_implementation_handoff(
        remediation_plan,
        run_id,
        selected_slice_id,
    )
    invalid_items = bool(json_list(diagnostics.get("item_issues")))
    all_supplied_evidence_invalid = bool(evidence_items) and not actionable_items
    status = "completed"
    if all_supplied_evidence_invalid:
        status = "failed_evidence_contract"
    elif not evidence_items:
        status = "needs_evidence"
    elif invalid_items:
        status = "completed_with_evidence_diagnostics"
    return {
        "ok": not all_supplied_evidence_invalid,
        "adapter": "standalone",
        "schema": "tmcp-review-plan-result-v0.1",
        "workflow_key": "expert_rubric_remediation_v1",
        "run_id": run_id,
        "status": status,
        "output_contract": [
            "sources inspected",
            "skipped sources and why",
            "packet summary",
            "extracted behavior atoms",
            "evidence gaps",
            "recommendation or remediation plan",
            "verification expectations",
        ],
        "validations": review_validations(
            packet,
            rubric,
            audit_report,
            remediation_plan,
            diagnostics,
        ),
        "harvest_warnings": harvest_warnings,
        "evidence_contract": review_evidence_contract,
        "evidence_remediation_contract": remediation_contract,
        "evidence_diagnostics": diagnostics,
        "expertise_packet": packet,
        "rubric": rubric,
        "audit_report": audit_report,
        "remediation_plan": remediation_plan,
        "remediation_slices": remediation_plan["slices"],
        "implementation_handoff": handoff,
        "artifact_paths": {},
    }
