"""Deterministic harvest ranking for bounded composition evidence."""

from __future__ import annotations

from typing import Any

from .composition import composition_evidence_terms
from .composition_declared_dependencies import (
    declared_dependency_closure,
    required_closure_source_ids,
    required_dependency_source_ids,
)
from .composition_seed_roots import (
    declared_seed_phrase_matches_objective,
    seed_root_terms,
)
from .harvest_node_policy import is_evidence_only_path
from .harvest_nodes import node_harvest_sort_key, node_signal_text, node_source_role


Node = dict[str, Any]


def composition_candidate_sort_key(
    candidate: Any,
    objective_terms: set[str],
    *,
    explicitly_scoped: bool = False,
) -> tuple[int, int, str]:
    """Prioritize governing and active sources before bounded candidate reads."""

    relative_path = str(candidate.relative_path).lower()
    name = candidate.logical_path.name.lower()
    if name in {"agents.md", "claude.md", ".cursorrules"}:
        role_rank = 0
    elif explicitly_scoped:
        # Caller-selected paths must survive discovery limits, but governing
        # instructions still take precedence over any lower-authority source.
        role_rank = 1
    elif (
        is_evidence_only_path(relative_path)
        and candidate.root.kind != "file"
        and not is_evidence_only_path(str(candidate.root.logical_path))
    ):
        role_rank = 3
    elif name in {"skill.md", "scoped-packet-seeds.json"}:
        role_rank = 2
    else:
        role_rank = 3
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


def _seed_objective_terms(node: Node, objective_terms: set[str]) -> set[str]:
    """Match seed roots only against harvested content, never a path label."""

    content = str(node.get("excerpt") or node.get("signal_excerpt") or "")
    content_terms = seed_root_terms(content)
    return objective_terms.intersection(content_terms)


def _seed_root_objective_terms(value: str) -> set[str]:
    return seed_root_terms(value)


def composition_result_order_with_requirements(
    nodes: list[Node],
    objective_terms: set[str],
    *,
    include_all_active_source_slices: bool,
    seed_root_objective: str | None = None,
) -> tuple[list[Node], set[str]]:
    """Retain distinct active behavior while reserving bounded evidence capacity.

    Candidate reads are authority-first so supporting prose cannot starve skill
    discovery under the byte budget. Default results retain governing sources,
    explicitly scoped or discriminative active skills, one non-seed active
    fallback, then every remaining active candidate before supporting evidence.
    Explicit all-active mode keeps every harvested active source ahead of
    supporting reads.
    """

    ordered = sorted(nodes, key=lambda node: _node_sort_key(node, objective_terms))
    governing_source_ids = {
        str(node.get("id") or "")
        for node in ordered
        if node_source_role(node) == "governing_instruction"
        and str(node.get("id") or "")
    }
    explicitly_scoped_source_ids = {
        str(node.get("id") or "")
        for node in ordered
        if node.get("explicitly_scoped") is True and str(node.get("id") or "")
    }
    if include_all_active_source_slices:
        required_source_ids = governing_source_ids.union(
            explicitly_scoped_source_ids,
            {
                str(node.get("id") or "")
                for node in ordered
                if node_source_role(node) == "active_skill"
                and str(node.get("id") or "")
            },
        )
        return ordered, required_source_ids
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
    protected_non_seed_active = [
        node
        for node in active
        if node.get("source_type") != "scoped_packet_seed"
        and (
            node.get("explicitly_scoped") is True
            or bool(matched_active_terms[id(node)].intersection(discriminative_terms))
        )
    ]
    active_seed_nodes = [
        node
        for node in active
        if node.get("source_type") == "scoped_packet_seed"
    ]
    seed_objective_terms = _seed_root_objective_terms(
        seed_root_objective or " ".join(sorted(objective_terms))
    )
    matched_seed_terms = {
        id(node): _seed_objective_terms(node, seed_objective_terms)
        for node in active_seed_nodes
    }
    seed_term_counts: dict[str, int] = {}
    for terms in matched_seed_terms.values():
        for term in terms:
            seed_term_counts[term] = seed_term_counts.get(term, 0) + 1
    discriminative_seed_terms = {
        term for term, count in seed_term_counts.items() if count == 1
    }
    root_seed_ids = {
        str(node.get("id") or "")
        for node in active_seed_nodes
        if node.get("explicitly_scoped") is True
        or bool(matched_seed_terms[id(node)].intersection(discriminative_seed_terms))
        or declared_seed_phrase_matches_objective(
            node,
            seed_root_objective or " ".join(sorted(objective_terms)),
        )
    }
    root_seed_counts = {
        seed_id: sum(
            str(node.get("id") or "") == seed_id for node in active_seed_nodes
        )
        for seed_id in root_seed_ids
    }
    ambiguous_root_seed_ids = sorted(
        seed_id for seed_id, count in root_seed_counts.items() if count != 1
    )
    if ambiguous_root_seed_ids:
        raise ValueError(
            "Composition declared dependency closure requires unique scoped seed ids: "
            + ", ".join(ambiguous_root_seed_ids)
        )
    dependency_closure = declared_dependency_closure(
        nodes,
        root_seed_ids=sorted(root_seed_ids),
        require_complete_seed_metadata=True,
    )
    dependency_source_ids = required_dependency_source_ids(dependency_closure)
    required_source_ids = governing_source_ids.union(
        explicitly_scoped_source_ids,
        required_closure_source_ids(dependency_closure),
    )
    root_seed_nodes = [
        node
        for node in active_seed_nodes
        if str(node.get("id") or "") in root_seed_ids
    ]
    required_dependencies = [
        node
        for node in active
        if str(node.get("id") or "") in dependency_source_ids
    ]
    protected_active = protected_non_seed_active + root_seed_nodes
    protected_active_ids = {id(node) for node in protected_active}
    fallback_candidates = [
        node
        for node in active
        if node.get("source_type") != "scoped_packet_seed"
        or str(node.get("id") or "") in root_seed_ids
    ]
    fallback_active = [] if protected_active or not fallback_candidates else [
        fallback_candidates[0]
    ]
    retained_active_ids = {
        id(node)
        for node in protected_active + required_dependencies + fallback_active
    }
    supporting = by_role["supporting_reference"]
    relevant_supporting = [
        node for node in supporting if _objective_terms(node, objective_terms)
    ]
    retained_supporting_ids = {id(node) for node in relevant_supporting}
    return (
        by_role["governing_instruction"]
        + root_seed_nodes
        + [
            node
            for node in required_dependencies
            if id(node) not in protected_active_ids
        ]
        + [
            node
            for node in protected_non_seed_active
            if id(node) not in {id(root) for root in root_seed_nodes}
        ]
        + fallback_active
        + [node for node in active if id(node) not in retained_active_ids]
        + relevant_supporting
        + [node for node in supporting if id(node) not in retained_supporting_ids]
        + by_role["evidence_only"]
    ), required_source_ids


def composition_result_order(
    nodes: list[Node],
    objective_terms: set[str],
    *,
    include_all_active_source_slices: bool,
    seed_root_objective: str | None = None,
) -> list[Node]:
    """Return composition-ranked nodes without exposing reservation metadata."""

    ordered, _required = composition_result_order_with_requirements(
        nodes,
        objective_terms,
        include_all_active_source_slices=include_all_active_source_slices,
        seed_root_objective=seed_root_objective,
    )
    return ordered
