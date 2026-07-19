"""Deterministic harvest ranking for bounded composition evidence."""

from __future__ import annotations

from typing import Any

from .composition import composition_evidence_terms
from .harvest_node_policy import is_evidence_only_path
from .harvest_nodes import node_harvest_sort_key, node_signal_text, node_source_role


Node = dict[str, Any]


def composition_candidate_sort_key(
    candidate: Any,
    objective_terms: set[str],
) -> tuple[int, int, str]:
    """Prioritize governing and active sources before bounded candidate reads."""

    relative_path = str(candidate.relative_path).lower()
    name = candidate.logical_path.name.lower()
    if name in {"agents.md", "claude.md", ".cursorrules"}:
        role_rank = 0
    elif (
        is_evidence_only_path(relative_path)
        and candidate.root.kind != "file"
        and not is_evidence_only_path(str(candidate.root.logical_path))
    ):
        role_rank = 3
    elif name in {"skill.md", "scoped-packet-seeds.json"}:
        role_rank = 1
    else:
        role_rank = 2
    relevance = len(
        objective_terms.intersection(composition_evidence_terms(relative_path))
    )
    return role_rank, -relevance, relative_path


def _node_sort_key(
    node: Node,
    objective_terms: set[str],
) -> tuple[int, int, tuple[Any, ...]]:
    role_rank = {
        "governing_instruction": 0,
        "active_skill": 1,
        "supporting_reference": 2,
        "evidence_only": 3,
    }.get(node_source_role(node), 3)
    relevance = len(_objective_terms(node, objective_terms))
    return role_rank, -relevance, node_harvest_sort_key(node)


def _objective_terms(node: Node, objective_terms: set[str]) -> set[str]:
    return objective_terms.intersection(
        composition_evidence_terms(node_signal_text(node))
    )


def composition_result_order(
    nodes: list[Node],
    objective_terms: set[str],
    *,
    include_all_active_source_slices: bool,
) -> list[Node]:
    """Retain distinct active behavior while reserving bounded evidence capacity.

    Candidate reads are authority-first so supporting prose cannot starve skill
    discovery under the byte budget. Default results retain governing sources,
    scoped or discriminative active skills, one active fallback, and relevant
    supporting evidence. Explicit all-active mode keeps every harvested active
    source ahead of supporting reads.
    """

    ordered = sorted(nodes, key=lambda node: _node_sort_key(node, objective_terms))
    if include_all_active_source_slices:
        return ordered
    by_role = {
        role: [node for node in ordered if node_source_role(node) == role]
        for role in (
            "governing_instruction",
            "active_skill",
            "supporting_reference",
            "evidence_only",
        )
    }
    active = by_role["active_skill"]
    matched_active_terms = {
        id(node): _objective_terms(node, objective_terms) for node in active
    }
    active_term_counts: dict[str, int] = {}
    for terms in matched_active_terms.values():
        for term in terms:
            active_term_counts[term] = active_term_counts.get(term, 0) + 1
    discriminative_terms = {
        term for term, count in active_term_counts.items() if count == 1
    }
    protected_active = [
        node
        for node in active
        if node.get("explicitly_scoped") is True
        or node.get("source_type") == "scoped_packet_seed"
        or bool(matched_active_terms[id(node)].intersection(discriminative_terms))
    ]
    fallback_active = [] if protected_active or not active else [active[0]]
    retained_active_ids = {id(node) for node in protected_active + fallback_active}
    supporting = by_role["supporting_reference"]
    relevant_supporting = [
        node for node in supporting if _objective_terms(node, objective_terms)
    ]
    retained_supporting_ids = {id(node) for node in relevant_supporting}
    return (
        by_role["governing_instruction"]
        + protected_active
        + fallback_active
        + relevant_supporting
        + [node for node in active if id(node) not in retained_active_ids]
        + [node for node in supporting if id(node) not in retained_supporting_ids]
        + by_role["evidence_only"]
    )
