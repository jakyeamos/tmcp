"""Normalization and typed graph policy for curated scoped packet seeds."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCOPED_SEED_RELATIONS = frozenset(
    {
        "activates",
        "affinity_for_route",
        "conflicts_with",
        "declares_behavior_atom",
        "defines_phase_transition",
        "enables",
        "precedes",
        "requires_receipt",
        "requires_verification",
        "supports_scoped_packet_seed",
        "transitions_to",
    }
)


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _ordered_strings(value: object) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in _json_list(value):
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def normalize_phase_transitions(value: object) -> dict[str, dict[str, list[str]]]:
    """Normalize the executable subset of scoped-seed phase transitions."""

    if not isinstance(value, Mapping):
        return {}
    transitions: dict[str, dict[str, list[str]]] = {}
    for raw_phase, raw_transition in value.items():
        phase = str(raw_phase).strip().lower()
        if not phase or not isinstance(raw_transition, Mapping):
            continue
        next_phases = _ordered_strings(raw_transition.get("next_phases"))
        if not next_phases:
            next_phases = _ordered_strings(raw_transition.get("next"))
        transitions[phase] = {
            "next_phases": next_phases,
            "activate_skills": _ordered_strings(raw_transition.get("activate_skills")),
            "verification_gates": _ordered_strings(
                raw_transition.get("verification_gates")
            ),
        }
    return transitions


def normalize_scoped_seed(seed: Mapping[str, Any]) -> dict[str, Any]:
    """Whitelist one scoped seed without discarding routing or lifecycle semantics."""

    seed_id = str(seed.get("id") or seed.get("seed_id") or "").strip()
    if not seed_id:
        return {}
    source_role = str(seed.get("source_role") or "active_skill").strip()
    explicit_activation = seed.get("activation_eligible")
    role_eligible = source_role in {"active_skill", "governing_instruction"}
    activation_eligible = role_eligible and explicit_activation is not False
    return {
        "id": seed_id,
        "name": str(seed.get("name") or seed.get("title") or seed_id),
        "kind": "scoped_packet_seed",
        "promotion_status": str(
            seed.get("promotion_status") or "proposal_not_promoted"
        ),
        "promote_as_single_global_graph": bool(
            seed.get("promote_as_single_global_graph", False)
        ),
        "relative_path": seed.get("relative_path"),
        "canonical_source": seed.get("canonical_source"),
        "source_role": source_role,
        "activation_eligible": activation_eligible,
        "source_references": _ordered_strings(seed.get("source_references")),
        "loads": _ordered_strings(seed.get("loads")),
        "route_affinity": _ordered_strings(seed.get("route_affinity")),
        "objective_patterns": _ordered_strings(seed.get("objective_patterns")),
        "phase_transitions": normalize_phase_transitions(seed.get("phase_transitions")),
        "chains_before": _ordered_strings(seed.get("chains_before")),
        "chains_after": _ordered_strings(seed.get("chains_after")),
        "do_not_activate_with": _ordered_strings(seed.get("do_not_activate_with")),
        "use_when": _ordered_strings(seed.get("use_when")),
        "modes": _ordered_strings(seed.get("modes")),
        "minimum_spec_fields": _ordered_strings(seed.get("minimum_spec_fields")),
        "ticket_types": _ordered_strings(seed.get("ticket_types")),
        "behavior_atoms": _ordered_strings(seed.get("behavior_atoms")),
        "verification_expectations": _ordered_strings(
            seed.get("verification_expectations")
        ),
        "required_receipts": _ordered_strings(seed.get("required_receipts")),
        "constraints": _ordered_strings(seed.get("constraints")),
        "routing_trigger": seed.get("routing_trigger"),
        "trust": "advisory_untrusted",
    }


def _skill_node_id(skill_id: str) -> str:
    return f"skill:{skill_id}"


def scoped_seed_graph_metadata(
    scoped_seeds: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Build deterministic typed nodes and edges for normalized scoped seeds."""

    route_nodes: list[dict[str, Any]] = []
    phase_nodes: list[dict[str, Any]] = []
    receipt_nodes: list[dict[str, Any]] = []
    verification_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(target: list[dict[str, Any]], node: dict[str, Any]) -> None:
        node_id = str(node.get("id") or "")
        if not node_id or node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        target.append(node)

    def add_edge(from_id: str, to_id: str, relation: str) -> None:
        if relation not in SCOPED_SEED_RELATIONS:
            return
        key = (from_id, to_id, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"from": from_id, "to": to_id, "relation": relation})

    for raw_seed in scoped_seeds:
        seed = normalize_scoped_seed(raw_seed)
        seed_id = str(seed.get("id") or "")
        if not seed_id:
            continue
        for source_ref in seed["source_references"]:
            add_edge(source_ref, seed_id, "supports_scoped_packet_seed")
        for atom in seed["behavior_atoms"]:
            add_edge(seed_id, atom, "declares_behavior_atom")
        for route_id in seed["route_affinity"]:
            route_node_id = f"route:{route_id}"
            add_node(
                route_nodes,
                {"id": route_node_id, "route_id": route_id},
            )
            add_edge(seed_id, route_node_id, "affinity_for_route")
        for skill_id in seed["chains_before"]:
            add_edge(seed_id, _skill_node_id(skill_id), "precedes")
        for skill_id in seed["chains_after"]:
            add_edge(seed_id, _skill_node_id(skill_id), "enables")
        for skill_id in seed["do_not_activate_with"]:
            add_edge(seed_id, _skill_node_id(skill_id), "conflicts_with")
        for phase, transition in seed["phase_transitions"].items():
            phase_node_id = f"phase-transition:{seed_id}:{phase}"
            add_node(
                phase_nodes,
                {
                    "id": phase_node_id,
                    "seed_id": seed_id,
                    "from_phase": phase,
                    "next_phases": list(transition["next_phases"]),
                    "activate_skills": list(transition["activate_skills"]),
                    "verification_gates": list(transition["verification_gates"]),
                },
            )
            add_edge(seed_id, phase_node_id, "defines_phase_transition")
            for next_phase in transition["next_phases"]:
                add_edge(
                    phase_node_id,
                    f"phase:{next_phase}",
                    "transitions_to",
                )
            for skill_id in transition["activate_skills"]:
                add_edge(phase_node_id, _skill_node_id(skill_id), "activates")
        for index, expectation in enumerate(seed["verification_expectations"], start=1):
            node_id = f"verification:{seed_id}:{index}"
            add_node(
                verification_nodes,
                {
                    "id": node_id,
                    "seed_id": seed_id,
                    "expectation": expectation,
                },
            )
            add_edge(seed_id, node_id, "requires_verification")
        for index, requirement in enumerate(seed["required_receipts"], start=1):
            node_id = f"receipt-requirement:{seed_id}:{index}"
            add_node(
                receipt_nodes,
                {
                    "id": node_id,
                    "seed_id": seed_id,
                    "requirement": requirement,
                },
            )
            add_edge(seed_id, node_id, "requires_receipt")

    return {
        "route_affinity_nodes": route_nodes,
        "phase_transition_nodes": phase_nodes,
        "receipt_requirement_nodes": receipt_nodes,
        "verification_expectation_nodes": verification_nodes,
        "edges": edges,
    }
