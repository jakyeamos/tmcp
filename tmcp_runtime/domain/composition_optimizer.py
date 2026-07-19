"""Conservative deterministic optimization for validated semantic skill graphs."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from collections import deque
import re
from typing import Any

from .composition_declared_dependencies import (
    declared_dependency_closure_is_well_formed,
    required_closure_source_ids,
)
from .composition_preflight import json_list, ordered_unique, string_list
from .composition_validation import ordering_pair


_TASK_STOPWORDS = frozenset(
    {"and", "the", "with", "from", "into", "that", "this", "result"}
)


def _role_cost(role: Mapping[str, Any]) -> int:
    value = role.get("context_cost")
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _source_context_costs(preflight: Mapping[str, Any]) -> dict[str, int]:
    """Derive context cost from cited harvested slices, never host estimates."""

    costs: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for item in json_list(preflight.get("candidate_source_slices")):
        if not isinstance(item, Mapping):
            continue
        node_id = str(item.get("source_node_id") or "")
        slice_id = str(item.get("slice_id") or "")
        if not node_id or not slice_id or (node_id, slice_id) in seen:
            continue
        seen.add((node_id, slice_id))
        try:
            token_cost = max(1, int(item.get("token_estimate") or 1))
        except (TypeError, ValueError, OverflowError):
            token_cost = 1
        costs[node_id] = costs.get(node_id, 0) + token_cost
    return costs


def _set(role: Mapping[str, Any], field: str) -> set[str]:
    return set(string_list(role.get(field)))


def _strictly_dominates(
    keeper: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> bool:
    if str(keeper.get("node_id")) == str(candidate.get("node_id")):
        return False
    if _set(keeper, "phase_affinity") != _set(candidate, "phase_affinity"):
        return False
    if _set(keeper, "inputs") != _set(candidate, "inputs"):
        return False
    for field in ("outputs", "covers", "entry_gates", "exit_gates"):
        if not _set(candidate, field).issubset(_set(keeper, field)):
            return False
    keeper_cost = _role_cost(keeper)
    candidate_cost = _role_cost(candidate)
    if keeper_cost > candidate_cost:
        return False
    return keeper_cost < candidate_cost or str(keeper.get("node_id")) < str(
        candidate.get("node_id")
    )


def _only_complements_keeper(
    candidate_id: str,
    keeper_id: str,
    edges: list[dict[str, Any]],
) -> bool:
    incident = [
        edge
        for edge in edges
        if candidate_id in {str(edge.get("from")), str(edge.get("to"))}
    ]
    if not incident:
        return False
    return all(
        edge.get("type") == "complements"
        and keeper_id in {str(edge.get("from")), str(edge.get("to"))}
        for edge in incident
    )


def _mandatory_node_ids(preflight: Mapping[str, Any]) -> set[str]:
    mandatory = {
        str(item.get("source_node_id") or "")
        for item in json_list(preflight.get("candidate_source_slices"))
        if isinstance(item, Mapping)
        and (
            item.get("mandatory") is True
            or item.get("source_role") == "governing_instruction"
        )
    }
    hints = preflight.get("scoped_seed_graph_hints")
    raw_closure = (
        hints.get("declared_dependency_closure")
        if isinstance(hints, Mapping)
        else None
    )
    closure = raw_closure if declared_dependency_closure_is_well_formed(raw_closure) else {}
    return mandatory.union(required_closure_source_ids(closure))


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", str(value).lower())
        if token not in _TASK_STOPWORDS
    }


def _role_terms(role: Mapping[str, Any]) -> set[str]:
    return _tokens(
        " ".join(
            [
                str(role.get("role") or ""),
                *string_list(role.get("outputs")),
                *string_list(role.get("covers")),
                *string_list(role.get("exit_gates")),
            ]
        )
    )


def _best_role_for_target(
    target: str,
    roles: list[dict[str, Any]],
) -> str:
    target_terms = _tokens(target)
    ranked = sorted(
        (
            (
                -len(target_terms.intersection(_role_terms(role))),
                _role_cost(role),
                str(role.get("node_id") or ""),
            )
            for role in roles
        )
    )
    if not ranked or ranked[0][0] == 0:
        return ""
    return ranked[0][2]


def _dependency_predecessors(edges: list[dict[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for edge in edges:
        pair = ordering_pair(edge)
        if pair is not None:
            result.setdefault(pair[1], set()).add(pair[0])
    return result


def _adjacency(edges: list[dict[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for edge in edges:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        result.setdefault(source, set()).add(target)
        result.setdefault(target, set()).add(source)
    return result


def _shortest_path(
    adjacency: Mapping[str, set[str]],
    starts: set[str],
    target: str,
) -> list[str]:
    pending: deque[tuple[str, list[str]]] = deque(
        (start, [start]) for start in sorted(starts)
    )
    visited = set(starts)
    while pending:
        node_id, path = pending.popleft()
        if node_id == target:
            return path
        for neighbor in sorted(adjacency.get(node_id, set())):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            pending.append((neighbor, [*path, neighbor]))
    return []


def optimize_semantic_subgraph(
    normalized_proposal: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Prune only source-backed roles that are strictly dominated complements."""

    optimized = deepcopy(dict(normalized_proposal))
    roles = [
        dict(item)
        for item in json_list(optimized.get("skill_roles"))
        if isinstance(item, Mapping)
    ]
    host_context_costs = {
        str(role.get("node_id") or ""): _role_cost(role) for role in roles
    }
    source_context_costs = _source_context_costs(preflight)
    for role in roles:
        node_id = str(role.get("node_id") or "")
        role["context_cost"] = source_context_costs.get(node_id, 1)
    edges = [
        dict(item)
        for item in json_list(optimized.get("relationships"))
        if isinstance(item, Mapping)
    ]
    mandatory = _mandatory_node_ids(preflight)
    rejected: list[dict[str, str]] = []
    rejected_ids: set[str] = set()
    ordered_roles = sorted(
        roles,
        key=lambda role: (_role_cost(role), str(role.get("node_id") or "")),
    )
    for candidate in reversed(ordered_roles):
        candidate_id = str(candidate.get("node_id") or "")
        if candidate_id in mandatory or candidate_id in rejected_ids:
            continue
        for keeper in ordered_roles:
            keeper_id = str(keeper.get("node_id") or "")
            if keeper_id in rejected_ids:
                continue
            if not _strictly_dominates(keeper, candidate):
                continue
            if not _only_complements_keeper(candidate_id, keeper_id, edges):
                continue
            rejected_ids.add(candidate_id)
            rejected.append(
                {
                    "node_id": candidate_id,
                    "reason": "strictly_dominated_redundant_complement",
                    "dominated_by": keeper_id,
                }
            )
            break

    available_roles = [
        role for role in roles if str(role.get("node_id")) not in rejected_ids
    ]
    available_ids = {str(role.get("node_id")) for role in available_roles}
    available_edges = [
        edge
        for edge in edges
        if str(edge.get("from")) in available_ids
        and str(edge.get("to")) in available_ids
    ]
    task_model = optimized.get("task_model")
    task = task_model if isinstance(task_model, Mapping) else {}
    coverage = optimized.get("coverage")
    coverage_map = coverage if isinstance(coverage, Mapping) else {}
    task_targets = ordered_unique(
        string_list(task.get("deliverables"))
        + string_list(task.get("success_criteria"))
        + string_list(task.get("subgoals"))
        + string_list(task.get("evidence_needs"))
        + string_list(coverage_map.get("facets"))
    )
    selected_ids = set(mandatory).intersection(available_ids)
    for target in task_targets:
        selected_id = _best_role_for_target(target, available_roles)
        if selected_id:
            selected_ids.add(selected_id)
    selected_ids.update(
        str(edge.get("from") or "")
        for edge in available_edges
        if edge.get("type") == "verifies"
    )
    selected_semantics = {
        value
        for role in available_roles
        if str(role.get("node_id") or "") in selected_ids
        for field in ("outputs", "covers")
        for value in string_list(role.get(field))
    }
    roles_by_id = {str(role.get("node_id") or ""): role for role in available_roles}
    for edge in available_edges:
        if edge.get("type") != "complements":
            continue
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if (source in selected_ids) == (target in selected_ids):
            continue
        complement = target if source in selected_ids else source
        complement_role = roles_by_id.get(complement, {})
        complement_semantics = {
            value
            for field in ("outputs", "covers")
            for value in string_list(complement_role.get(field))
        }
        if complement_semantics.difference(selected_semantics):
            selected_ids.add(complement)
            selected_semantics.update(complement_semantics)
    nonmandatory_selected = selected_ids.difference(mandatory)
    if not nonmandatory_selected:
        selected_ids = set(available_ids)

    predecessors = _dependency_predecessors(available_edges)
    pending = list(selected_ids)
    while pending:
        node_id = pending.pop()
        for predecessor in sorted(predecessors.get(node_id, set())):
            if predecessor not in selected_ids:
                selected_ids.add(predecessor)
                pending.append(predecessor)

    roots = set(mandatory).intersection(available_ids) or available_ids.difference(
        predecessors
    )
    if not roots:
        roots = {min(available_ids)} if available_ids else set()
    adjacency = _adjacency(available_edges)
    for node_id in sorted(selected_ids):
        selected_ids.update(_shortest_path(adjacency, roots, node_id))

    for role in available_roles:
        node_id = str(role.get("node_id") or "")
        if node_id in selected_ids:
            continue
        rejected_ids.add(node_id)
        rejected.append(
            {
                "node_id": node_id,
                "reason": "lower_utility_context_candidate",
                "dominated_by": "task_coverage_and_dependency_closure",
            }
        )

    selected_roles = [
        role for role in roles if str(role.get("node_id")) in selected_ids
    ]
    selected_ids = {str(role.get("node_id")) for role in selected_roles}
    selected_edges = [
        edge
        for edge in edges
        if str(edge.get("from")) in selected_ids and str(edge.get("to")) in selected_ids
    ]
    optimized["skill_roles"] = selected_roles
    optimized["relationships"] = selected_edges

    criteria = string_list(task.get("success_criteria"))
    covered = ordered_unique(
        [facet for role in selected_roles for facet in string_list(role.get("covers"))]
    )
    candidate_cost = sum(_role_cost(role) for role in roles)
    selected_cost = sum(_role_cost(role) for role in selected_roles)
    context_ratio = round(selected_cost / candidate_cost, 4) if candidate_cost else 0.0
    dependency_edges = [edge for edge in selected_edges if ordering_pair(edge)]
    verification_edges = [
        edge for edge in selected_edges if edge.get("type") == "verifies"
    ]
    complement_edges = [
        edge for edge in selected_edges if edge.get("type") == "complements"
    ]
    diagnostics = {
        "policy": "coverage_dependency_cost_v0.1",
        "candidate_node_ids": [str(role.get("node_id")) for role in roles],
        "selected_node_ids": [str(role.get("node_id")) for role in selected_roles],
        "rejected_nodes": rejected,
        "mandatory_node_ids": sorted(mandatory),
        "candidate_context_cost": candidate_cost,
        "selected_context_cost": selected_cost,
        "host_context_costs_ignored": host_context_costs,
        "source_context_costs": source_context_costs,
        "context_ratio": context_ratio,
        "context_budget_warning": context_ratio > 0.75,
        "covered_criteria": [
            criterion for criterion in criteria if criterion in covered
        ],
        "uncovered_criteria": [
            criterion for criterion in criteria if criterion not in covered
        ],
        "dependency_edge_count": len(dependency_edges),
        "verification_edge_count": len(verification_edges),
        "complementarity_edge_count": len(complement_edges),
        "required_dependency_closure_preserved": all(
            predecessor in selected_ids
            for successor in selected_ids
            for predecessor in predecessors.get(successor, set())
        ),
        "selection_score": round(
            len(set(criteria).intersection(covered)) * 10
            + len(verification_edges) * 3
            + len(complement_edges) * 2
            - selected_cost / 1000
            - len(rejected),
            4,
        ),
    }
    return optimized, diagnostics
