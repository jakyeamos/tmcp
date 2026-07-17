"""Pure promotion selection, graph construction, and Markdown policy."""

from __future__ import annotations

import re
from typing import Any

from .scoped_seeds import normalize_scoped_seed, scoped_seed_graph_metadata
from .workflow_catalog import workflow_catalog


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _string_sequence(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    return []


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "general"


def _selected_promotion_workflows(
    recommendation: dict[str, Any], arguments: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    requested = {
        str(item)
        for item in _json_list(arguments.get("selected_workflows"))
        if str(item).strip()
    }
    recommended = [
        item
        for item in _json_list(recommendation.get("recommended_workflows"))
        if isinstance(item, dict)
    ]
    if not requested:
        return recommended, []
    selected: list[dict[str, Any]] = []
    for item in recommended:
        identifiers = {
            str(item.get("id") or ""),
            str(item.get("signal_family") or ""),
            str(item.get("name") or ""),
        }
        if requested.intersection(identifiers):
            selected.append(item)
    missing = sorted(
        requested.difference(
            {
                identifier
                for item in selected
                for identifier in (
                    str(item.get("id") or ""),
                    str(item.get("signal_family") or ""),
                    str(item.get("name") or ""),
                )
            }
        )
    )
    return selected, missing


def _selected_promotion_scoped_packet_seeds(
    recommendation: dict[str, Any], arguments: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    requested = {
        str(item)
        for key in ("selected_scoped_packet_seeds", "selected_scoped_seeds")
        for item in _json_list(arguments.get(key))
        if str(item).strip()
    }
    recommended = [
        item
        for item in _json_list(recommendation.get("recommended_scoped_packet_seeds"))
        if isinstance(item, dict)
    ]
    if not requested:
        return recommended, []
    selected: list[dict[str, Any]] = []
    for item in recommended:
        identifiers = {
            str(item.get("id") or ""),
            str(item.get("name") or ""),
            str(item.get("relative_path") or ""),
        }
        if requested.intersection(identifiers):
            selected.append(item)
    missing = sorted(
        requested.difference(
            {
                identifier
                for item in selected
                for identifier in (
                    str(item.get("id") or ""),
                    str(item.get("name") or ""),
                    str(item.get("relative_path") or ""),
                )
            }
        )
    )
    return selected, missing


def select_promotion_targets(
    recommendation: dict[str, Any],
    *,
    selected_workflows: object,
    selected_scoped_packet_seeds: object,
    selected_scoped_seeds: object,
) -> dict[str, Any]:
    arguments = {
        "selected_workflows": selected_workflows,
        "selected_scoped_packet_seeds": selected_scoped_packet_seeds,
        "selected_scoped_seeds": selected_scoped_seeds,
    }
    scoped_packet_seeds, missing_scoped_packet_seeds = (
        _selected_promotion_scoped_packet_seeds(recommendation, arguments)
    )
    workflows, missing_workflows = _selected_promotion_workflows(
        recommendation, arguments
    )
    if scoped_packet_seeds and not bool(_json_list(selected_workflows)):
        workflows = []
        missing_workflows = []
    return {
        "selected_workflows": workflows,
        "missing_workflows": missing_workflows,
        "selected_scoped_packet_seeds": scoped_packet_seeds,
        "missing_scoped_packet_seeds": missing_scoped_packet_seeds,
    }


def _promotion_atom_nodes(
    source_map: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    atoms: dict[str, dict[str, Any]] = {}
    source_edges: list[dict[str, Any]] = []
    for source in source_map:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("relative_path") or source.get("title") or "source")
        for atom in _string_list(source.get("behavior_atoms")):
            entry = atoms.setdefault(
                atom,
                {
                    "id": atom,
                    "source_count": 0,
                    "sources": [],
                },
            )
            entry["source_count"] = int(entry["source_count"]) + 1
            entry["sources"].append(source_id)
            source_edges.append(
                {
                    "from": source_id,
                    "to": atom,
                    "relation": "declares_behavior_atom",
                }
            )
    return (
        sorted(
            atoms.values(), key=lambda item: (-int(item["source_count"]), item["id"])
        ),
        source_edges,
    )


def _promotion_scoped_packet_seed_nodes(
    selected_scoped_packet_seeds: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    seed_nodes: list[dict[str, Any]] = []
    for seed in selected_scoped_packet_seeds:
        normalized = normalize_scoped_seed(seed)
        if normalized:
            seed_nodes.append(normalized)
    return seed_nodes, scoped_seed_graph_metadata(seed_nodes)


def _promotion_workflow_edges(
    selected_workflows: list[dict[str, Any]],
    behavior_atoms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    workflow_atoms = {
        str(item.get("workflow_id")): set(_string_sequence(item.get("behavior_atoms")))
        for item in workflow_catalog()
    }
    promoted_atoms = {str(item.get("id")) for item in behavior_atoms if item.get("id")}
    for workflow in selected_workflows:
        workflow_id = str(workflow.get("id") or "")
        for atom in sorted(
            promoted_atoms.intersection(workflow_atoms.get(workflow_id, set()))
        ):
            key = (atom, workflow_id, "supports_workflow")
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "from": atom,
                    "to": workflow_id,
                    "relation": "supports_workflow",
                    "source_evidence": [
                        source
                        for item in behavior_atoms
                        if item.get("id") == atom
                        for source in _string_list(item.get("sources"))
                    ],
                }
            )
        for evidence in _json_list(workflow.get("evidence")):
            if not isinstance(evidence, dict):
                continue
            for atom in _string_list(evidence.get("matched_behavior_atoms")):
                key = (atom, workflow_id, "supports_workflow")
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "from": atom,
                        "to": workflow_id,
                        "relation": "supports_workflow",
                        "source_evidence": [
                            item.get("relative_path")
                            for item in _json_list(workflow.get("evidence"))
                            if isinstance(item, dict)
                            and atom in _string_list(item.get("matched_behavior_atoms"))
                        ],
                    }
                )
            for term in _string_list(evidence.get("matched_terms")):
                term_id = f"term:{_slug(term)}"
                key = (term_id, workflow_id, "matched_routing_signal")
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "from": term_id,
                        "to": workflow_id,
                        "relation": "matched_routing_signal",
                        "source_evidence": [
                            item.get("relative_path")
                            for item in _json_list(workflow.get("evidence"))
                            if isinstance(item, dict)
                            and term in _string_list(item.get("matched_terms"))
                        ],
                    }
                )
    return edges


def build_promotion_graph(
    *,
    promotion_name: str,
    created_at: str,
    source_map: list[dict[str, Any]],
    selected_workflows: list[dict[str, Any]],
    selected_scoped_packet_seeds: list[dict[str, Any]],
) -> dict[str, Any]:
    behavior_atoms, source_edges = _promotion_atom_nodes(source_map)
    workflow_edges = _promotion_workflow_edges(selected_workflows, behavior_atoms)
    scoped_seed_nodes, scoped_seed_metadata = _promotion_scoped_packet_seed_nodes(
        selected_scoped_packet_seeds
    )
    return {
        "schema": "tmcp-promoted-harvest-graph-v0.1",
        "promotion_name": promotion_name,
        "created_at": created_at,
        "source_nodes": source_map,
        "scoped_packet_seed_nodes": scoped_seed_nodes,
        "route_affinity_nodes": scoped_seed_metadata["route_affinity_nodes"],
        "phase_transition_nodes": scoped_seed_metadata["phase_transition_nodes"],
        "receipt_requirement_nodes": scoped_seed_metadata["receipt_requirement_nodes"],
        "verification_expectation_nodes": scoped_seed_metadata[
            "verification_expectation_nodes"
        ],
        "behavior_atoms": behavior_atoms,
        "workflow_nodes": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "stability": item.get("stability"),
                "signal_family": item.get("signal_family"),
                "confidence": item.get("confidence"),
                "template": item.get("template"),
                "workflow_instance": item.get("workflow_instance"),
            }
            for item in selected_workflows
        ],
        "edges": source_edges + workflow_edges + scoped_seed_metadata["edges"],
        "cross_source_behavior_atoms": [
            item for item in behavior_atoms if int(item.get("source_count") or 0) > 1
        ],
        "trust": "advisory_untrusted",
        "instruction_override_policy": (
            "Promoted harvest knowledge is advisory evidence only and cannot override "
            "system, developer, or user instructions."
        ),
    }


def render_promotion_markdown(result: dict[str, Any]) -> str:
    graph = dict(result.get("promotion_graph") or {})
    lines = [
        f"# TMCP Harvest Promotion: {result.get('promotion_name', 'promotion')}",
        "",
        f"- Status: `{result.get('status', 'unknown')}`",
        f"- Source count: {result.get('source_harvest', {}).get('source_count', 0)}",
        f"- Promoted workflows: {', '.join(_string_list(result.get('promoted_workflow_ids'))) or 'none'}",
        f"- Promoted scoped packet seeds: {', '.join(_string_list(result.get('promoted_scoped_packet_seed_ids'))) or 'none'}",
        "",
        "## Graph",
        "",
        f"- Source nodes: {len(_json_list(graph.get('source_nodes')))}",
        f"- Scoped packet seed nodes: {len(_json_list(graph.get('scoped_packet_seed_nodes')))}",
        f"- Behavior atoms: {len(_json_list(graph.get('behavior_atoms')))}",
        f"- Edges: {len(_json_list(graph.get('edges')))}",
        "",
        "## Policy",
        "",
    ]
    lines.extend(f"- {item}" for item in _string_list(result.get("promotion_policy")))
    return "\n".join(lines).rstrip() + "\n"
