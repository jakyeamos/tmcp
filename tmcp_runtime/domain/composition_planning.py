"""Deterministic staged-plan compilation for validated semantic proposals."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .composition_preflight import (
    COMPOSITION_PLAN_SCHEMA,
    COMPOSITION_TRUST,
    INSTRUCTION_OVERRIDE_POLICY,
    PHASE_ORDER,
    json_list,
    ordered_unique,
    stable_digest,
    string_list,
)
from .composition_optimizer import optimize_semantic_subgraph
from .composition_validation import (
    SemanticProposalValidationError,
    ordering_pair,
    validate_semantic_proposal,
)


def _phase_for_role(role: dict[str, Any], current_phase: str) -> str:
    phases = string_list(role.get("phase_affinity"))
    if current_phase in phases:
        return current_phase
    return min(
        phases or ["start"],
        key=lambda phase: (
            PHASE_ORDER.index(phase) if phase in PHASE_ORDER else len(PHASE_ORDER)
        ),
    )


def _bridge_instruction(role: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    node_id = str(role["node_id"])
    role_name = str(role.get("role") or source.get("title") or node_id)
    inputs = "; ".join(string_list(role.get("inputs")))
    outputs = "; ".join(string_list(role.get("outputs")))
    gates = "; ".join(string_list(role.get("exit_gates")))
    return {
        "node_id": node_id,
        "instruction": (
            f"Apply {role_name} using {inputs}; produce {outputs}; exit when {gates}."
        ),
        "citations": string_list(role.get("citations")),
        "trust": COMPOSITION_TRUST,
    }


def _graph_provenance(
    roles: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    slices_by_id: dict[str, dict[str, Any]],
    scoped_seed_edges: list[dict[str, Any]],
) -> dict[str, Any]:
    digest_by_node = {
        node_id: str(item.get("source_digest") or "")
        for node_id, item in nodes_by_id.items()
    }
    normalized_edges = sorted(
        {
            (
                digest_by_node.get(str(edge["from"]), ""),
                str(edge["type"]),
                digest_by_node.get(str(edge["to"]), ""),
                tuple(
                    sorted(
                        str(slices_by_id[citation].get("slice_digest") or "")
                        for citation in string_list(edge.get("citations"))
                        if citation in slices_by_id
                    )
                ),
            )
            for edge in edges
        }
    )
    normalized_seed_edges = sorted(
        {
            (
                str(edge.get("from") or ""),
                str(edge.get("relation") or ""),
                str(edge.get("to") or ""),
                tuple(
                    sorted(
                        str(slices_by_id[citation].get("slice_digest") or "")
                        for citation in string_list(edge.get("citations"))
                        if citation in slices_by_id
                    )
                ),
            )
            for edge in scoped_seed_edges
        }
    )
    content_digests = sorted({digest_by_node[str(role["node_id"])] for role in roles})
    graph_digest = stable_digest(
        {
            "content_digests": content_digests,
            "edges": normalized_edges,
            "scoped_seed_edges": normalized_seed_edges,
        },
        32,
    )
    return {
        "graph_digest": graph_digest,
        "content_digests": content_digests,
        "normalized_relationship_count": len(normalized_edges),
        "normalized_scoped_seed_relationship_count": len(normalized_seed_edges),
        "identity_policy": "normalized_source_content_and_typed_relationships",
    }


def _ordered_stages(
    levels: list[list[str]],
    roles_by_id: dict[str, dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    current_phase: str,
) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    for level in levels:
        grouped: dict[str, list[str]] = defaultdict(list)
        for node_id in level:
            grouped[_phase_for_role(roles_by_id[node_id], current_phase)].append(
                node_id
            )
        ordered_phases = sorted(
            grouped,
            key=lambda phase: (
                PHASE_ORDER.index(phase) if phase in PHASE_ORDER else len(PHASE_ORDER)
            ),
        )
        for stage_phase in ordered_phases:
            node_ids = sorted(grouped[stage_phase])
            gates = ordered_unique(
                [
                    gate
                    for node_id in node_ids
                    for gate in string_list(roles_by_id[node_id].get("entry_gates"))
                ]
            )
            incoming = [
                edge
                for edge in edges
                if (ordering_pair(edge) or (None, None))[1] in node_ids
            ]
            for edge in incoming:
                predecessor = (ordering_pair(edge) or ("", ""))[0]
                if predecessor and predecessor not in node_ids:
                    gates.append(
                        f"Complete `{predecessor}` and make its handoff available."
                    )
            stages.append(
                {
                    "stage_id": f"stage-{len(stages) + 1}",
                    "order": len(stages) + 1,
                    "phase": stage_phase,
                    "status": "deferred",
                    "entry_conditions": ordered_unique(gates),
                    "node_ids": node_ids,
                    "bridge_instructions": [
                        _bridge_instruction(roles_by_id[node_id], nodes_by_id[node_id])
                        for node_id in node_ids
                    ],
                }
            )
    active_index = next(
        (
            index
            for index, stage in enumerate(stages)
            if stage["phase"] == current_phase
        ),
        0,
    )
    if stages:
        stages[active_index]["status"] = "active"
    return stages


def build_composition_plan(
    proposal: dict[str, Any],
    preflight: dict[str, Any],
    *,
    current_phase: str | None = None,
) -> dict[str, Any]:
    """Compile a validated semantic proposal into a deterministic staged plan."""

    validation = validate_semantic_proposal(proposal, preflight)
    if not validation["valid"]:
        raise SemanticProposalValidationError(validation["errors"])
    normalized = dict(validation["normalized_proposal"])
    normalized, selection_diagnostics = optimize_semantic_subgraph(
        normalized,
        preflight,
    )
    optimized_validation = validate_semantic_proposal(normalized, preflight)
    if not optimized_validation["valid"]:
        raise SemanticProposalValidationError(optimized_validation["errors"])
    normalized = dict(optimized_validation["normalized_proposal"])
    phase = current_phase or str(normalized.get("current_phase") or "start")
    slices = [
        item
        for item in json_list(preflight.get("candidate_source_slices"))
        if isinstance(item, dict)
    ]
    slices_by_id = {str(item.get("slice_id") or ""): item for item in slices}
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for item in slices:
        nodes_by_id.setdefault(str(item.get("source_node_id") or ""), item)
    roles = [
        item
        for item in json_list(normalized.get("skill_roles"))
        if isinstance(item, dict)
    ]
    edges = [
        item
        for item in json_list(normalized.get("relationships"))
        if isinstance(item, dict)
    ]
    roles_by_id = {str(role["node_id"]): role for role in roles}
    levels = [
        string_list(level)
        for level in json_list(optimized_validation["topological_levels"])
    ]
    stages = _ordered_stages(levels, roles_by_id, nodes_by_id, edges, phase)
    active_stage = next(stage for stage in stages if stage["status"] == "active")
    resolved_phase = str(active_stage["phase"])
    active_node_ids = set(string_list(active_stage.get("node_ids")))
    governing_node_ids = {
        str(role["node_id"])
        for role in roles
        if nodes_by_id[str(role["node_id"])]["source_role"] == "governing_instruction"
    }
    covered = ordered_unique(
        [facet for role in roles for facet in string_list(role.get("covers"))]
    )
    task_model = dict(normalized["task_model"])
    criteria = string_list(task_model.get("success_criteria"))
    uncovered = [criterion for criterion in criteria if criterion not in covered]
    coverage_input = dict(normalized["coverage"])
    unresolved = ordered_unique(
        string_list(coverage_input.get("unresolved_gaps")) + uncovered
    )
    scoped_seed_hints = dict(preflight.get("scoped_seed_graph_hints") or {})
    selected_role_ids = {str(role["node_id"]) for role in roles}
    selected_seed_ids = {
        str(seed.get("id") or "")
        for seed in json_list(scoped_seed_hints.get("scoped_seeds"))
        if isinstance(seed, dict) and str(seed.get("id") or "") in selected_role_ids
    }
    selected_seed_citations = {
        citation
        for seed in json_list(scoped_seed_hints.get("scoped_seeds"))
        if isinstance(seed, dict) and str(seed.get("id") or "") in selected_seed_ids
        for citation in string_list(seed.get("citations"))
    }
    scoped_seed_edges = [
        edge
        for edge in json_list(scoped_seed_hints.get("typed_edges"))
        if isinstance(edge, dict)
        and selected_seed_citations.intersection(string_list(edge.get("citations")))
    ]
    provenance = _graph_provenance(
        roles,
        edges,
        nodes_by_id,
        slices_by_id,
        scoped_seed_edges,
    )
    recipe_roles = sorted(
        [
            {
                "source_digest": str(
                    nodes_by_id[str(role["node_id"])].get("source_digest") or ""
                ),
                "source_role": str(
                    nodes_by_id[str(role["node_id"])].get("source_role") or ""
                ),
                "role": str(role.get("role") or ""),
                "inputs": string_list(role.get("inputs")),
                "outputs": string_list(role.get("outputs")),
                "phase_affinity": string_list(role.get("phase_affinity")),
                "entry_gates": string_list(role.get("entry_gates")),
                "exit_gates": string_list(role.get("exit_gates")),
                "context_cost": int(role.get("context_cost") or 0),
                "covers": string_list(role.get("covers")),
            }
            for role in roles
        ],
        key=lambda item: (item["source_digest"], item["role"]),
    )
    recipe_stages = [
        {
            "order": int(stage.get("order") or 0),
            "phase": str(stage.get("phase") or ""),
            "source_digests": sorted(
                str(nodes_by_id[node_id].get("source_digest") or "")
                for node_id in string_list(stage.get("node_ids"))
            ),
        }
        for stage in stages
    ]
    plan_identity = {
        "preflight_id": preflight.get("preflight_id"),
        "task_model": task_model,
        "graph_digest": provenance["graph_digest"],
        "current_phase": resolved_phase,
        "roles": recipe_roles,
        "stages": recipe_stages,
        "coverage": {
            "facets": string_list(coverage_input.get("facets")),
            "unresolved_gaps": string_list(coverage_input.get("unresolved_gaps")),
        },
    }
    recipe_digest = stable_digest(plan_identity, 32)
    provenance["recipe_digest"] = recipe_digest
    process_only = [
        str(role["node_id"]) for role in roles if not string_list(role.get("covers"))
    ]
    active_context_cost = sum(
        int(role.get("context_cost") or 0)
        for role in roles
        if str(role["node_id"]) in active_node_ids.union(governing_node_ids)
    )
    selected_context_cost = sum(int(role.get("context_cost") or 0) for role in roles)
    compiled_context_ratio = (
        round(active_context_cost / selected_context_cost, 4)
        if selected_context_cost
        else 0.0
    )
    selection_diagnostics["active_context_cost"] = active_context_cost
    selection_diagnostics["compiled_context_ratio"] = compiled_context_ratio
    selection_diagnostics["compiled_context_budget_warning"] = (
        compiled_context_ratio > 0.75
    )
    return {
        "schema": COMPOSITION_PLAN_SCHEMA,
        "composition_plan_id": "composition-" + recipe_digest[:20],
        "preflight_id": preflight.get("preflight_id"),
        "current_phase": resolved_phase,
        "governing_node_ids": sorted(governing_node_ids),
        "task_model": task_model,
        "skill_roles": [
            {
                **role,
                "source_role": nodes_by_id[str(role["node_id"])]["source_role"],
                "activation": (
                    "active"
                    if str(role["node_id"]) in active_node_ids.union(governing_node_ids)
                    else "deferred"
                ),
            }
            for role in roles
        ],
        "typed_edges": edges,
        "scoped_seed_graph_hints": {
            **scoped_seed_hints,
            "scoped_seeds": [
                seed
                for seed in json_list(scoped_seed_hints.get("scoped_seeds"))
                if isinstance(seed, dict)
                and str(seed.get("id") or "") in selected_seed_ids
            ],
            "typed_edges": scoped_seed_edges,
        },
        "ordered_stages": stages,
        "coverage": {
            "facets": ordered_unique(
                string_list(coverage_input.get("facets")) + covered
            ),
            "covered_criteria": [
                criterion for criterion in criteria if criterion in covered
            ],
            "uncovered_criteria": uncovered,
            "unresolved_gaps": unresolved,
        },
        "provenance": provenance,
        "composition_diagnostics": {
            "missing_capabilities": unresolved,
            "uncovered_criteria": uncovered,
            "conflicts": [
                edge for edge in edges if edge.get("type") == "conflicts_with"
            ],
            "rejected_proposal_elements": validation["errors"],
            "truncation": dict(preflight.get("diagnostics") or {}),
            "process_only_warnings": process_only,
            "validation_warnings": optimized_validation["warnings"],
            "subgraph_selection": selection_diagnostics,
        },
        "trust": COMPOSITION_TRUST,
        "instruction_override_policy": INSTRUCTION_OVERRIDE_POLICY,
    }


def compile_semantic_composition(
    proposal: dict[str, Any],
    preflight: dict[str, Any],
    *,
    current_phase: str | None = None,
) -> dict[str, Any]:
    """Return an integration-friendly accepted/rejected composition envelope."""

    validation = validate_semantic_proposal(proposal, preflight)
    if not validation["valid"]:
        return {
            "accepted": False,
            "validation": validation,
            "composition_plan": None,
            "trust": COMPOSITION_TRUST,
        }
    return {
        "accepted": True,
        "validation": validation,
        "composition_plan": build_composition_plan(
            proposal, preflight, current_phase=current_phase
        ),
        "trust": COMPOSITION_TRUST,
    }
