"""Derive compiled scoped-seed graph data from compact host contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .scoped_seeds import scoped_seed_graph_metadata


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [str(item).strip() for item in _json_list(value) if str(item).strip()]


def selected_scoped_seed_graph(
    hints: Mapping[str, Any],
    *,
    selected_seed_ids: set[str],
    selected_dependency_closure: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild selected derived seed graph without reloading host metadata."""

    seed_contracts = [
        dict(seed)
        for seed in _json_list(hints.get("scoped_seeds"))
        if isinstance(seed, Mapping)
        and str(seed.get("id") or "") in selected_seed_ids
    ]
    graph = scoped_seed_graph_metadata(seed_contracts)
    citations_by_seed = {
        str(seed.get("id") or ""): _strings(seed.get("citations"))
        for seed in seed_contracts
    }
    owner_by_node = {
        str(node.get("id") or ""): str(node.get("seed_id") or "")
        for field in (
            "phase_transition_nodes",
            "receipt_requirement_nodes",
            "verification_expectation_nodes",
        )
        for node in _json_list(graph.get(field))
        if isinstance(node, Mapping)
    }
    typed_edges: list[dict[str, Any]] = []
    for edge in _json_list(graph.get("edges")):
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        owner = (
            source
            if source in citations_by_seed
            else target
            if target in citations_by_seed
            else owner_by_node.get(source) or owner_by_node.get(target) or ""
        )
        citations = citations_by_seed.get(owner, [])
        if citations:
            typed_edges.append({**dict(edge), "citations": citations})
    return {
        "scoped_seeds": seed_contracts,
        "route_affinity_nodes": list(graph["route_affinity_nodes"]),
        "phase_transition_nodes": list(graph["phase_transition_nodes"]),
        "receipt_requirement_nodes": list(graph["receipt_requirement_nodes"]),
        "verification_expectation_nodes": list(
            graph["verification_expectation_nodes"]
        ),
        "typed_edges": typed_edges,
        "declared_dependency_closure": dict(selected_dependency_closure),
    }
