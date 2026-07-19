"""Deterministic scoped-seed root selection for composition preflight."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .composition import (
    COMPOSITION_GENERIC_TERMS,
    COMPOSITION_LOW_SIGNAL_TERMS,
    COMPOSITION_SHORT_SIGNAL_TERMS,
)
from .composition_declared_dependencies import (
    declared_dependency_closure,
    node_is_explicitly_scoped,
    required_closure_source_ids,
)
from .harvest_nodes import node_source_role


def seed_root_terms(value: object) -> set[str]:
    """Keep task facets while excluding generic composition boilerplate."""

    return {
        term
        for term in re.findall(r"[a-z0-9]+", str(value).lower())
        if len(term) >= 3 or term in COMPOSITION_SHORT_SIGNAL_TERMS
    }.difference(COMPOSITION_GENERIC_TERMS | COMPOSITION_LOW_SIGNAL_TERMS)


def _normalized_phrase(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))


def declared_seed_phrase_matches_objective(
    node: Mapping[str, Any],
    objective: str,
) -> bool:
    objective_phrase = _normalized_phrase(objective)
    if not objective_phrase:
        return False
    return any(
        len(phrase.split()) >= 2
        and phrase in objective_phrase
        for field in ("use_when", "objective_patterns")
        for value in (node.get(field) if isinstance(node.get(field), list) else [])
        if (phrase := _normalized_phrase(value))
    )


def select_scoped_seed_closure(
    source_nodes: Sequence[Mapping[str, Any]],
    *,
    citable_source_ids: set[str],
    explicitly_scoped_source_ids: set[str],
    seed_objective_terms_by_source: Mapping[str, set[str]],
    objective: str,
    explicitly_scoped_paths: Sequence[str],
    include_all_active_source_slices: bool,
) -> dict[str, Any]:
    """Choose only task-rooted seed bundles and close their dependencies.

    Default composition treats a scoped seed as active only when an exact
    caller scope or a discriminative, source-backed task facet chooses it as a
    root. Its resolved dependencies are required; every other seed stays
    deferred. This prevents a shared word such as ``evidence`` from activating
    unrelated workflow bundles.
    """

    explicit_paths = tuple(explicitly_scoped_paths)

    def is_active_skill(node: Mapping[str, Any]) -> bool:
        return node_source_role(
            dict(node),
            explicitly_scoped=node_is_explicitly_scoped(node, explicit_paths),
        ) == "active_skill"

    citable_active_seed_nodes = [
        node
        for node in source_nodes
        if str(node.get("id") or "") in citable_source_ids
        and str(node.get("source_type") or "") == "scoped_packet_seed"
        and is_active_skill(node)
    ]
    citable_active_seed_ids = {
        str(node.get("id") or "") for node in citable_active_seed_nodes
    }
    seed_term_counts: dict[str, int] = {}
    for source_node_id in citable_active_seed_ids:
        for term in seed_objective_terms_by_source.get(source_node_id, set()):
            seed_term_counts[term] = seed_term_counts.get(term, 0) + 1
    discriminative_seed_root_terms = {
        term for term, count in seed_term_counts.items() if count == 1
    }
    content_root_seed_ids = {
        source_node_id
        for source_node_id, terms in seed_objective_terms_by_source.items()
        if source_node_id in citable_active_seed_ids
        and bool(terms.intersection(discriminative_seed_root_terms))
    }
    declared_phrase_root_seed_ids = {
        str(node.get("id") or "")
        for node in citable_active_seed_nodes
        if declared_seed_phrase_matches_objective(node, objective)
    }
    if include_all_active_source_slices:
        seed_root_ids = sorted(citable_active_seed_ids)
    else:
        seed_root_ids = sorted(
            citable_active_seed_ids.intersection(
                explicitly_scoped_source_ids.union(content_root_seed_ids)
                .union(declared_phrase_root_seed_ids)
            )
        )
    root_seed_counts = {
        seed_id: sum(
            str(node.get("id") or "") == seed_id
            for node in citable_active_seed_nodes
        )
        for seed_id in seed_root_ids
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
        source_nodes,
        root_seed_ids=seed_root_ids,
        explicitly_scoped_paths=explicit_paths,
        require_complete_seed_metadata=True,
    )
    required_closure_ids = required_closure_source_ids(dependency_closure)
    uncitable_closure_ids = sorted(required_closure_ids.difference(citable_source_ids))
    if uncitable_closure_ids:
        raise ValueError(
            "Composition declared dependency closure requires citable source slices: "
            + ", ".join(uncitable_closure_ids)
        )
    deferred_nonroot_scoped_seed_ids = (
        set()
        if include_all_active_source_slices
        else citable_active_seed_ids.difference(required_closure_ids)
    )
    return {
        "dependency_closure": dependency_closure,
        "required_closure_source_ids": required_closure_ids,
        "deferred_nonroot_scoped_seed_ids": deferred_nonroot_scoped_seed_ids,
        "discriminative_seed_root_terms": discriminative_seed_root_terms,
        "declared_phrase_root_seed_ids": declared_phrase_root_seed_ids,
    }
