"""Read-only workflow recommendation orchestration over safe harvest results."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from tmcp_runtime.domain.harvest_labels import WORKFLOW_SIGNAL_GUIDANCE_LABEL_IDS
from tmcp_runtime.domain.harvest_nodes import (
    SourceAdvisories,
    json_list,
    node_signal_text,
)
from tmcp_runtime.domain.workflow_adaptive import (
    build_adaptive_workflow_pack,
    custom_workflow_ideas,
    recommended_scoped_packet_seeds,
)
from tmcp_runtime.domain.workflow_catalog import (
    experimental_workflow_ids,
    select_workflow_catalog,
    stable_workflow_ids,
    workflow_stability,
)
from tmcp_runtime.domain.workflow_recommendations import (
    recommendation_reason,
    score_workflow_signal,
    workflow_instance,
    workflow_rubric_seed,
    workflow_template,
)
from tmcp_runtime.services.harvest import harvest_skills


ComposePreview = Callable[[], dict[str, Any]]


def recommend_workflows(
    arguments: Mapping[str, Any],
    *,
    source_advisories: SourceAdvisories | None = None,
    compose_preview: ComposePreview | None = None,
) -> dict[str, Any]:
    """Build a recommendation from a safe harvest without persisting artifacts."""

    objective = str(
        arguments.get("objective")
        or "Recommend custom TMCP workflows from harvested skill signals."
    )
    harvest_args = dict(arguments)
    harvest_args["objective"] = objective
    harvest_args["write_artifacts"] = False
    harvest = harvest_skills(
        harvest_args,
        source_advisories=source_advisories,
    )
    source_nodes = [
        item
        for item in json_list(harvest.get("source_nodes"))
        if isinstance(item, dict)
    ]
    catalog = select_workflow_catalog(arguments.get("candidate_workflows"))
    min_confidence = float(arguments.get("min_confidence") or 0.25)
    scores = sorted(
        (
            score_workflow_signal(
                workflow,
                source_nodes,
                node_signal_text=node_signal_text,
                signal_guidance_label_ids=WORKFLOW_SIGNAL_GUIDANCE_LABEL_IDS,
            )
            for workflow in catalog
        ),
        key=lambda item: (
            float(item["confidence"]),
            float(item["score"]),
            str(item["workflow_id"]),
        ),
        reverse=True,
    )
    workflows_by_id = {str(item["workflow_id"]): item for item in catalog}
    recommended: list[dict[str, Any]] = []
    not_recommended: list[dict[str, Any]] = []
    for score in scores:
        workflow = workflows_by_id[str(score["workflow_id"])]
        if score["confidence"] >= min_confidence and score["evidence"]:
            recommended.append(
                {
                    "id": workflow["workflow_id"],
                    "name": workflow["name"],
                    "stability": workflow_stability(workflow),
                    "signal_family": workflow["signal_family"],
                    "confidence": score["confidence"],
                    "score": score["score"],
                    "why": recommendation_reason(score),
                    "evidence": score["evidence"],
                    "starter_prompt": workflow["starter_prompt"],
                    "expected_artifacts": list(workflow["expected_artifacts"]),
                    "template": workflow_template(workflow),
                    "workflow_instance": workflow_instance(
                        workflow=workflow,
                        objective=objective,
                        harvest=harvest,
                        score=score,
                    ),
                    "rubric_seed": workflow_rubric_seed(workflow, objective),
                }
            )
        else:
            not_recommended.append(
                {
                    "id": workflow["workflow_id"],
                    "stability": workflow_stability(workflow),
                    "signal_family": workflow["signal_family"],
                    "confidence": score["confidence"],
                    "reason": recommendation_reason(score),
                }
            )
    primary = [item["signal_family"] for item in recommended[:2]]
    secondary = [
        item["signal_family"]
        for item in recommended[2:]
        if item["signal_family"] not in primary
    ]
    weak = [
        item["signal_family"]
        for item in scores
        if 0 < float(item["confidence"]) < min_confidence
        and item["signal_family"] not in primary
        and item["signal_family"] not in secondary
    ]
    priority_profile = {
        "primary_signals": primary,
        "secondary_signals": secondary,
        "weak_signals": sorted(set(weak)),
        "evidence": [
            {
                "signal_family": item["signal_family"],
                "workflow_id": item["workflow_id"],
                "stability": item["stability"],
                "confidence": item["confidence"],
                "evidence": item["evidence"][:3],
            }
            for item in scores
            if item["evidence"]
        ][:6],
        "workflow_stability": {
            "stable_public_workflows": stable_workflow_ids(),
            "experimental_workflows": experimental_workflow_ids(),
            "policy": (
                "Stable workflows are the public first-release contract. "
                "Experimental workflows remain callable and are labeled in outputs."
            ),
        },
    }
    scoped_packet_seeds = recommended_scoped_packet_seeds(source_nodes)
    custom_ideas = custom_workflow_ideas(source_nodes, recommended)
    adaptive_pack = build_adaptive_workflow_pack(
        harvest=harvest,
        source_nodes=source_nodes,
        priority_profile=priority_profile,
        recommended=recommended,
        recommended_scoped_packet_seeds=scoped_packet_seeds,
        not_recommended=not_recommended,
        custom_workflow_ideas=custom_ideas,
    )
    result: dict[str, Any] = {
        "ok": True,
        "adapter": "standalone",
        "schema": "tmcp-workflow-recommendation-v1",
        "source_harvest": {
            "schema": harvest.get("schema"),
            "source_paths": harvest.get("source_paths", []),
            "source_count": harvest.get("source_count", 0),
            "matched_source_count": harvest.get("matched_source_count", 0),
            "redaction_summary": harvest.get("redaction_summary", {}),
            "warnings": harvest.get("warnings", []),
            "skipped_sources_and_why": harvest.get("warnings", []),
        },
        "output_contract": [
            "sources inspected",
            "skipped sources and why",
            "packet summary",
            "extracted behavior atoms",
            "evidence gaps",
            "recommendation or remediation plan",
            "verification expectations",
        ],
        "priority_profile": priority_profile,
        "signal_scores": scores,
        "recommended_scoped_packet_seeds": scoped_packet_seeds,
        "recommended_workflows": recommended,
        "custom_workflow_ideas": custom_ideas,
        "adaptive_workflow_pack": adaptive_pack,
        "not_recommended": not_recommended,
        "quality_rules": [
            "Recommendations cite harvested evidence.",
            "Workflow stability is labeled as stable or experimental.",
            "Weak signals are not promoted above the confidence threshold.",
            "Privacy redaction remains enabled by default.",
            "Recommendations are advisory until the user selects a workflow.",
            "Implementation remains approval-gated.",
        ],
    }
    if bool(arguments.get("compose", False)):
        if compose_preview is None:
            raise ValueError(
                "Recommendation compose preview requires adapter callback."
            )
        result["composed_packet"] = compose_preview()
    return result
