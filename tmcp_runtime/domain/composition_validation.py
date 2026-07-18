"""Public deterministic validation entry points for semantic composition."""

from __future__ import annotations

from typing import Any

from .composition_preflight import (
    ACTIVE_SOURCE_ROLES,
    COMPOSITION_TRUST,
    INSTRUCTION_OVERRIDE_POLICY,
    SEMANTIC_PROPOSAL_SCHEMA,
    json_list,
    normalized_text,
    string_list,
)
from .composition_validation_graph import (
    _normalized_edge,
    _normalized_role,
    _topological_levels,
    _validate_connected,
    _validate_edge,
    _validate_harvested_conflicts,
    _validate_role,
    ordering_pair,
)
from .composition_validation_text import (
    _action_is_prohibited,
    _claim_is_supported,
    _claim_stems,
    _claim_terms,
    _error,
    _hazardous_text,
    _security_clauses,
    _security_text,
    _source_claim_terms,
    _validate_claim,
)


class SemanticProposalValidationError(ValueError):
    """Raised when a host semantic proposal fails deterministic validation."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__("Semantic proposal failed deterministic validation.")


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
    task_evidence_terms = _claim_terms(preflight.get("objective"))
    task_evidence_text = normalized_text(preflight.get("objective"))
    selected_task_slices = [
        source_slice
        for source_slice in slices
        if str(source_slice.get("source_node_id") or "") in roles_by_id
        and str(source_slice.get("source_role") or "") in ACTIVE_SOURCE_ROLES
    ]
    task_evidence_terms.update(
        term
        for source_slice in selected_task_slices
        for term in _source_claim_terms(source_slice)
    )
    task_evidence_text = "\n".join(
        [task_evidence_text]
        + [
            normalized_text(source_slice.get("content"))
            for source_slice in selected_task_slices
        ]
    )
    for field, claims in task_model.items():
        _validate_claim(
            claims,
            path=f"task_model.{field}",
            evidence_terms=task_evidence_terms,
            evidence_text=task_evidence_text,
            require_grounding=field == "constraints",
            errors=errors,
        )
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
    coverage_evidence_terms = set(task_evidence_terms)
    coverage_evidence_terms.update(
        term for claims in task_model.values() for term in _claim_terms(claims)
    )
    for field in ("facets", "unresolved_gaps"):
        _validate_claim(
            coverage.get(field),
            path=f"coverage.{field}",
            evidence_terms=coverage_evidence_terms,
            evidence_text=task_evidence_text,
            require_grounding=False,
            errors=errors,
        )
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
