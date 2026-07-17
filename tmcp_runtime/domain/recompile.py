"""Pure recompilation policy shared by TMCP runtime adapters."""

from __future__ import annotations

import json
import hashlib
from collections.abc import Callable, Mapping
from typing import Any


Packet = dict[str, Any]
ComposeMarkdown = Callable[[Packet], str]

RECOMPILE_REASON_DETAILS: dict[str, str] = {
    "user_redirect": "Latest user message redirected the task.",
    "phase_transition": "Family phase transition activated the next skill layer.",
    "implementation_phase_detected": (
        "Work moved from visual exploration into production implementation."
    ),
    "verification_failure": "Runtime failures require debugging and regression focus.",
    "browser_evidence_available": "Browser evidence is available for the next verification step.",
    "task_identity_shift": "Task identity changed materially from the previous packet.",
    "runtime_context_changed": "Runtime evidence changed the next operating packet.",
}


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def parse_previous_packet(arguments: Packet) -> Packet | None:
    previous_packet = arguments.get("previous_packet")
    if isinstance(previous_packet, dict):
        return previous_packet
    if isinstance(previous_packet, str) and previous_packet.strip().startswith("{"):
        payload = json.loads(previous_packet)
        if isinstance(payload, dict):
            return payload
    return None


def resolve_recompile_reason(arguments: Packet, state: Packet) -> str:
    latest_user_message = str(arguments.get("latest_user_message") or "").lower()
    if any(
        term in latest_user_message
        for term in ("actually", "instead", "new goal", "different")
    ):
        return "user_redirect"
    identity_delta = state.get("task_identity_delta")
    if isinstance(identity_delta, dict) and identity_delta.get("reason") in {
        "task_identity_primary_changed",
        "user_redirect",
    }:
        return "task_identity_shift"
    if _string_list(arguments.get("failures")):
        return "verification_failure"
    if _string_list(arguments.get("browser_evidence")):
        return "browser_evidence_available"
    suggested_phase = str(state.get("suggested_phase") or "")
    files_changed = _string_list(arguments.get("files_changed"))
    if suggested_phase:
        if suggested_phase == "implementation" and files_changed:
            return "implementation_phase_detected"
        return "phase_transition"
    if files_changed:
        return "implementation_phase_detected"
    return "runtime_context_changed"


def recompile_detail(reason: str) -> str:
    return RECOMPILE_REASON_DETAILS.get(
        reason, "Runtime evidence changed the next operating packet."
    )


def _drop_reason(item_id: str, recompile_reason: str, packet_delta: Packet) -> str:
    deactivated = set(_string_list(packet_delta.get("deactivated_atoms"))) | set(
        _string_list(packet_delta.get("stale_atoms"))
    )
    if item_id in deactivated:
        return "Deactivated by family phase transition."
    if recompile_reason == "implementation_phase_detected" and (
        "research" in item_id or item_id == "freshness_research"
    ):
        return "Implementation files changed; exploration atoms deferred."
    return f"Not required after {recompile_reason}."


def _composition_plan(packet: Mapping[str, Any]) -> dict[str, Any] | None:
    plan = packet.get("composition_plan")
    return dict(plan) if isinstance(plan, Mapping) else None


def _graph_item_id(prefix: str, item: Mapping[str, Any]) -> str:
    if prefix == "relationship":
        identity: object = [
            item.get("from"),
            item.get("type"),
            item.get("to"),
            sorted(_string_list(item.get("citations"))),
        ]
    elif prefix == "instruction":
        identity = [
            item.get("node_id"),
            item.get("instruction"),
            sorted(_string_list(item.get("citations"))),
        ]
    else:
        identity = dict(item)
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return f"{prefix}-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _plan_graph_snapshot(plan: Mapping[str, Any]) -> dict[str, Any]:
    roles = [
        dict(item)
        for item in _json_list(plan.get("skill_roles"))
        if isinstance(item, Mapping)
    ]
    active_skills = sorted(
        str(role.get("node_id") or "")
        for role in roles
        if role.get("activation") == "active"
        or role.get("source_role") == "governing_instruction"
    )
    deferred_skills = sorted(
        str(role.get("node_id") or "")
        for role in roles
        if str(role.get("node_id") or "") not in active_skills
    )
    active_nodes = set(active_skills)
    edges = [
        dict(item)
        for item in _json_list(plan.get("typed_edges"))
        if isinstance(item, Mapping)
    ]
    active_edges = [
        edge
        for edge in edges
        if str(edge.get("from") or "") in active_nodes
        or str(edge.get("to") or "") in active_nodes
    ]
    relationships = {
        _graph_item_id("relationship", edge): edge for edge in active_edges
    }
    active_stages = [
        item
        for item in _json_list(plan.get("ordered_stages"))
        if isinstance(item, Mapping) and item.get("status") == "active"
    ]
    bridges = [
        dict(bridge)
        for stage in active_stages
        for bridge in _json_list(stage.get("bridge_instructions"))
        if isinstance(bridge, Mapping)
    ]
    instructions = {_graph_item_id("instruction", bridge): bridge for bridge in bridges}
    state = plan.get("runtime_state")
    runtime_state = dict(state) if isinstance(state, Mapping) else {}
    fulfilled = [
        dict(item)
        for item in _json_list(runtime_state.get("fulfilled_obligations"))
        if isinstance(item, Mapping)
    ]
    return {
        "active_skills": active_skills,
        "deferred_skills": deferred_skills,
        "relationships": relationships,
        "instructions": instructions,
        "conflicts": [
            edge
            for edge in active_edges
            if edge.get("type") == "conflicts_with"
            and str(edge.get("from") or "") in active_nodes
            and str(edge.get("to") or "") in active_nodes
        ],
        "reads": _string_list(runtime_state.get("files_read")),
        "fulfilled": fulfilled,
    }


def _composition_graph_diff(previous: Packet, current: Packet) -> Packet | None:
    previous_plan = _composition_plan(previous)
    current_plan = _composition_plan(current)
    if previous_plan is None and current_plan is None:
        return None
    previous_snapshot = _plan_graph_snapshot(previous_plan or {})
    current_snapshot = _plan_graph_snapshot(current_plan or {})
    previous_skills = set(previous_snapshot["active_skills"])
    current_skills = set(current_snapshot["active_skills"])
    previous_relationships = set(previous_snapshot["relationships"])
    current_relationships = set(current_snapshot["relationships"])
    previous_instructions = set(previous_snapshot["instructions"])
    current_instructions = set(current_snapshot["instructions"])
    previous_reads = set(previous_snapshot["reads"])
    previous_fulfilled = {
        str(item.get("gate_id") or "") for item in previous_snapshot["fulfilled"]
    }
    current_fulfilled = {
        str(item.get("gate_id") or "") for item in current_snapshot["fulfilled"]
    }
    return {
        "skills": {
            "added": sorted(current_skills - previous_skills),
            "dropped": sorted(previous_skills - current_skills),
            "unchanged": sorted(previous_skills & current_skills),
            "deferred": current_snapshot["deferred_skills"],
        },
        "relationships": {
            "added": sorted(current_relationships - previous_relationships),
            "dropped": sorted(previous_relationships - current_relationships),
            "unchanged": sorted(previous_relationships & current_relationships),
            "active": list(current_snapshot["relationships"].values()),
        },
        "instructions": {
            "added": sorted(current_instructions - previous_instructions),
            "dropped": sorted(previous_instructions - current_instructions),
            "unchanged": sorted(previous_instructions & current_instructions),
            "active": list(current_snapshot["instructions"].values()),
        },
        "reads": {
            "added": [
                path for path in current_snapshot["reads"] if path not in previous_reads
            ],
            "all": current_snapshot["reads"],
        },
        "gates": {
            "newly_fulfilled": sorted(current_fulfilled - previous_fulfilled),
            "failed": [],
            "pending": [],
            "bypassed": [],
        },
        "conflicts": {"active": current_snapshot["conflicts"]},
        "fulfilled_obligations": {
            "added": sorted(current_fulfilled - previous_fulfilled),
            "all": sorted(current_fulfilled),
        },
    }


def packet_diff(
    previous: Packet,
    current: Packet,
    *,
    packet_delta: Packet,
    recompile_reason: str,
    graph_diff: Mapping[str, Any] | None = None,
    merge_graph_runtime: bool = False,
) -> Packet:
    prev_atoms = set(_string_list(previous.get("active_atoms")))
    curr_atoms = set(_string_list(current.get("active_atoms")))
    previous_required_reads = _string_list(previous.get("required_reads"))
    current_required_reads = _string_list(current.get("required_reads"))
    previous_required_read_set = set(previous_required_reads)
    current_required_read_set = set(current_required_reads)
    prev_routes = set(
        _string_list((previous.get("task_identity") or {}).get("active_routes"))
    )
    curr_routes = set(
        _string_list((current.get("task_identity") or {}).get("active_routes"))
    )
    dropped: list[dict[str, str]] = []
    for atom in sorted(prev_atoms - curr_atoms):
        dropped.append(
            {
                "kind": "atom",
                "id": atom,
                "reason": _drop_reason(atom, recompile_reason, packet_delta),
            }
        )
    for route in sorted(prev_routes - curr_routes):
        dropped.append(
            {
                "kind": "route",
                "id": route,
                "reason": _drop_reason(route, recompile_reason, packet_delta),
            }
        )
    added: list[dict[str, str]] = []
    for atom in sorted(curr_atoms - prev_atoms):
        added.append(
            {
                "kind": "atom",
                "id": atom,
                "reason": "Activated after runtime recompile.",
            }
        )
    for skill in _string_list(packet_delta.get("suggested_skills")):
        added.append(
            {
                "kind": "skill",
                "id": skill,
                "reason": "phase_transitions.activate_skills",
            }
        )
    for route in sorted(curr_routes - prev_routes):
        added.append(
            {
                "kind": "route",
                "id": route,
                "reason": "Route activated from runtime evidence.",
            }
        )
    derived_graph_diff = _composition_graph_diff(previous, current)
    resolved_graph_diff = derived_graph_diff
    if graph_diff is not None:
        runtime_graph_diff = {key: value for key, value in graph_diff.items()}
        if not merge_graph_runtime or derived_graph_diff is None:
            resolved_graph_diff = runtime_graph_diff
        else:
            resolved_graph_diff = dict(derived_graph_diff)
            for key in ("reads", "gates", "conflicts", "fulfilled_obligations"):
                value = runtime_graph_diff.get(key)
                if isinstance(value, Mapping):
                    resolved_graph_diff[key] = dict(value)
            for key, active_field in (
                ("skills", "deferred"),
                ("relationships", "active"),
                ("instructions", "active"),
            ):
                runtime_value = runtime_graph_diff.get(key)
                resolved_value = resolved_graph_diff.get(key)
                if isinstance(runtime_value, Mapping) and isinstance(
                    resolved_value, Mapping
                ):
                    merged_value = dict(resolved_value)
                    merged_value[active_field] = runtime_value.get(active_field, [])
                    resolved_graph_diff[key] = merged_value
    if resolved_graph_diff is not None:
        skill_changes = resolved_graph_diff.get("skills")
        if isinstance(skill_changes, Mapping):
            existing_added_skills = {
                item["id"] for item in added if item.get("kind") == "skill"
            }
            for skill in _string_list(skill_changes.get("added")):
                if skill in existing_added_skills:
                    continue
                added.append(
                    {
                        "kind": "skill",
                        "id": skill,
                        "reason": "Activated by composition graph runtime.",
                    }
                )
            for skill in _string_list(skill_changes.get("dropped")):
                dropped.append(
                    {
                        "kind": "skill",
                        "id": skill,
                        "reason": "Deferred by composition graph runtime.",
                    }
                )
    phase_change = None
    previous_phase = str(previous.get("phase") or "")
    current_phase = str(current.get("phase") or "")
    if previous_phase and current_phase and previous_phase != current_phase:
        phase_change = {"from": previous_phase, "to": current_phase}
    result = {
        "dropped": dropped,
        "added": added,
        "unchanged": sorted(prev_atoms & curr_atoms),
        "phase_change": phase_change,
        "required_reads": {
            "added": [
                path
                for path in current_required_reads
                if path not in previous_required_read_set
            ],
            "dropped": [
                path
                for path in previous_required_reads
                if path not in current_required_read_set
            ],
            "unchanged": [
                path
                for path in current_required_reads
                if path in previous_required_read_set
            ],
            "all": current_required_reads,
        },
    }
    if resolved_graph_diff is not None:
        graph_phase_change = resolved_graph_diff.get("phase_change")
        if graph_phase_change is not None:
            result["phase_change"] = graph_phase_change
        for key in (
            "skills",
            "relationships",
            "instructions",
            "reads",
            "gates",
            "conflicts",
            "fulfilled_obligations",
        ):
            value = resolved_graph_diff.get(key)
            result[key] = dict(value) if isinstance(value, Mapping) else {}
    return result


def merge_packet_delta(
    packet: Packet,
    packet_delta: Packet,
    *,
    next_gates: list[str],
) -> Packet:
    merged = dict(packet)
    activated = _string_list(packet_delta.get("activated_atoms"))
    deactivated = set(
        _string_list(packet_delta.get("deactivated_atoms"))
        + _string_list(packet_delta.get("stale_atoms"))
    )
    active_atoms = [
        atom
        for atom in _ordered_unique(
            _string_list(merged.get("active_atoms")) + activated
        )
        if atom not in deactivated
    ]
    deferred_atoms = _ordered_unique(
        [
            atom
            for atom in _string_list(merged.get("deferred_atoms"))
            if atom not in active_atoms
        ]
        + [atom for atom in deactivated if atom not in active_atoms]
    )
    required_reads = _ordered_unique(
        _string_list(merged.get("required_reads"))
        + _string_list(packet_delta.get("newly_required_reads"))
    )
    verification_gates = _ordered_unique(
        _string_list(merged.get("verification_gates")) + next_gates
    )
    family_context = dict(merged.get("family_context") or {})
    delta_family_context = packet_delta.get("family_context")
    if isinstance(delta_family_context, dict) and delta_family_context:
        family_context.update(delta_family_context)
    suggested_phase = str(packet_delta.get("suggested_phase") or "").strip()
    if suggested_phase:
        merged["phase"] = suggested_phase
    merged["active_atoms"] = active_atoms[:16]
    merged["deferred_atoms"] = deferred_atoms[:8]
    merged["required_reads"] = required_reads[:12]
    merged["verification_gates"] = verification_gates[:10]
    merged["family_context"] = family_context
    return merged


def apply_validated_proposals(
    packet: Packet, validated_changes: list[Packet]
) -> Packet:
    if not validated_changes:
        return packet
    task_identity = dict(packet.get("task_identity") or {})
    active_routes = _string_list(task_identity.get("active_routes"))
    for change in validated_changes:
        action = str(change.get("action") or "")
        if action == "add_route":
            route = str(change.get("route") or "")
            if route and route not in active_routes:
                active_routes.append(route)
    task_identity["active_routes"] = active_routes
    secondary = _string_list(task_identity.get("secondary"))
    for route in active_routes:
        if route != task_identity.get("primary") and route not in secondary:
            secondary.append(route)
    task_identity["secondary"] = secondary[:6]
    packet["task_identity"] = task_identity
    return packet


def render_recompiled_packet_markdown(
    recompiled: Packet,
    *,
    compose_markdown: ComposeMarkdown,
) -> str:
    packet = recompiled.get("packet")
    if not isinstance(packet, dict):
        return ""
    lines = [
        "## Recompile",
        f"Reason: {recompiled.get('recompile_reason', '')}",
        f"Detail: {recompiled.get('recompile_detail', '')}",
    ]
    packet_delta = recompiled.get("packet_diff")
    if isinstance(packet_delta, dict):
        dropped = [
            item
            for item in _json_list(packet_delta.get("dropped"))
            if isinstance(item, dict)
        ]
        added = [
            item
            for item in _json_list(packet_delta.get("added"))
            if isinstance(item, dict)
        ]
        if dropped:
            lines.extend(["", "### Dropped"])
            for item in dropped:
                lines.append(
                    f"- {item.get('kind', 'item')}: {item.get('id', '')} ({item.get('reason', '')})"
                )
        if added:
            lines.extend(["", "### Added"])
            for item in added:
                lines.append(
                    f"- {item.get('kind', 'item')}: {item.get('id', '')} ({item.get('reason', '')})"
                )
    base_markdown = compose_markdown(packet)
    return base_markdown.replace(
        "# TMCP Packet\n",
        "# TMCP Packet\n" + "\n".join(lines) + "\n",
        1,
    )
