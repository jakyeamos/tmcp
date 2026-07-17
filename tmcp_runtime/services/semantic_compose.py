"""Apply validated semantic plans to compatibility composed packets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

from tmcp_runtime.domain.harvest_nodes import json_list, ordered_unique, string_list
from tmcp_runtime.domain.packets import render_composed_packet_markdown
from tmcp_runtime.domain.receipts import build_receipt_template


InstructionBuilder = Callable[[Mapping[str, Any]], list[str]]


def _routing_metadata(node: Mapping[str, Any]) -> dict[str, Any]:
    metadata = node.get("routing_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _semantic_source_nodes(
    plan: Mapping[str, Any],
    preflight: Mapping[str, Any],
    source_nodes: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    path_by_node_id: dict[str, str] = {}
    for item in json_list(preflight.get("candidate_source_slices")):
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("source_node_id") or "")
        path_by_node_id.setdefault(node_id, str(item.get("relative_path") or ""))
    source_by_path = {
        str(node.get("relative_path") or node.get("path") or ""): node
        for node in source_nodes
    }
    source_by_id = {
        str(node.get("id") or ""): node for node in source_nodes if node.get("id")
    }
    selected: dict[str, dict[str, Any]] = {}
    for role in json_list(plan.get("skill_roles")):
        if not isinstance(role, dict):
            continue
        node_id = str(role.get("node_id") or "")
        node = source_by_id.get(node_id) or source_by_path.get(
            path_by_node_id.get(node_id, "")
        )
        if node is not None:
            selected[node_id] = node
    return selected


def _semantic_packet_id(
    packet: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> str:
    identity = {
        "objective": packet.get("objective"),
        "phase": packet.get("phase"),
        "composition_plan_id": plan.get("composition_plan_id"),
        "graph_digest": dict(plan.get("provenance") or {}).get("graph_digest"),
    }
    serialized = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "packet-" + hashlib.sha256(serialized.encode()).hexdigest()[:12]


def _apply_rejected_semantic_proposal(
    packet: dict[str, Any],
    preflight: Mapping[str, Any],
    compiled: Mapping[str, Any],
) -> dict[str, Any]:
    validation = dict(compiled.get("validation") or {})
    diagnostics = dict(packet.get("composition_diagnostics") or {})
    diagnostics.update(
        {
            "preflight": dict(preflight.get("diagnostics") or {}),
            "rejected_proposal_elements": json_list(validation.get("errors")),
            "validation_warnings": json_list(validation.get("warnings")),
        }
    )
    packet["ok"] = False
    packet["active_instructions"] = []
    packet["active_atoms"] = []
    packet["tool_script_prompts"] = []
    packet["verification_gates"] = []
    packet["stop_conditions"] = []
    packet["composition_plan"] = None
    packet["semantic_proposal_validation"] = {
        "accepted": False,
        "errors": json_list(validation.get("errors")),
        "warnings": json_list(validation.get("warnings")),
    }
    packet["composition_diagnostics"] = diagnostics
    shortcut = dict(packet.get("shortcut_candidate") or {})
    shortcut.update(
        {
            "status": "ineligible",
            "matched": False,
            "reason": "The semantic proposal failed deterministic validation.",
        }
    )
    packet["shortcut_candidate"] = shortcut
    packet["packet_markdown"] = render_composed_packet_markdown(packet)
    return packet


def apply_semantic_composition(
    packet: dict[str, Any],
    *,
    source_nodes: list[dict[str, Any]],
    preflight: Mapping[str, Any],
    compiled: Mapping[str, Any],
    instruction_builder: InstructionBuilder,
) -> dict[str, Any]:
    """Project one accepted plan, or a structured rejection, onto a packet."""

    if not bool(compiled.get("accepted")):
        return _apply_rejected_semantic_proposal(packet, preflight, compiled)
    plan = compiled.get("composition_plan")
    if not isinstance(plan, dict):
        raise ValueError("Accepted semantic composition requires a composition plan.")
    selected = _semantic_source_nodes(plan, preflight, source_nodes)
    roles = [
        item for item in json_list(plan.get("skill_roles")) if isinstance(item, dict)
    ]
    active_node_ids = {
        str(role.get("node_id") or "")
        for role in roles
        if role.get("activation") == "active"
        or role.get("source_role") == "governing_instruction"
    }
    active_nodes = [
        selected[str(role.get("node_id") or "")]
        for role in roles
        if str(role.get("node_id") or "") in active_node_ids
        and str(role.get("node_id") or "") in selected
    ]
    deferred_nodes = [
        selected[str(role.get("node_id") or "")]
        for role in roles
        if str(role.get("node_id") or "") in selected
        and str(role.get("node_id") or "") not in active_node_ids
    ]
    active_bridges = [
        bridge
        for stage in json_list(plan.get("ordered_stages"))
        if isinstance(stage, dict) and stage.get("status") == "active"
        for bridge in json_list(stage.get("bridge_instructions"))
        if isinstance(bridge, dict)
    ]
    active_instructions = [
        instruction
        for node in active_nodes
        for instruction in instruction_builder(node)
        if not instruction.startswith("Apply relevant harvested behavior atoms")
    ]
    active_instructions.extend(
        str(bridge.get("instruction") or "") for bridge in active_bridges
    )
    active_atoms = ordered_unique(
        [
            atom
            for node in active_nodes
            for atom in string_list(node.get("behavior_atoms"))
        ]
    )
    deferred_atoms = ordered_unique(
        [
            atom
            for node in deferred_nodes
            for atom in string_list(node.get("behavior_atoms"))
            if atom not in active_atoms
        ]
    )
    packet["active_instructions"] = ordered_unique(active_instructions)[:10]
    packet["tool_script_prompts"] = ordered_unique(
        [
            prompt
            for node in active_nodes
            for prompt in string_list(
                _routing_metadata(node).get("tool_script_prompts")
            )
        ]
    )[:10]
    packet["stop_conditions"] = ordered_unique(
        [
            condition
            for node in active_nodes
            for condition in string_list(_routing_metadata(node).get("stop_conditions"))
        ]
    )[:8]
    packet["active_atoms"] = active_atoms[:16]
    packet["deferred_atoms"] = deferred_atoms[:16]
    current_stage_conditions = ordered_unique(
        [
            condition
            for stage in json_list(plan.get("ordered_stages"))
            if isinstance(stage, dict) and stage.get("status") == "active"
            for condition in string_list(stage.get("entry_conditions"))
        ]
    )
    active_exit_gates = ordered_unique(
        [
            gate
            for role in roles
            if str(role.get("node_id") or "") in active_node_ids
            for gate in string_list(role.get("exit_gates"))
        ]
    )
    packet["verification_gates"] = ordered_unique(
        current_stage_conditions + active_exit_gates
    )[:16]
    citations: list[dict[str, Any]] = []
    for role in roles:
        node_id = str(role.get("node_id") or "")
        node = selected.get(node_id)
        if node is None:
            continue
        citations.append(
            {
                "source": node.get("relative_path"),
                "path": node.get("path"),
                "source_role": role.get("source_role"),
                "content_digest": node.get("content_digest"),
                "matched_atoms": string_list(node.get("behavior_atoms"))[:5],
                "relationship_citations": string_list(role.get("citations")),
                "trust": node.get("trust", "untrusted_harvested_text"),
            }
        )
    selected_paths = {
        str(node.get("relative_path") or node.get("path") or "")
        for node in selected.values()
    }
    packet["ignored_sources"] = [
        item
        for item in json_list(packet.get("ignored_sources"))
        if isinstance(item, dict)
        and str(item.get("source") or "") not in selected_paths
    ]
    packet["evidence_citations"] = citations
    plan_diagnostics = dict(plan.get("composition_diagnostics") or {})
    diagnostics = dict(packet.get("composition_diagnostics") or {})
    diagnostics.update(plan_diagnostics)
    diagnostics["preflight"] = dict(preflight.get("diagnostics") or {})
    packet["composition_diagnostics"] = diagnostics
    packet["conflicts"] = json_list(plan_diagnostics.get("conflicts"))
    packet["composition_plan"] = plan
    validation = dict(compiled.get("validation") or {})
    packet["semantic_proposal_validation"] = {
        "accepted": True,
        "errors": [],
        "warnings": json_list(validation.get("warnings")),
    }
    provenance = dict(plan.get("provenance") or {})
    graph_digest = str(provenance.get("graph_digest") or "")
    compiled_from = dict(packet.get("compiled_from") or {})
    compiled_from["composition_graph_digest"] = graph_digest
    if graph_digest:
        compiled_from["graph_version"] = graph_digest[:16]
    packet["compiled_from"] = compiled_from
    packet_id = _semantic_packet_id(packet, plan)
    packet["packet_id"] = packet_id
    selected_skill_ids = [
        str(role.get("node_id") or "")
        for role in roles
        if role.get("source_role") == "active_skill"
    ]
    packet["receipt_template"] = build_receipt_template(
        packet_id=packet_id,
        activated_atoms=packet["active_atoms"],
        composition_fields={
            "recipe_id": plan.get("composition_plan_id"),
            "task_identity": packet.get("task_identity") or {},
            "graph_digest": graph_digest,
            "content_digests": string_list(provenance.get("content_digests")),
            "selected_skill_ids": selected_skill_ids,
            "phase_trace": [
                {
                    "phase": packet.get("phase"),
                    "status": "active",
                    "activated_skill_ids": sorted(active_node_ids),
                }
            ],
            "gate_results": [],
        },
    )
    shortcut = dict(packet.get("shortcut_candidate") or {})
    shortcut.update(
        {
            "status": "ineligible",
            "matched": False,
            "compiled_from": {
                **dict(shortcut.get("compiled_from") or {}),
                **compiled_from,
            },
            "reason": (
                "Semantic compositions require verified receipts and explicit "
                "project-recipe promotion before shortcut reuse."
            ),
        }
    )
    packet["shortcut_candidate"] = shortcut
    safety = dict(packet.get("safety") or {})
    safety["host_assisted_semantics"] = True
    safety["semantic_proposal_executes_tools"] = False
    packet["safety"] = safety
    packet["packet_markdown"] = render_composed_packet_markdown(packet)
    return packet
