"""Public deterministic validation entry points for semantic composition."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .composition_preflight import (
    ACTIVE_SOURCE_ROLES,
    COMPOSITION_TRUST,
    INSTRUCTION_OVERRIDE_POLICY,
    PHASE_ORDER,
    SEMANTIC_PROPOSAL_SCHEMA,
    json_list,
    normalized_text,
    string_list,
)
from .composition_declared_dependencies import (
    declared_dependency_closure_is_well_formed,
)
from .composition_validation_graph import (
    _normalized_edge,
    _normalized_role,
    _topological_levels,
    _validate_connected,
    _validate_edge,
    _validate_role,
    ordering_pair,
)
from .composition_validation_conflicts import validate_harvested_conflicts
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


def _validate_declared_dependencies(
    preflight: dict[str, Any],
    roles_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    slices_by_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    """Require a selected seed's explicit skill closure and typed handoff."""

    hints = preflight.get("scoped_seed_graph_hints")
    selected_seed_ids = {
        node_id
        for node_id in roles_by_id
        if str(nodes_by_id.get(node_id, {}).get("source_type") or "")
        == "scoped_packet_seed"
    }
    if not isinstance(hints, Mapping):
        if selected_seed_ids:
            errors.append(
                _error(
                    "missing_declared_dependency_closure",
                    "scoped_seed_graph_hints",
                    "Selected scoped seeds require a prepared declared dependency closure.",
                )
            )
        return
    if "declared_dependency_closure" not in hints:
        if selected_seed_ids:
            errors.append(
                _error(
                    "missing_declared_dependency_closure",
                    "scoped_seed_graph_hints.declared_dependency_closure",
                    "Selected scoped seeds require a prepared declared dependency closure.",
                )
            )
        return
    closure = hints.get("declared_dependency_closure")
    if not declared_dependency_closure_is_well_formed(closure):
        errors.append(
            _error(
                "invalid_declared_dependency_closure",
                "scoped_seed_graph_hints.declared_dependency_closure",
                "Declared dependency closure must match the prepared contract.",
            )
        )
        return
    assert isinstance(closure, Mapping)
    selected_seed_hint_records = [
        seed
        for seed in json_list(hints.get("scoped_seeds"))
        if isinstance(seed, dict) and str(seed.get("id") or "") in selected_seed_ids
    ]
    selected_seed_hint_counts: dict[str, int] = {}
    for seed in selected_seed_hint_records:
        seed_id = str(seed.get("id") or "")
        selected_seed_hint_counts[seed_id] = (
            selected_seed_hint_counts.get(seed_id, 0) + 1
        )
    for seed_id in sorted(selected_seed_ids):
        hint_count = selected_seed_hint_counts.get(seed_id, 0)
        if hint_count == 1:
            continue
        errors.append(
            _error(
                (
                    "missing_selected_scoped_seed_hint"
                    if hint_count == 0
                    else "ambiguous_selected_scoped_seed_hint"
                ),
                "scoped_seed_graph_hints.scoped_seeds",
                f"Selected seed {seed_id} requires one source-backed lifecycle hint.",
            )
        )
    declared_seed_hints = {
        str(seed.get("id") or ""): seed for seed in selected_seed_hint_records
    }
    roots = {str(seed_id) for seed_id in json_list(closure.get("root_seed_ids"))}
    dependency_seed_ids = {
        str(dependency.get("source_node_id") or "")
        for dependency in json_list(closure.get("required_dependency_nodes"))
        if isinstance(dependency, dict)
    }
    for seed_id in sorted(selected_seed_ids):
        if seed_id not in roots and seed_id not in dependency_seed_ids:
            errors.append(
                _error(
                    "missing_declared_dependency_closure",
                    "scoped_seed_graph_hints.declared_dependency_closure",
                    f"Selected seed {seed_id} is not covered by the prepared closure.",
                )
            )
    for dependency in json_list(closure.get("required_dependency_nodes")):
        if not isinstance(dependency, dict):
            continue
        seed_id = str(dependency.get("seed_id") or "")
        target_id = str(dependency.get("source_node_id") or "")
        if (
            target_id in selected_seed_ids
            and target_id not in roots
            and seed_id not in roles_by_id
        ):
            errors.append(
                _error(
                    "missing_declared_dependency_parent",
                    "skill_roles",
                    f"Selected dependency seed {target_id} requires declaring seed {seed_id}.",
                )
            )
    declared_records = [
        record
        for field in ("required_dependency_nodes", "unresolved_dependencies")
        for record in json_list(closure.get(field))
        if isinstance(record, dict)
    ]
    for dependency in json_list(closure.get("unresolved_dependencies")):
        if not isinstance(dependency, dict):
            continue
        seed_id = str(dependency.get("seed_id") or "")
        if seed_id not in roles_by_id:
            continue
        errors.append(
            _error(
                "unresolved_declared_dependency",
                "scoped_seed_graph_hints.declared_dependency_closure",
                "Selected seed "
                + seed_id
                + " references unavailable dependency "
                + str(dependency.get("reference") or "<empty>")
                + " ("
                + str(dependency.get("status") or "unknown")
                + ").",
            )
        )

    def declared_references(seed: Mapping[str, Any]) -> list[tuple[str, str, str, str]]:
        references = [
            (reference, field, relationship_type, "")
            for field, relationship_type in (
                ("chains_before", "precedes"),
                ("chains_after", "enables"),
            )
            for reference in string_list(seed.get(field))
        ]
        transitions = seed.get("phase_transitions")
        if not isinstance(transitions, Mapping):
            return references
        for phase, transition in transitions.items():
            if not isinstance(transition, Mapping):
                continue
            references.extend(
                (
                    reference,
                    "phase_transitions.activate_skills",
                    "enables",
                    str(phase),
                )
                for reference in string_list(transition.get("activate_skills"))
            )
        return references

    for seed_id, seed in sorted(declared_seed_hints.items()):
        for reference, field, relationship_type, phase in declared_references(seed):
            matching = [
                record
                for record in declared_records
                if str(record.get("seed_id") or "") == seed_id
                and str(record.get("reference") or "") == reference
                and str(record.get("field") or "") == field
                and str(record.get("relationship_type") or "") == relationship_type
                and str(record.get("phase") or "") == phase
            ]
            if len(matching) != 1:
                errors.append(
                    _error(
                        "missing_declared_dependency_closure_entry",
                        "scoped_seed_graph_hints.declared_dependency_closure",
                        f"Selected seed {seed_id} lacks one closure record for {reference}.",
                    )
                )
    for dependency in json_list(closure.get("required_dependency_nodes")):
        if not isinstance(dependency, dict):
            continue
        seed_id = str(dependency.get("seed_id") or "")
        target_id = str(dependency.get("source_node_id") or "")
        if seed_id not in roles_by_id:
            continue
        if target_id not in roles_by_id:
            errors.append(
                _error(
                    "missing_declared_dependency",
                    "skill_roles",
                    f"Selected seed {seed_id} requires source {target_id}.",
                )
            )
            continue
        relation = str(dependency.get("relationship_type") or "")
        matching_edges = [
            edge
            for edge in edges
            if edge.get("from") == seed_id
            and edge.get("to") == target_id
            and edge.get("type") == relation
        ]
        if not matching_edges:
            errors.append(
                _error(
                    "missing_declared_dependency_relationship",
                    "relationships",
                    f"Selected seed {seed_id} requires a {relation} relationship to {target_id}.",
                )
            )
            continue
        seed_citations = {
            slice_id
            for slice_id, source_slice in slices_by_id.items()
            if str(source_slice.get("source_node_id") or "") == seed_id
        }
        if not any(
            seed_citations.intersection(string_list(edge.get("citations")))
            for edge in matching_edges
        ):
            errors.append(
                _error(
                    "unsupported_declared_dependency_relationship",
                    "relationships",
                    f"Declared relationship {seed_id} {relation} {target_id} must cite its seed.",
                )
            )
        declared_phase = str(dependency.get("phase") or "")
        if declared_phase in PHASE_ORDER:
            target_phases = string_list(roles_by_id[target_id].get("phase_affinity"))
            if any(
                phase in PHASE_ORDER
                and PHASE_ORDER.index(phase) < PHASE_ORDER.index(declared_phase)
                for phase in target_phases
            ):
                errors.append(
                    _error(
                        "declared_dependency_phase_inversion",
                        "skill_roles",
                        f"{target_id} cannot activate before declared {declared_phase} phase.",
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
    _validate_declared_dependencies(
        preflight,
        roles_by_id,
        edges,
        nodes_by_id,
        slices_by_id,
        errors,
    )
    validate_harvested_conflicts(nodes_by_id, roles_by_id, errors)
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
