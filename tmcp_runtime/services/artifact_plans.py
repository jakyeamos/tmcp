"""Pure artifact manifest assembly for adapter-owned persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tmcp_runtime.domain.review_results import (
    render_audit_markdown,
    render_remediation_plan_markdown,
    render_rubric_markdown,
)
from tmcp_runtime.domain.workflow_adaptive import (
    render_workflow_recommendations_markdown,
)
from tmcp_runtime.domain.workflow_promotion import render_promotion_markdown


@dataclass(frozen=True)
class ArtifactPlan:
    """Already-safe artifact content and the response aliases for its paths."""

    json_artifacts: dict[str, Any]
    text_artifacts: dict[str, str]
    path_aliases: dict[str, str]


def build_review_artifact_plan(
    *,
    expertise_packet: dict[str, Any],
    rubric: dict[str, Any],
    audit_report: dict[str, Any],
    remediation_plan: dict[str, Any],
    implementation_handoff: dict[str, Any],
) -> ArtifactPlan:
    """Build the review artifacts from values redacted by the adapter."""

    safe_packet = dict(expertise_packet)
    safe_rubric = dict(rubric)
    safe_audit_report = dict(audit_report)
    safe_remediation_plan = dict(remediation_plan)
    safe_handoff = dict(implementation_handoff)
    return ArtifactPlan(
        json_artifacts={
            "expertise-packet.json": safe_packet,
            "rubric.json": safe_rubric,
            "audit-report.json": safe_audit_report,
            "remediation-plan.json": safe_remediation_plan,
            "implementation-handoff.json": safe_handoff,
        },
        text_artifacts={
            "rubric.md": render_rubric_markdown(safe_rubric),
            "audit-report.md": render_audit_markdown(safe_audit_report),
            "remediation-plan.md": render_remediation_plan_markdown(
                safe_remediation_plan
            ),
        },
        path_aliases={
            "expertise_packet": "expertise-packet.json",
            "rubric_json": "rubric.json",
            "rubric_markdown": "rubric.md",
            "audit_report_json": "audit-report.json",
            "audit_report_markdown": "audit-report.md",
            "remediation_plan_json": "remediation-plan.json",
            "remediation_plan_markdown": "remediation-plan.md",
            "implementation_handoff_json": "implementation-handoff.json",
        },
    )


def build_workflow_recommendation_artifact_plan(
    result: dict[str, Any],
) -> ArtifactPlan:
    """Build recommendation artifacts from an adapter-redacted result."""

    safe_result = dict(result)
    json_artifacts: dict[str, Any] = {
        "workflow-recommendations.json": safe_result,
    }
    path_aliases = {
        "recommendation_json": "workflow-recommendations.json",
        "recommendation_markdown": "workflow-recommendations.md",
    }
    profile = safe_result.get("priority_profile")
    if isinstance(profile, dict):
        json_artifacts["priority-profile.json"] = dict(profile)
        path_aliases["priority_profile_json"] = "priority-profile.json"
    adaptive_pack = safe_result.get("adaptive_workflow_pack")
    if isinstance(adaptive_pack, dict):
        json_artifacts["adaptive-workflow-pack.json"] = dict(adaptive_pack)
        path_aliases["adaptive_pack_json"] = "adaptive-workflow-pack.json"
    return ArtifactPlan(
        json_artifacts=json_artifacts,
        text_artifacts={
            "workflow-recommendations.md": render_workflow_recommendations_markdown(
                safe_result
            ),
        },
        path_aliases=path_aliases,
    )


def build_promotion_artifact_plan(result: dict[str, Any]) -> ArtifactPlan:
    """Build local promotion artifacts from an adapter-redacted result."""

    safe_result = dict(result)
    json_artifacts: dict[str, Any] = {
        "promoted-harvest.json": safe_result,
    }
    path_aliases = {
        "promotion_json": "promoted-harvest.json",
        "promotion_markdown": "promoted-harvest.md",
    }
    graph = safe_result.get("promotion_graph")
    if isinstance(graph, dict):
        json_artifacts["promotion-graph.json"] = dict(graph)
        path_aliases["promotion_graph_json"] = "promotion-graph.json"
    adaptive_pack = safe_result.get("adaptive_workflow_pack")
    if isinstance(adaptive_pack, dict):
        json_artifacts["adaptive-workflow-pack.json"] = dict(adaptive_pack)
        path_aliases["adaptive_pack_json"] = "adaptive-workflow-pack.json"
    return ArtifactPlan(
        json_artifacts=json_artifacts,
        text_artifacts={"promoted-harvest.md": render_promotion_markdown(safe_result)},
        path_aliases=path_aliases,
    )


def build_global_promotion_artifact_plan(
    *,
    promotion_summary: dict[str, Any],
    promotion_graph: dict[str, Any],
    adaptive_workflow_pack: dict[str, Any] | None,
) -> ArtifactPlan:
    """Build the global-promotion artifact manifest from safe adapter values."""

    json_artifacts: dict[str, Any] = {
        "promoted-harvest.json": dict(promotion_summary),
        "promotion-graph.json": dict(promotion_graph),
    }
    path_aliases = {
        "promotion_json": "promoted-harvest.json",
        "promotion_graph_json": "promotion-graph.json",
    }
    if adaptive_workflow_pack is not None:
        json_artifacts["adaptive-workflow-pack.json"] = dict(adaptive_workflow_pack)
        path_aliases["adaptive_pack_json"] = "adaptive-workflow-pack.json"
    return ArtifactPlan(
        json_artifacts=json_artifacts,
        text_artifacts={},
        path_aliases=path_aliases,
    )
