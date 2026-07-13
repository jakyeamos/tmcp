"""Pure adaptive workflow-pack construction and recommendation Markdown policy."""

from __future__ import annotations

import re
from typing import Any

from .workflow_recommendations import source_scope_for


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "general"


def _scoped_seed_routing_trigger(seed: dict[str, Any]) -> str:
    seed_id = str(seed.get("id") or seed.get("seed_id") or "scoped_packet_seed")
    return (
        f"Use TMCP scoped packet seed `{seed_id}` when the task matches its curated "
        "use_when conditions and the required receipt evidence exists."
    )


def recommended_scoped_packet_seeds(
    source_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for node in source_nodes:
        if str(node.get("source_type") or "") != "scoped_packet_seed":
            continue
        seed_id = str(node.get("seed_id") or node.get("id") or "").strip()
        if not seed_id:
            continue
        recommendations.append(
            {
                "id": seed_id,
                "name": str(node.get("title") or seed_id),
                "kind": "scoped_packet_seed",
                "basis": "curated_scoped_packet_seed",
                "confidence": 1.0,
                "promotion_status": str(
                    node.get("promotion_status") or "proposal_not_promoted"
                ),
                "promote_as_single_global_graph": bool(
                    node.get("promote_as_single_global_graph", False)
                ),
                "relative_path": node.get("relative_path"),
                "canonical_source": node.get("canonical_source"),
                "source_references": _string_list(node.get("source_references")),
                "loads": _string_list(node.get("loads")),
                "chains_before": _string_list(node.get("chains_before")),
                "chains_after": _string_list(node.get("chains_after")),
                "do_not_activate_with": _string_list(node.get("do_not_activate_with")),
                "use_when": _string_list(node.get("use_when")),
                "modes": _string_list(node.get("modes")),
                "minimum_spec_fields": _string_list(node.get("minimum_spec_fields")),
                "ticket_types": _string_list(node.get("ticket_types")),
                "behavior_atoms": _string_list(node.get("behavior_atoms")),
                "verification_expectations": _string_list(
                    node.get("verification_expectations")
                ),
                "required_receipts": _string_list(node.get("required_receipts")),
                "guidance_labels": _json_list(node.get("guidance_labels")),
                "routing_trigger": _scoped_seed_routing_trigger(node),
                "approval_required": True,
                "trust": "advisory_untrusted",
                "why": (
                    "Curated scoped packet seed from a constrained TMCP harvest; "
                    "use as a scoped candidate, not as global default behavior."
                ),
            }
        )
    return recommendations


def _count_strings(values: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [
        {"id": key, "count": count}
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def custom_workflow_ideas(
    source_nodes: list[dict[str, Any]], recommended: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    atoms = [
        atom
        for node in source_nodes
        for atom in _string_list(node.get("behavior_atoms"))
    ]
    recommended_families = {
        str(item.get("signal_family"))
        for item in recommended
        if item.get("signal_family")
    }
    ideas: list[dict[str, Any]] = []
    for atom_count in _count_strings(atoms)[:4]:
        atom = str(atom_count["id"])
        if len(ideas) >= 3:
            break
        source_evidence = [
            {
                "relative_path": node.get("relative_path"),
                "source_type": node.get("source_type"),
                "title": node.get("title"),
                "guidance_labels": node.get("guidance_labels", []),
            }
            for node in source_nodes
            if atom in _string_list(node.get("behavior_atoms"))
        ][:3]
        if not source_evidence:
            continue
        idea_id = f"custom_{_slug(atom)}_workflow"
        ideas.append(
            {
                "id": idea_id,
                "name": f"Custom {atom.replace('-', ' ').title()} Workflow",
                "stability": "experimental",
                "basis": "harvested_behavior_atom",
                "behavior_atom": atom,
                "source_count": atom_count["count"],
                "why": (
                    f"Harvested sources repeatedly emphasize `{atom}`; generate a workflow "
                    "around that local operating habit if no default template is specific enough."
                ),
                "source_evidence": source_evidence,
                "suggested_artifacts": [
                    "custom TMCP packet",
                    "source-backed rubric dimensions",
                    "routing trigger",
                    "approval-gated next workflow selection",
                ],
                "routing_trigger": (
                    f"Use TMCP `{idea_id}` when the task depends on harvested `{atom}` behavior "
                    "more than a fixed default workflow."
                ),
                "approval_required": True,
                "related_default_signal_families": sorted(recommended_families),
            }
        )
    return ideas


def _source_overlap_analysis(source_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    clusters: list[dict[str, Any]] = []
    labels_by_id: dict[str, dict[str, Any]] = {}
    sources_by_label: dict[str, list[dict[str, Any]]] = {}
    for node in source_nodes:
        for label in _json_list(node.get("guidance_labels")):
            if not isinstance(label, dict):
                continue
            label_id = str(label.get("id") or "")
            if not label_id:
                continue
            labels_by_id.setdefault(label_id, label)
            sources_by_label.setdefault(label_id, []).append(
                {
                    "relative_path": node.get("relative_path"),
                    "source_type": node.get("source_type"),
                    "source_scope": source_scope_for(str(node.get("path") or "")),
                    "title": node.get("title"),
                    "matched_terms": _string_list(label.get("matched_terms"))[:8],
                }
            )
    for label_id, sources in sorted(sources_by_label.items()):
        unique_sources: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for source in sources:
            path = str(source.get("relative_path") or "")
            if path in seen_paths:
                continue
            seen_paths.add(path)
            unique_sources.append(source)
        if len(unique_sources) < 2:
            continue
        label = labels_by_id[label_id]
        clusters.append(
            {
                "label_id": label_id,
                "label": label.get("label"),
                "summary": label.get("summary"),
                "source_count": len(unique_sources),
                "sources": unique_sources[:6],
                "recommended_action": "consolidate_or_rank",
                "decision_rule": (
                    "Prefer the highest-priority local source when labels duplicate; "
                    "preserve distinct matched terms as supporting context."
                ),
            }
        )
    clusters.sort(key=lambda item: (-int(item["source_count"]), str(item["label_id"])))
    return {
        "policy": (
            "Overlapping harvested sources are not activated as equal instructions. "
            "TMCP labels what each source contributes, consolidates duplicate labels where practical, "
            "and keeps distinct label coverage as supporting context."
        ),
        "clusters": clusters[:12],
    }


def _documented_process_gaps(
    *,
    source_nodes: list[dict[str, Any]],
    recommended: list[dict[str, Any]],
    recommended_scoped_packet_seeds: list[dict[str, Any]],
    not_recommended: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if not source_nodes:
        gaps.append(
            {
                "id": "no_harvested_sources",
                "severity": "high",
                "message": "No source documents were harvested, so TMCP cannot adapt workflows to local behavior.",
            }
        )
    if not recommended and not recommended_scoped_packet_seeds:
        gaps.append(
            {
                "id": "no_default_template_above_threshold",
                "severity": "medium",
                "message": "No default workflow template met the confidence threshold.",
            }
        )
    for item in not_recommended[:4]:
        if not isinstance(item, dict):
            continue
        confidence = float(item.get("confidence") or 0.0)
        if confidence == 0.0:
            gaps.append(
                {
                    "id": f"missing_{item.get('signal_family')}_signals",
                    "severity": "low",
                    "message": f"No meaningful evidence found for `{item.get('signal_family')}`.",
                }
            )
    if not gaps:
        gaps.append(
            {
                "id": "selection_required",
                "severity": "info",
                "message": "Signals are sufficient for recommendations; user approval is still required before applying a workflow.",
            }
        )
    return gaps


def build_adaptive_workflow_pack(
    *,
    harvest: dict[str, Any],
    source_nodes: list[dict[str, Any]],
    priority_profile: dict[str, Any],
    recommended: list[dict[str, Any]],
    recommended_scoped_packet_seeds: list[dict[str, Any]],
    not_recommended: list[dict[str, Any]],
    custom_workflow_ideas: list[dict[str, Any]],
) -> dict[str, Any]:
    scopes = _count_strings(
        [source_scope_for(str(node.get("path") or "")) for node in source_nodes]
    )
    source_types = _count_strings(
        [str(node.get("source_type") or "unknown") for node in source_nodes]
    )
    atoms = _count_strings(
        [
            atom
            for node in source_nodes
            for atom in _string_list(node.get("behavior_atoms"))
        ]
    )
    source_map = [
        {
            "id": node.get("id"),
            "relative_path": node.get("relative_path"),
            "title": node.get("title"),
            "source_type": node.get("source_type"),
            "source_scope": source_scope_for(str(node.get("path") or "")),
            "behavior_atoms": node.get("behavior_atoms", []),
            "guidance_labels": node.get("guidance_labels", []),
            "keywords": _string_list(node.get("keywords"))[:8],
            "routing_metadata": node.get("routing_metadata", {}),
            "source_references": node.get("source_references", []),
            "use_when": node.get("use_when", []),
            "modes": node.get("modes", []),
            "minimum_spec_fields": node.get("minimum_spec_fields", []),
            "ticket_types": node.get("ticket_types", []),
            "verification_expectations": node.get("verification_expectations", []),
            "promotion_status": node.get("promotion_status"),
            "promote_as_single_global_graph": node.get(
                "promote_as_single_global_graph"
            ),
            "required_receipts": node.get("required_receipts", []),
        }
        for node in source_nodes[:12]
    ]
    return {
        "schema": "tmcp-adaptive-workflow-pack-v0.1",
        "artifact_type": "adaptive_workflow_pack",
        "harvested_source_map": source_map,
        "operating_profile": {
            "source_paths": harvest.get("source_paths", []),
            "source_count": harvest.get("source_count", 0),
            "matched_source_count": harvest.get("matched_source_count", 0),
            "source_scope_counts": scopes,
            "source_type_counts": source_types,
            "primary_signals": priority_profile.get("primary_signals", []),
            "secondary_signals": priority_profile.get("secondary_signals", []),
            "weak_signals": priority_profile.get("weak_signals", []),
        },
        "strongest_behavior_signals": atoms[:8],
        "overlap_analysis": _source_overlap_analysis(source_nodes),
        "workflow_stability": {
            "stable_public_workflows": [
                item["id"] for item in recommended if item.get("stability") == "stable"
            ],
            "experimental_workflows": [
                item["id"]
                for item in recommended
                if item.get("stability") == "experimental"
            ],
            "policy": (
                "Experimental workflows remain shipped and callable, but their "
                "public contracts may change."
            ),
        },
        "recommended_default_templates": [
            item["template"]
            for item in recommended
            if isinstance(item.get("template"), dict)
        ],
        "recommended_scoped_packet_seeds": recommended_scoped_packet_seeds,
        "generated_custom_workflow_ideas": custom_workflow_ideas,
        "suggested_routing_triggers": [
            item["routing_trigger"] for item in recommended_scoped_packet_seeds
        ]
        + [
            item["workflow_instance"]["routing_trigger"]
            for item in recommended
            if isinstance(item.get("workflow_instance"), dict)
        ]
        + [item["routing_trigger"] for item in custom_workflow_ideas],
        "documented_process_gaps": _documented_process_gaps(
            source_nodes=source_nodes,
            recommended=recommended,
            recommended_scoped_packet_seeds=recommended_scoped_packet_seeds,
            not_recommended=not_recommended,
        ),
        "next_workflow_selection": {
            "approval_required": True,
            "instruction": "Select one scoped packet seed, default template, or custom workflow idea before running expert_rubric_review_plan.",
            "candidate_scoped_seed_ids": [
                item["id"] for item in recommended_scoped_packet_seeds
            ],
            "candidate_template_ids": [item["id"] for item in recommended],
            "candidate_custom_workflow_ids": [
                item["id"] for item in custom_workflow_ideas
            ],
        },
    }


def render_workflow_recommendations_markdown(result: dict[str, Any]) -> str:
    lines = ["# TMCP Workflow Recommendations", ""]
    profile = result.get("priority_profile", {})
    lines.extend(
        [
            f"- Primary signals: {', '.join(_string_list(profile.get('primary_signals'))) or 'none'}",
            f"- Secondary signals: {', '.join(_string_list(profile.get('secondary_signals'))) or 'none'}",
            f"- Weak signals: {', '.join(_string_list(profile.get('weak_signals'))) or 'none'}",
            "",
            "## Recommended Workflows",
        ]
    )
    recommendations = _json_list(result.get("recommended_workflows"))
    if not recommendations:
        lines.append("- No workflows met the recommendation threshold.")
    for item in recommendations:
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- Confidence: {item['confidence']}",
                f"- Stability: `{item.get('stability', 'experimental')}`",
                f"- Signal family: `{item['signal_family']}`",
                f"- Why: {item['why']}",
                f"- Starter prompt: {item['starter_prompt']}",
                f"- Workflow instance: `{item.get('workflow_instance', {}).get('id', 'pending')}`",
                "",
            ]
        )
    scoped_seeds = _json_list(result.get("recommended_scoped_packet_seeds"))
    if scoped_seeds:
        lines.extend(["## Recommended Scoped Packet Seeds", ""])
        for item in scoped_seeds:
            if isinstance(item, dict):
                lines.append(
                    f"- `{item.get('id')}`: {item.get('promotion_status', 'proposal_not_promoted')}"
                )
        lines.append("")
    lines.extend(["## Custom Workflow Ideas", ""])
    custom_ideas = _json_list(result.get("custom_workflow_ideas"))
    if not custom_ideas:
        lines.append("- No custom workflow ideas were generated.")
    for item in custom_ideas:
        if isinstance(item, dict):
            lines.append(f"- `{item['id']}`: {item['why']}")
    lines.extend(["## Not Recommended", ""])
    for item in _json_list(result.get("not_recommended")):
        if isinstance(item, dict):
            lines.append(f"- `{item['id']}`: {item['reason']}")
    return "\n".join(lines).rstrip() + "\n"
