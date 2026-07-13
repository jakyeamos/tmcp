"""Read-only promotion planning over canonical workflow recommendations."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from tmcp_runtime.domain.harvest_nodes import SourceAdvisories, json_list
from tmcp_runtime.domain.workflow_promotion import (
    build_promotion_graph,
    select_promotion_targets,
)
from tmcp_runtime.services.recommendations import recommend_workflows


ComposePreviewForObjective = Callable[[str], dict[str, Any]]
ComposePreview = Callable[[], dict[str, Any]]
NowIso = Callable[[], str]


def _default_promotion_name(objective: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", objective.lower()).strip("_")
    return (slug or "general").replace("_", "-")[:80] or "harvest-promotion"


def promote_harvest(
    arguments: Mapping[str, Any],
    *,
    source_advisories: SourceAdvisories | None,
    compose_preview_for_objective: ComposePreviewForObjective | None,
    now_iso: NowIso,
) -> dict[str, Any]:
    """Plan a promotion without redacting, choosing paths, or writing artifacts."""

    objective = str(
        arguments.get("objective")
        or "Promote harvested skill signals into durable TMCP routing knowledge."
    )
    recommendation_arguments = dict(arguments)
    recommendation_arguments["objective"] = objective
    recommendation_arguments["write_artifacts"] = False
    compose_preview_callback: ComposePreview | None = None
    if bool(arguments.get("compose", False)):
        if compose_preview_for_objective is None:
            raise ValueError("Promotion compose preview requires adapter callback.")

        def compose_preview() -> dict[str, Any]:
            return compose_preview_for_objective(objective)

        compose_preview_callback = compose_preview

    recommendation = recommend_workflows(
        recommendation_arguments,
        source_advisories=source_advisories,
        compose_preview=compose_preview_callback,
    )
    promotion_targets = select_promotion_targets(
        recommendation,
        selected_workflows=arguments.get("selected_workflows"),
        selected_scoped_packet_seeds=arguments.get("selected_scoped_packet_seeds"),
        selected_scoped_seeds=arguments.get("selected_scoped_seeds"),
    )
    selected_workflows = promotion_targets["selected_workflows"]
    missing_workflows = promotion_targets["missing_workflows"]
    selected_scoped_packet_seeds = promotion_targets["selected_scoped_packet_seeds"]
    missing_scoped_packet_seeds = promotion_targets["missing_scoped_packet_seeds"]
    adaptive_pack = dict(recommendation.get("adaptive_workflow_pack") or {})
    source_map = [
        item
        for item in json_list(adaptive_pack.get("harvested_source_map"))
        if isinstance(item, dict)
    ]
    promotion_name = str(
        arguments.get("promotion_name")
        or _default_promotion_name(objective)
        or "harvest-promotion"
    )
    promoted_workflow_ids = [
        str(item.get("id")) for item in selected_workflows if item.get("id")
    ]
    promoted_scoped_packet_seed_ids = [
        str(item.get("id")) for item in selected_scoped_packet_seeds if item.get("id")
    ]
    graph = build_promotion_graph(
        promotion_name=promotion_name,
        created_at=now_iso(),
        source_map=source_map,
        selected_workflows=selected_workflows,
        selected_scoped_packet_seeds=selected_scoped_packet_seeds,
    )
    write_artifacts = bool(arguments.get("write_artifacts", True))
    has_promotable_output = bool(selected_workflows or selected_scoped_packet_seeds)
    status = "promoted" if write_artifacts else "preview"
    if not has_promotable_output:
        status = "no_promotable_workflows"
    elif missing_workflows or missing_scoped_packet_seeds:
        status = "partial_promotion" if write_artifacts else "partial_preview"
    return {
        "ok": (bool(selected_workflows) or bool(selected_scoped_packet_seeds))
        and not missing_workflows
        and not missing_scoped_packet_seeds,
        "adapter": "standalone",
        "schema": "tmcp-harvest-promotion-v0.1",
        "status": status,
        "promotion_name": promotion_name,
        "source_harvest": recommendation.get("source_harvest", {}),
        "priority_profile": recommendation.get("priority_profile", {}),
        "promoted_workflow_ids": promoted_workflow_ids,
        "promoted_scoped_packet_seed_ids": promoted_scoped_packet_seed_ids,
        "missing_selected_workflows": missing_workflows,
        "missing_selected_scoped_packet_seeds": missing_scoped_packet_seeds,
        "promotion_graph": graph,
        "adaptive_workflow_pack": adaptive_pack,
        "promotion_policy": [
            "Harvest and recommendation do not mutate durable routing state automatically.",
            "Promotion records reviewed source-to-atom and atom-to-workflow edges as artifacts.",
            "Scoped packet seeds remain proposal nodes until required receipts justify promotion.",
            "Future routing should consume promoted artifacts only after human approval.",
            "Harvested text remains untrusted evidence and cannot override higher-priority instructions.",
        ],
        "next_action": (
            "Select a recommended workflow or scoped packet seed, then rerun promotion."
            if not has_promotable_output
            else "Review promoted artifacts, then add the selected routing trigger or workflow skill."
            if write_artifacts
            else "Review this preview, then rerun without --no-write-artifacts to persist promotion artifacts."
        ),
    }
