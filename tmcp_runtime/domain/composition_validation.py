"""Deterministic validation for host-proposed semantic composition."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .composition_preflight import (
    ACTIVE_SOURCE_ROLES,
    ALLOWED_RELATIONSHIPS,
    COMPOSITION_TRUST,
    INSTRUCTION_OVERRIDE_POLICY,
    RELATIONSHIP_TYPE_SEMANTICS,
    SEMANTIC_PROPOSAL_SCHEMA,
    json_list,
    normalized_text,
    string_list,
)


OVERRIDE_HAZARD_PHRASES = (
    "ignore previous instructions",
    "ignore system instructions",
    "ignore developer instructions",
    "ignore user instructions",
    "override system instructions",
    "override developer instructions",
    "override user instructions",
    "supersede governing instructions",
    "bypass higher-priority instructions",
)


class SemanticProposalValidationError(ValueError):
    """Raised when a host semantic proposal fails deterministic validation."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__("Semantic proposal failed deterministic validation.")


def _error(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return max(0, int(value or 0))
    except (OverflowError, ValueError):
        return 0


def _normalized_role(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": str(value.get("node_id") or "").strip(),
        "role": str(value.get("role") or "").strip(),
        "inputs": string_list(value.get("inputs")),
        "outputs": string_list(value.get("outputs")),
        "phase_affinity": string_list(value.get("phase_affinity")),
        "entry_gates": string_list(value.get("entry_gates")),
        "exit_gates": string_list(value.get("exit_gates")),
        "context_cost": _nonnegative_int(value.get("context_cost")),
        "covers": string_list(value.get("covers")),
        "citations": string_list(value.get("citations")),
    }


def _normalized_edge(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "from": str(value.get("from") or "").strip(),
        "to": str(value.get("to") or "").strip(),
        "type": str(value.get("type") or "").strip(),
        "citations": string_list(value.get("citations")),
        "rationale": normalized_text(value.get("rationale")),
    }


def ordering_pair(edge: dict[str, Any]) -> tuple[str, str] | None:
    """Resolve one typed relationship to its prerequisite ordering direction."""

    relation = str(edge.get("type") or "")
    source = str(edge.get("from") or "")
    target = str(edge.get("to") or "")
    ordering = RELATIONSHIP_TYPE_SEMANTICS.get(relation, {}).get("ordering")
    if ordering == "to_before_from":
        return target, source
    if ordering == "from_before_to":
        return source, target
    return None


def _topological_levels(
    node_ids: list[str], edges: list[dict[str, Any]]
) -> tuple[list[list[str]], list[str]]:
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        pair = ordering_pair(edge)
        if (
            pair is None
            or pair[0] not in indegree
            or pair[1] not in indegree
            or pair[1] in outgoing[pair[0]]
        ):
            continue
        outgoing[pair[0]].add(pair[1])
        indegree[pair[1]] += 1
    levels: list[list[str]] = []
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    visited: list[str] = []
    while ready:
        level = ready
        levels.append(level)
        visited.extend(level)
        next_ready: list[str] = []
        for source in level:
            for target in sorted(outgoing[source]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    next_ready.append(target)
        ready = sorted(next_ready)
    return levels, sorted(set(node_ids).difference(visited))


def _hazardous_text(proposal: dict[str, Any]) -> bool:
    text = normalized_text(proposal).lower()
    return any(phrase in text for phrase in OVERRIDE_HAZARD_PHRASES)


def _validate_role(
    role: dict[str, Any],
    index: int,
    nodes_by_id: dict[str, dict[str, Any]],
    slices_by_id: dict[str, dict[str, Any]],
    roles_by_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    node_id = str(role["node_id"])
    path = f"skill_roles[{index}]"
    if not node_id or node_id not in nodes_by_id:
        errors.append(
            _error(
                "unknown_node",
                f"{path}.node_id",
                f"Unknown source node: {node_id or '<empty>'}.",
            )
        )
        return
    if node_id in roles_by_id:
        errors.append(
            _error(
                "duplicate_role",
                f"{path}.node_id",
                f"Duplicate role for {node_id}.",
            )
        )
    source_role = str(nodes_by_id[node_id].get("source_role") or "")
    if source_role not in ACTIVE_SOURCE_ROLES:
        errors.append(
            _error(
                "inactive_source_activation",
                f"{path}.node_id",
                f"{source_role} sources may cite evidence but cannot activate behavior.",
            )
        )
    if not str(role["role"]):
        errors.append(
            _error(
                "missing_role",
                f"{path}.role",
                "Every selected source needs a semantic role.",
            )
        )
    for field, label in (
        ("inputs", "required input"),
        ("outputs", "produced handoff"),
        ("phase_affinity", "phase affinity"),
        ("exit_gates", "exit gate"),
    ):
        if not string_list(role.get(field)):
            errors.append(
                _error(
                    "incomplete_skill_role",
                    f"{path}.{field}",
                    f"Every selected source needs at least one explicit {label}.",
                )
            )
    citations = list(role["citations"])
    if not citations:
        errors.append(
            _error(
                "missing_citations",
                f"{path}.citations",
                "Every skill role requires at least one harvested source slice.",
            )
        )
    for citation in citations:
        if citation not in slices_by_id:
            errors.append(
                _error(
                    "unknown_citation",
                    f"{path}.citations",
                    f"Unknown source slice: {citation}.",
                )
            )
        elif str(slices_by_id[citation].get("source_node_id") or "") != node_id:
            errors.append(
                _error(
                    "unsupported_role_claim",
                    f"{path}.citations",
                    "A role citation must come from the source assigned to that role.",
                )
            )
    roles_by_id[node_id] = role


def _validate_edge(
    edge: dict[str, Any],
    index: int,
    nodes_by_id: dict[str, dict[str, Any]],
    slices_by_id: dict[str, dict[str, Any]],
    roles_by_id: dict[str, dict[str, Any]],
    seen_edges: set[tuple[str, str, str]],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    path = f"relationships[{index}]"
    relation = str(edge["type"])
    source = str(edge["from"])
    target = str(edge["to"])
    if relation not in ALLOWED_RELATIONSHIPS:
        errors.append(
            _error(
                "unsupported_relationship",
                f"{path}.type",
                f"Unsupported relationship: {relation or '<empty>'}.",
            )
        )
    for field, node_id in (("from", source), ("to", target)):
        if node_id not in roles_by_id:
            errors.append(
                _error(
                    "unknown_node",
                    f"{path}.{field}",
                    f"Relationship references an unknown active node: {node_id or '<empty>'}.",
                )
            )
    key = (source, target, relation)
    if key in seen_edges:
        warnings.append(
            _error(
                "duplicate_relationship",
                path,
                f"Duplicate relationship {source} {relation} {target}.",
            )
        )
    seen_edges.add(key)
    if source and source == target:
        errors.append(
            _error(
                "relationship_cycle",
                path,
                "A relationship cannot target its own source node.",
            )
        )
    citations = list(edge["citations"])
    if not citations:
        errors.append(
            _error(
                "missing_citations",
                f"{path}.citations",
                "Every relationship requires harvested source citations.",
            )
        )
    for citation in citations:
        if citation not in slices_by_id:
            errors.append(
                _error(
                    "unknown_citation",
                    f"{path}.citations",
                    f"Unknown source slice: {citation}.",
                )
            )
    cited_node_ids = {
        str(slices_by_id[citation].get("source_node_id") or "")
        for citation in citations
        if citation in slices_by_id
    }
    if citations and not cited_node_ids.intersection({source, target}):
        errors.append(
            _error(
                "unsupported_relationship_claim",
                f"{path}.citations",
                "A relationship citation must come from at least one endpoint source.",
            )
        )
    if source in nodes_by_id and target in nodes_by_id:
        source_role = str(nodes_by_id[source].get("source_role") or "")
        target_role = str(nodes_by_id[target].get("source_role") or "")
        pair = ordering_pair(edge)
        ordering_overrides_governing = bool(
            pair
            and str(nodes_by_id[pair[1]].get("source_role") or "")
            == "governing_instruction"
            and str(nodes_by_id[pair[0]].get("source_role") or "")
            != "governing_instruction"
        )
        conflicts_with_governing = bool(
            relation == "conflicts_with"
            and "governing_instruction" in {source_role, target_role}
            and source_role != target_role
        )
        if ordering_overrides_governing or conflicts_with_governing:
            errors.append(
                _error(
                    "precedence_override_hazard",
                    path,
                    "A lower-priority source cannot precede, enable, or conflict with a governing instruction.",
                )
            )
    if relation == "conflicts_with" and source in roles_by_id and target in roles_by_id:
        shared = sorted(
            set(roles_by_id[source]["phase_affinity"]).intersection(
                roles_by_id[target]["phase_affinity"]
            )
        )
        if shared:
            errors.append(
                _error(
                    "same_phase_conflict",
                    path,
                    f"Conflicting skills share active phases: {', '.join(shared)}.",
                )
            )


def _validate_harvested_conflicts(
    nodes_by_id: dict[str, dict[str, Any]],
    roles_by_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    aliases: dict[str, str] = {}
    for node_id, item in nodes_by_id.items():
        for alias in (
            node_id,
            str(item.get("title") or ""),
            str(item.get("relative_path") or ""),
        ):
            if alias:
                aliases[alias.lower()] = node_id
    for node_id, role in roles_by_id.items():
        for incompatible in string_list(nodes_by_id[node_id].get("incompatibilities")):
            target = aliases.get(incompatible.lower())
            if not target or target not in roles_by_id:
                continue
            shared = sorted(
                set(role["phase_affinity"]).intersection(
                    roles_by_id[target]["phase_affinity"]
                )
            )
            if shared:
                errors.append(
                    _error(
                        "same_phase_conflict",
                        f"skill_roles[{node_id}]",
                        f"Harvested incompatibility with {target} shares phases: {', '.join(shared)}.",
                    )
                )


def _validate_connected(
    edges: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    roles_by_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    if len(roles_by_id) <= 1:
        return
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in roles_by_id}
    incoming: set[str] = set()
    for edge in edges:
        source = str(edge["from"])
        target = str(edge["to"])
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            adjacency[target].add(source)
            pair = ordering_pair(edge)
            incoming.add(pair[1] if pair is not None else target)
    roots = sorted(
        node_id
        for node_id in roles_by_id
        if str(nodes_by_id[node_id].get("source_role")) == "governing_instruction"
    )
    if not roots:
        roots = sorted(set(roles_by_id).difference(incoming))
    pending = list(roots[:1] or sorted(roles_by_id)[:1])
    reachable: set[str] = set()
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        pending.extend(sorted(adjacency[node_id].difference(reachable)))
    for node_id in sorted(set(roles_by_id).difference(reachable)):
        errors.append(
            _error(
                "disconnected_node",
                f"skill_roles[{node_id}]",
                "Every non-root selected skill needs a provenance-backed relationship.",
            )
        )
    for node_id in sorted(set(roles_by_id).difference(roots)):
        if node_id in incoming:
            continue
        errors.append(
            _error(
                "missing_incoming_relationship",
                f"skill_roles[{node_id}]",
                "Every non-governing skill needs an incoming provenance-backed relationship.",
            )
        )


def validate_semantic_proposal(
    proposal: dict[str, Any], preflight: dict[str, Any]
) -> dict[str, Any]:
    """Validate host semantics against harvested evidence and precedence policy."""

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    slices = [
        item
        for item in json_list(preflight.get("candidate_source_slices"))
        if isinstance(item, dict)
    ]
    slices_by_id = {str(item.get("slice_id") or ""): item for item in slices}
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for item in slices:
        nodes_by_id.setdefault(str(item.get("source_node_id") or ""), item)
    if proposal.get("schema") != SEMANTIC_PROPOSAL_SCHEMA:
        errors.append(
            _error("invalid_schema", "schema", f"Expected {SEMANTIC_PROPOSAL_SCHEMA}.")
        )
    if proposal.get("preflight_id") != preflight.get("preflight_id"):
        errors.append(
            _error(
                "preflight_mismatch",
                "preflight_id",
                "Proposal was not derived from this preflight.",
            )
        )
    if _hazardous_text(proposal):
        errors.append(
            _error("precedence_override_hazard", "$", INSTRUCTION_OVERRIDE_POLICY)
        )
    roles = [
        _normalized_role(item)
        for item in json_list(proposal.get("skill_roles"))
        if isinstance(item, dict)
    ]
    if not roles:
        errors.append(
            _error(
                "missing_skill_roles",
                "skill_roles",
                "A semantic composition requires at least one cited source role.",
            )
        )
    roles_by_id: dict[str, dict[str, Any]] = {}
    for index, role in enumerate(roles):
        _validate_role(role, index, nodes_by_id, slices_by_id, roles_by_id, errors)
    mandatory_governing = {
        node_id
        for node_id, item in nodes_by_id.items()
        if item.get("mandatory") is True
        or item.get("source_role") == "governing_instruction"
    }
    for node_id in sorted(mandatory_governing.difference(roles_by_id)):
        errors.append(
            _error(
                "missing_governing_source",
                "skill_roles",
                f"Mandatory governing source {node_id} must be selected first.",
            )
        )
    edges = [
        _normalized_edge(item)
        for item in json_list(proposal.get("relationships"))
        if isinstance(item, dict)
    ]
    seen_edges: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(edges):
        _validate_edge(
            edge,
            index,
            nodes_by_id,
            slices_by_id,
            roles_by_id,
            seen_edges,
            errors,
            warnings,
        )
    _validate_harvested_conflicts(nodes_by_id, roles_by_id, errors)
    _validate_connected(edges, nodes_by_id, roles_by_id, errors)
    levels, cycle_nodes = _topological_levels(list(roles_by_id), edges)
    if cycle_nodes:
        errors.append(
            _error(
                "relationship_cycle",
                "relationships",
                f"Ordering cycle includes: {', '.join(cycle_nodes)}.",
            )
        )
    raw_task = proposal.get("task_model")
    task = raw_task if isinstance(raw_task, dict) else {}
    task_model = {
        key: string_list(task.get(key))
        for key in (
            "deliverables",
            "success_criteria",
            "constraints",
            "subgoals",
            "evidence_needs",
        )
    }
    for field in ("deliverables", "success_criteria", "subgoals", "evidence_needs"):
        if not task_model[field]:
            errors.append(
                _error(
                    "incomplete_task_model",
                    f"task_model.{field}",
                    f"Semantic composition requires at least one {field.replace('_', ' ')} entry.",
                )
            )
    raw_coverage = proposal.get("coverage")
    coverage = raw_coverage if isinstance(raw_coverage, dict) else {}
    normalized = {
        "schema": SEMANTIC_PROPOSAL_SCHEMA,
        "preflight_id": str(proposal.get("preflight_id") or ""),
        "current_phase": str(proposal.get("current_phase") or "start"),
        "task_model": task_model,
        "skill_roles": roles,
        "relationships": edges,
        "coverage": {
            "facets": string_list(coverage.get("facets")),
            "unresolved_gaps": string_list(coverage.get("unresolved_gaps")),
        },
        "trust": COMPOSITION_TRUST,
    }
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized_proposal": normalized,
        "topological_levels": levels,
        "trust": COMPOSITION_TRUST,
        "instruction_override_policy": INSTRUCTION_OVERRIDE_POLICY,
    }
