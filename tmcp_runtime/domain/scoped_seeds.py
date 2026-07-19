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
MAX_SCOPED_SEED_ID_CHARS = 160
MAX_SCOPED_SEED_NAME_CHARS = 160
MAX_SCOPED_SEED_VALUE_CHARS = 240
MAX_SCOPED_SEED_PATH_CHARS = 512
MAX_SCOPED_SEED_STATUS_CHARS = 80
MAX_SCOPED_SEED_TRUNCATION_LABEL_CHARS = 80
MAX_SCOPED_SEED_LIST_ITEMS = 12
MAX_SCOPED_SEED_PHASES = 5
MAX_SCOPED_SEED_PHASE_ITEMS = 8


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded_text(value: object, maximum: int) -> tuple[str, bool]:
    normalized = str(value or "").strip()
    return normalized[:maximum], len(normalized) > maximum


def _ordered_strings(
    value: object,
    *,
    maximum_items: int = MAX_SCOPED_SEED_LIST_ITEMS,
    maximum_chars: int = MAX_SCOPED_SEED_VALUE_CHARS,
) -> tuple[list[str], bool]:
    seen: set[str] = set()
    result: list[str] = []
    truncated = False
    for item in _json_list(value):
        normalized, value_truncated = _bounded_text(item, maximum_chars)
        truncated = truncated or value_truncated
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if len(result) >= maximum_items:
            truncated = True
            continue
        result.append(normalized)
    return result, truncated


def _normalized_strings(
    value: object,
    field: str,
    truncated_fields: list[str],
    *,
    maximum_items: int = MAX_SCOPED_SEED_LIST_ITEMS,
    maximum_chars: int = MAX_SCOPED_SEED_VALUE_CHARS,
) -> list[str]:
    normalized, truncated = _ordered_strings(
        value,
        maximum_items=maximum_items,
        maximum_chars=maximum_chars,
    )
    if truncated:
        truncated_fields.append(field)
    return normalized


def _normalize_phase_transitions(
    value: object,
) -> tuple[dict[str, dict[str, list[str]]], list[str]]:
    """Normalize the executable subset of scoped-seed phase transitions."""

    if not isinstance(value, Mapping):
        return {}, []
    transitions: dict[str, dict[str, list[str]]] = {}
    truncated_fields: list[str] = []
    for raw_phase, raw_transition in value.items():
        phase, phase_truncated = _bounded_text(raw_phase, MAX_SCOPED_SEED_VALUE_CHARS)
        phase = phase.lower()
        if phase_truncated:
            truncated_fields.append("phase_transitions")
        if not phase or not isinstance(raw_transition, Mapping):
            continue
        if len(transitions) >= MAX_SCOPED_SEED_PHASES:
            truncated_fields.append("phase_transitions")
            continue
        next_phases = _normalized_strings(
            raw_transition.get("next_phases"),
            "phase_transitions.next_phases",
            truncated_fields,
            maximum_items=MAX_SCOPED_SEED_PHASE_ITEMS,
        )
        if not next_phases:
            next_phases = _normalized_strings(
                raw_transition.get("next"),
                "phase_transitions.next",
                truncated_fields,
                maximum_items=MAX_SCOPED_SEED_PHASE_ITEMS,
            )
        transitions[phase] = {
            "next_phases": next_phases,
            "activate_skills": _normalized_strings(
                raw_transition.get("activate_skills"),
                "phase_transitions.activate_skills",
                truncated_fields,
                maximum_items=MAX_SCOPED_SEED_PHASE_ITEMS,
            ),
            "verification_gates": _normalized_strings(
                raw_transition.get("verification_gates"),
                "phase_transitions.verification_gates",
                truncated_fields,
                maximum_items=MAX_SCOPED_SEED_PHASE_ITEMS,
            ),
        }
    return transitions, sorted(set(truncated_fields))


def normalize_phase_transitions(value: object) -> dict[str, dict[str, list[str]]]:
    """Normalize bounded executable scoped-seed phase transitions."""

    transitions, _truncated_fields = _normalize_phase_transitions(value)
    return transitions


def normalize_scoped_seed(seed: Mapping[str, Any]) -> dict[str, Any]:
    """Whitelist one scoped seed without discarding routing or lifecycle semantics."""

    seed_id, id_truncated = _bounded_text(
        seed.get("id") or seed.get("seed_id"),
        MAX_SCOPED_SEED_ID_CHARS,
    )
    if not seed_id or id_truncated:
        return {}
    source_role, source_role_truncated = _bounded_text(
        seed.get("source_role") or "active_skill",
        MAX_SCOPED_SEED_VALUE_CHARS,
    )
    explicit_activation = seed.get("activation_eligible")
    role_eligible = source_role in {"active_skill", "governing_instruction"}
    activation_eligible = role_eligible and explicit_activation is not False
    inherited_truncations, inherited_truncations_truncated = _ordered_strings(
        seed.get("metadata_truncated_fields"),
        maximum_chars=MAX_SCOPED_SEED_TRUNCATION_LABEL_CHARS,
    )
    truncated_fields: list[str] = list(inherited_truncations)
    if inherited_truncations_truncated:
        truncated_fields.append("metadata_truncated_fields")
    if source_role_truncated:
        truncated_fields.append("source_role")
    name, name_truncated = _bounded_text(
        seed.get("name") or seed.get("title") or seed_id,
        MAX_SCOPED_SEED_NAME_CHARS,
    )
    if name_truncated:
        truncated_fields.append("name")
    transitions, transition_truncations = _normalize_phase_transitions(
        seed.get("phase_transitions")
    )
    truncated_fields.extend(transition_truncations)
    promotion_status, promotion_status_truncated = _bounded_text(
        seed.get("promotion_status") or "proposal_not_promoted",
        MAX_SCOPED_SEED_STATUS_CHARS,
    )
    relative_path, relative_path_truncated = _bounded_text(
        seed.get("relative_path"),
        MAX_SCOPED_SEED_PATH_CHARS,
    )
    canonical_source, canonical_source_truncated = _bounded_text(
        seed.get("canonical_source"),
        MAX_SCOPED_SEED_PATH_CHARS,
    )
    routing_trigger, routing_trigger_truncated = _bounded_text(
        seed.get("routing_trigger"),
        MAX_SCOPED_SEED_VALUE_CHARS,
    )
    if promotion_status_truncated:
        truncated_fields.append("promotion_status")
    if relative_path_truncated:
        truncated_fields.append("relative_path")
    if canonical_source_truncated:
        truncated_fields.append("canonical_source")
    if routing_trigger_truncated:
        truncated_fields.append("routing_trigger")
    return {
        "id": seed_id,
        "name": name,
        "kind": "scoped_packet_seed",
        "promotion_status": promotion_status,
        "promote_as_single_global_graph": bool(
            seed.get("promote_as_single_global_graph", False)
        ),
        "relative_path": relative_path,
        "canonical_source": canonical_source,
        "source_role": source_role,
        "activation_eligible": activation_eligible,
        "source_references": _normalized_strings(
            seed.get("source_references"), "source_references", truncated_fields
        ),
        "loads": _normalized_strings(seed.get("loads"), "loads", truncated_fields),
        "route_affinity": _normalized_strings(
            seed.get("route_affinity"), "route_affinity", truncated_fields
        ),
        "objective_patterns": _normalized_strings(
            seed.get("objective_patterns"), "objective_patterns", truncated_fields
        ),
        "phase_transitions": transitions,
        "chains_before": _normalized_strings(
            seed.get("chains_before"), "chains_before", truncated_fields
        ),
        "chains_after": _normalized_strings(
            seed.get("chains_after"), "chains_after", truncated_fields
        ),
        "do_not_activate_with": _normalized_strings(
            seed.get("do_not_activate_with"),
            "do_not_activate_with",
            truncated_fields,
        ),
        "use_when": _normalized_strings(
            seed.get("use_when"), "use_when", truncated_fields
        ),
        "modes": _normalized_strings(seed.get("modes"), "modes", truncated_fields),
        "minimum_spec_fields": _normalized_strings(
            seed.get("minimum_spec_fields"),
            "minimum_spec_fields",
            truncated_fields,
        ),
        "ticket_types": _normalized_strings(
            seed.get("ticket_types"), "ticket_types", truncated_fields
        ),
        "behavior_atoms": _normalized_strings(
            seed.get("behavior_atoms"), "behavior_atoms", truncated_fields
        ),
        "verification_expectations": _normalized_strings(
            seed.get("verification_expectations"),
            "verification_expectations",
            truncated_fields,
        ),
        "required_receipts": _normalized_strings(
            seed.get("required_receipts"), "required_receipts", truncated_fields
        ),
        "constraints": _normalized_strings(
            seed.get("constraints"), "constraints", truncated_fields
        ),
        "routing_trigger": routing_trigger,
        "metadata_truncated_fields": sorted(set(truncated_fields)),
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
