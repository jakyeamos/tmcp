"""Graph-shape and source-binding validation for semantic composition."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .composition import COMPOSITION_GENERIC_TERMS
from .composition_preflight import (
    ACTIVE_SOURCE_ROLES,
    ALLOWED_RELATIONSHIPS,
    PHASE_ORDER,
    RELATIONSHIP_TYPE_SEMANTICS,
    normalized_text,
    string_list,
)
from .composition_validation_text import (
    _CLAIM_GRAMMAR_TERMS,
    _claim_stems,
    _claim_terms,
    _error,
    _source_claim_terms,
    _validate_claim,
)


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


def _phase_indices(role: dict[str, Any]) -> list[int]:
    return [PHASE_ORDER.index(phase) for phase in role["phase_affinity"] if phase in PHASE_ORDER]


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


def _handoff_labels(role: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [
        normalized_text(item).lower()
        for field in fields
        for item in string_list(role.get(field))
        if normalized_text(item)
    ]


def _source_grounded_handoff_labels(
    node_id: str,
    role: dict[str, Any],
    fields: tuple[str, ...],
    slices_by_id: dict[str, dict[str, Any]],
    *,
    allow_generic_handoff_reference: bool = False,
) -> list[str]:
    evidence_terms = _role_source_terms(node_id, role, slices_by_id)
    evidence_stems = {
        stem for term in evidence_terms for stem in _claim_stems(term)
    }
    labels: list[str] = []
    for label in _handoff_labels(role, fields):
        label_terms = _claim_terms(label)
        label_stems = {
            stem for term in label_terms for stem in _claim_stems(term)
        }
        anchored = not label_stems.isdisjoint(evidence_stems)
        generic_reference = (
            allow_generic_handoff_reference
            and not label_terms.difference(
                COMPOSITION_GENERIC_TERMS | _CLAIM_GRAMMAR_TERMS
            )
            and "handoff" in evidence_terms
        )
        if anchored or generic_reference:
            labels.append(label)
    return labels


def _handoff_labels_overlap(
    producer_id: str,
    producer: dict[str, Any],
    consumer_id: str,
    consumer: dict[str, Any],
    slices_by_id: dict[str, dict[str, Any]],
) -> bool:
    producer_labels = _source_grounded_handoff_labels(
        producer_id,
        producer,
        ("outputs",),
        slices_by_id,
    )
    consumer_labels = _source_grounded_handoff_labels(
        consumer_id,
        consumer,
        ("inputs", "entry_gates"),
        slices_by_id,
        allow_generic_handoff_reference=True,
    )
    return any(
        producer_label == consumer_label
        or producer_label in consumer_label
        or consumer_label in producer_label
        for producer_label in producer_labels
        for consumer_label in consumer_labels
    )


def _role_source_terms(
    node_id: str,
    role: dict[str, Any],
    slices_by_id: dict[str, dict[str, Any]],
) -> set[str]:
    return {
        term
        for citation in string_list(role.get("citations"))
        if citation in slices_by_id
        and str(slices_by_id[citation].get("source_node_id") or "") == node_id
        for term in _source_claim_terms(slices_by_id[citation])
    }


def _relationship_type_is_grounded(
    edge: dict[str, Any],
    *,
    nodes_by_id: dict[str, dict[str, Any]],
    slices_by_id: dict[str, dict[str, Any]],
    roles_by_id: dict[str, dict[str, Any]],
) -> bool:
    """Require an ordering edge to resolve to a cited, typed handoff."""

    relation = str(edge.get("type") or "")
    source_id = str(edge.get("from") or "")
    target_id = str(edge.get("to") or "")
    source_role = roles_by_id.get(source_id)
    target_role = roles_by_id.get(target_id)
    if not isinstance(source_role, dict) or not isinstance(target_role, dict):
        return False
    source_source_role = str(nodes_by_id.get(source_id, {}).get("source_role") or "")
    if relation in {"precedes", "enables", "produces"}:
        return (
            source_source_role == "governing_instruction"
            or _handoff_labels_overlap(
                source_id,
                source_role,
                target_id,
                target_role,
                slices_by_id,
            )
        )
    if relation in {"requires", "consumes"}:
        return _handoff_labels_overlap(
            target_id,
            target_role,
            source_id,
            source_role,
            slices_by_id,
        )
    if relation == "verifies":
        verifier_terms = _role_source_terms(source_id, source_role, slices_by_id)
        verifies_capability = any(
            not _claim_stems("verify").isdisjoint(_claim_stems(term))
            for term in verifier_terms
        )
        return verifies_capability and _handoff_labels_overlap(
            target_id,
            target_role,
            source_id,
            source_role,
            slices_by_id,
        )
    # Non-ordering relationships cannot advance a stage. Their endpoint
    # citations remain mandatory and are validated above.
    return relation in {"complements", "conflicts_with"}


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
    for phase in string_list(role.get("phase_affinity")):
        if phase not in PHASE_ORDER:
            errors.append(
                _error(
                    "unknown_phase",
                    f"{path}.phase_affinity",
                    f"Unsupported composition phase: {phase}.",
                )
            )
    if source_role == "governing_instruction" and role["phase_affinity"] != ["start"]:
        errors.append(
            _error(
                "governing_phase_affinity",
                f"{path}.phase_affinity",
                "Governing instructions must have only the start phase affinity.",
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
    cited_slices = [
        slices_by_id[citation]
        for citation in citations
        if citation in slices_by_id
        and str(slices_by_id[citation].get("source_node_id") or "") == node_id
    ]
    evidence_terms = {
        term for source_slice in cited_slices for term in _source_claim_terms(source_slice)
    }
    evidence_text = "\n".join(
        normalized_text(source_slice.get("content")) for source_slice in cited_slices
    )
    for field in (
        "role",
        "inputs",
        "outputs",
        "entry_gates",
        "exit_gates",
        "covers",
    ):
        _validate_claim(
            role.get(field),
            path=f"{path}.{field}",
            evidence_terms=evidence_terms,
            evidence_text=evidence_text,
            errors=errors,
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
    cited_slices = [
        slices_by_id[citation]
        for citation in citations
        if citation in slices_by_id
    ]
    evidence_terms = {
        term for source_slice in cited_slices for term in _source_claim_terms(source_slice)
    }
    evidence_text = "\n".join(
        normalized_text(source_slice.get("content")) for source_slice in cited_slices
    )
    if str(edge.get("rationale") or "").strip():
        _validate_claim(
            edge.get("rationale"),
            path=f"{path}.rationale",
            evidence_terms=evidence_terms,
            evidence_text=evidence_text,
            ignored_terms=_claim_terms(source).union(_claim_terms(target)),
            errors=errors,
        )
    if (
        relation in ALLOWED_RELATIONSHIPS
        and source in roles_by_id
        and target in roles_by_id
        and not _relationship_type_is_grounded(
            edge,
            nodes_by_id=nodes_by_id,
            slices_by_id=slices_by_id,
            roles_by_id=roles_by_id,
        )
    ):
        errors.append(
            _error(
                "unsupported_relationship_claim",
                f"{path}.type",
                "Relationship type does not resolve to a source-grounded handoff.",
            )
        )
    if source in nodes_by_id and target in nodes_by_id:
        source_role = str(nodes_by_id[source].get("source_role") or "")
        target_role = str(nodes_by_id[target].get("source_role") or "")
        pair = ordering_pair(edge)
        if pair and pair[0] in roles_by_id and pair[1] in roles_by_id:
            predecessor_indices = _phase_indices(roles_by_id[pair[0]])
            dependent_indices = _phase_indices(roles_by_id[pair[1]])
            if predecessor_indices and dependent_indices and max(predecessor_indices) > min(dependent_indices):
                errors.append(
                    _error(
                        "phase_order_inversion",
                        path,
                        "A prerequisite cannot have a later phase affinity than its dependent.",
                    )
                )
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
