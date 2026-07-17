"""In-memory recompiled-packet finalization over adapter-composed packets."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from tmcp_runtime.domain.composition_runtime import advance_composition_runtime
from tmcp_runtime.domain.harvest_nodes import (
    json_list,
    node_source_role,
    ordered_unique,
    source_role_is_activation_eligible,
    string_list,
)
from tmcp_runtime.domain.packets import render_composed_packet_markdown
from tmcp_runtime.domain.recompile import (
    apply_validated_proposals,
    merge_packet_delta,
    packet_diff,
    recompile_detail,
    render_recompiled_packet_markdown,
    resolve_recompile_reason,
)
from tmcp_runtime.services.compose import (
    active_instructions_for_source_node,
    enrich_packet_from_source_nodes,
)
from tmcp_runtime.services.semantic_compose import apply_semantic_composition


RECOMPILED_PACKET_SCHEMA = "tmcp-recompiled-packet-v0.1"
_RUNTIME_CONTINUITY_FIELDS = (
    "handoff_results",
    "available_handoff_ids",
    "fulfilled_obligations",
    "files_read",
    "files_changed",
    "commands_run",
    "browser_evidence_count",
    "runtime_observations",
)


def _graph_digest(plan: Mapping[str, Any]) -> str:
    provenance = plan.get("provenance")
    if not isinstance(provenance, Mapping):
        return ""
    return str(provenance.get("graph_digest") or "")


def _carry_compatible_runtime_evidence(
    plan: dict[str, Any], prior_plan: Mapping[str, Any] | None
) -> list[str]:
    """Carry verified runtime evidence only across an identical source graph."""

    graph_digest = _graph_digest(plan)
    if (
        prior_plan is None
        or not graph_digest
        or graph_digest != _graph_digest(prior_plan)
    ):
        return []
    prior_state = prior_plan.get("runtime_state")
    if not isinstance(prior_state, Mapping):
        return []
    carried = {
        field: deepcopy(prior_state[field])
        for field in _RUNTIME_CONTINUITY_FIELDS
        if field in prior_state
    }
    if carried:
        plan["runtime_state"] = carried
    return sorted(carried)


def _role_source_citation(
    role: Mapping[str, Any], packet: Mapping[str, Any]
) -> dict[str, Any]:
    role_citations = sorted(string_list(role.get("citations")))
    if not role_citations:
        return {}
    for item in json_list(packet.get("evidence_citations")):
        if not isinstance(item, Mapping):
            continue
        if sorted(string_list(item.get("relationship_citations"))) == role_citations:
            return dict(item)
    return {}


def _bind_runtime_plan_sources(
    plan: Mapping[str, Any],
    source_nodes: list[dict[str, Any]],
    packet: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id = {str(node.get("id") or ""): node for node in source_nodes}
    by_path = {
        str(node.get("relative_path") or node.get("path") or ""): node
        for node in source_nodes
    }
    bound_nodes = list(source_nodes)
    issues: list[dict[str, Any]] = []
    for role in json_list(plan.get("skill_roles")):
        if not isinstance(role, Mapping):
            continue
        node_id = str(role.get("node_id") or "")
        citation = _role_source_citation(role, packet)
        expected_digest = str(citation.get("content_digest") or "")
        expected_path = str(citation.get("source") or citation.get("path") or "")
        expected_role = str(
            citation.get("source_role") or role.get("source_role") or ""
        )
        exact = by_id.get(node_id)
        if exact is not None:
            actual_digest = str(exact.get("content_digest") or "")
            actual_role = node_source_role(exact)
            if expected_digest and actual_digest != expected_digest:
                issues.append(
                    {
                        "code": "composition_source_content_changed",
                        "node_id": node_id,
                        "source": expected_path,
                        "expected_content_digest": expected_digest,
                        "actual_content_digest": actual_digest,
                    }
                )
            if expected_role and actual_role != expected_role:
                issues.append(
                    {
                        "code": "composition_source_role_changed",
                        "node_id": node_id,
                        "source": expected_path,
                        "expected_source_role": expected_role,
                        "actual_source_role": actual_role,
                    }
                )
            continue
        digest_matches = [
            node
            for node in source_nodes
            if expected_digest
            and str(node.get("content_digest") or "") == expected_digest
            and (not expected_role or node_source_role(node) == expected_role)
        ]
        path_match = by_path.get(expected_path)
        if path_match is not None and path_match in digest_matches:
            digest_matches = [path_match]
        if len(digest_matches) == 1:
            alias = dict(digest_matches[0])
            alias["id"] = node_id
            bound_nodes.append(alias)
            continue
        if len(digest_matches) > 1:
            issues.append(
                {
                    "code": "composition_source_rebind_ambiguous",
                    "node_id": node_id,
                    "source": expected_path,
                    "expected_content_digest": expected_digest,
                }
            )
            continue
        if path_match is not None:
            issues.append(
                {
                    "code": "composition_source_content_changed",
                    "node_id": node_id,
                    "source": expected_path,
                    "expected_content_digest": expected_digest,
                    "actual_content_digest": path_match.get("content_digest"),
                }
            )
            continue
        issues.append(
            {
                "code": "composition_source_unavailable",
                "node_id": node_id,
                "source": expected_path,
                "expected_content_digest": expected_digest,
            }
        )
    return bound_nodes, issues


def _reject_stale_runtime_plan(
    packet: dict[str, Any],
    *,
    plan: dict[str, Any],
    issues: list[dict[str, Any]],
    metadata_packet: Mapping[str, Any],
) -> dict[str, Any]:
    rejected = dict(packet)
    for key in ("composition_diagnostics", "semantic_proposal_validation"):
        value = metadata_packet.get(key)
        if isinstance(value, Mapping):
            rejected[key] = dict(value)
    diagnostics = rejected.get("composition_diagnostics")
    diagnostic_map = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
    diagnostic_map["runtime_source_validation"] = {
        "accepted": False,
        "errors": issues,
        "required_action": "Prepare and submit a fresh semantic proposal.",
    }
    rejected["ok"] = False
    rejected["composition_plan"] = plan
    rejected["composition_plan_status"] = "stale_source_provenance"
    rejected["composition_diagnostics"] = diagnostic_map
    rejected["deferred_atoms"] = ordered_unique(
        string_list(rejected.get("active_atoms"))
        + string_list(rejected.get("deferred_atoms"))
    )
    rejected["active_atoms"] = []
    rejected["active_instructions"] = []
    rejected["tool_script_prompts"] = []
    rejected["stop_conditions"] = []
    rejected["verification_gates"] = [
        "Prepare a fresh semantic proposal from the current source content."
    ]
    receipt = rejected.get("receipt_template")
    if isinstance(receipt, dict):
        rejected["receipt_template"] = {**receipt, "activated_atoms": []}
    shortcut = rejected.get("shortcut_candidate")
    shortcut_map = dict(shortcut) if isinstance(shortcut, Mapping) else {}
    shortcut_map.update(
        {
            "status": "ineligible",
            "matched": False,
            "reason": "Composition source provenance changed; fresh preparation is required.",
        }
    )
    rejected["shortcut_candidate"] = shortcut_map
    return rejected


def _runtime_preflight(
    plan: Mapping[str, Any],
    source_nodes: list[dict[str, Any]],
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    diagnostics = packet.get("composition_diagnostics")
    diagnostic_map = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
    preflight_diagnostics = diagnostic_map.get("preflight")
    return {
        "preflight_id": plan.get("preflight_id"),
        "candidate_source_slices": [
            {
                "source_node_id": node.get("id"),
                "relative_path": node.get("relative_path") or node.get("path"),
            }
            for node in source_nodes
            if node.get("id")
        ],
        "diagnostics": (
            dict(preflight_diagnostics)
            if isinstance(preflight_diagnostics, Mapping)
            else {}
        ),
    }


def _apply_runtime_plan(
    packet: dict[str, Any],
    *,
    plan: dict[str, Any],
    source_nodes: list[dict[str, Any]],
    metadata_packet: Mapping[str, Any],
) -> dict[str, Any]:
    for key in ("composition_diagnostics", "semantic_proposal_validation"):
        value = metadata_packet.get(key)
        if isinstance(value, Mapping):
            packet[key] = dict(value)
    packet["phase"] = str(plan.get("current_phase") or packet.get("phase") or "start")
    validation = packet.get("semantic_proposal_validation")
    validation_map = dict(validation) if isinstance(validation, Mapping) else {}
    return apply_semantic_composition(
        packet,
        source_nodes=source_nodes,
        preflight=_runtime_preflight(plan, source_nodes, metadata_packet),
        compiled={
            "accepted": True,
            "composition_plan": plan,
            "validation": {
                "warnings": json_list(validation_map.get("warnings")),
            },
        },
        instruction_builder=active_instructions_for_source_node,
    )


def _apply_runtime_metadata(
    packet: dict[str, Any], composition_runtime: Mapping[str, Any]
) -> None:
    public_runtime = {
        key: value
        for key, value in composition_runtime.items()
        if key != "composition_plan"
    }
    packet["composition_runtime"] = public_runtime
    diagnostics = packet.get("composition_diagnostics")
    diagnostic_map = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
    diagnostic_map["runtime"] = {
        "phase_advance": composition_runtime.get("phase_advance") or {},
        "gate_evaluation": composition_runtime.get("gate_evaluation") or {},
        "handoff_evaluation": composition_runtime.get("handoff_evaluation") or {},
        "warnings": composition_runtime.get("warnings") or [],
    }
    packet["composition_diagnostics"] = diagnostic_map
    phase_advance = composition_runtime.get("phase_advance")
    phase_map = dict(phase_advance) if isinstance(phase_advance, Mapping) else {}
    required_gate_ids = set(string_list(phase_map.get("pending_gate_ids")))
    gate_evaluation = composition_runtime.get("gate_evaluation")
    gate_map = dict(gate_evaluation) if isinstance(gate_evaluation, Mapping) else {}
    required_gate_names = [
        str(item.get("name") or "")
        for item in json_list(gate_map.get("catalog"))
        if isinstance(item, Mapping)
        and str(item.get("gate_id") or "") in required_gate_ids
    ]
    required_handoff_ids = set(string_list(phase_map.get("pending_handoff_ids")))
    handoff_evaluation = composition_runtime.get("handoff_evaluation")
    handoff_map = (
        dict(handoff_evaluation) if isinstance(handoff_evaluation, Mapping) else {}
    )
    required_handoff_names = [
        "Receive typed handoff from "
        + str(item.get("producer_node_id") or "producer")
        + " to "
        + str(item.get("consumer_node_id") or "consumer")
        for item in json_list(handoff_map.get("catalog"))
        if isinstance(item, Mapping)
        and str(item.get("handoff_id") or "") in required_handoff_ids
    ]
    packet["verification_gates"] = ordered_unique(
        string_list(packet.get("verification_gates"))
        + required_gate_names
        + required_handoff_names
    )[:16]
    receipt = packet.get("receipt_template")
    if not isinstance(receipt, dict):
        return
    receipt["phase_trace"] = [
        dict(item)
        for item in json_list(composition_runtime.get("phase_trace"))
        if isinstance(item, Mapping)
    ]
    receipt["gate_results"] = [
        dict(item)
        for item in json_list(gate_map.get("evaluated_gates"))
        if isinstance(item, Mapping)
    ]
    receipt["handoff_results"] = [
        dict(item)
        for item in json_list(handoff_map.get("evaluated_handoffs"))
        if isinstance(item, Mapping)
    ]
    plan = composition_runtime.get("composition_plan")
    plan_map = dict(plan) if isinstance(plan, Mapping) else {}
    runtime_state = plan_map.get("runtime_state")
    state_map = dict(runtime_state) if isinstance(runtime_state, Mapping) else {}
    receipt["commands_run"] = string_list(state_map.get("commands_run"))
    observations = [
        item
        for item in json_list(composition_runtime.get("runtime_observations"))
        if isinstance(item, Mapping)
    ]
    receipt["verification_results"] = [
        str(item.get("summary") or "")
        for item in observations
        if item.get("kind") == "verification_results" and item.get("summary")
    ]
    receipt["user_overrides"] = [
        str(item.get("summary") or "")
        for item in observations
        if item.get("kind") == "user_overrides" and item.get("summary")
    ]


def finalize_recompiled_packet(
    arguments: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    previous_packet: dict[str, Any],
    composed_packet: dict[str, Any],
    previous_packet_id: str | None,
) -> dict[str, Any]:
    """Finalize a full recompile without reading, writing, or redacting data."""

    packet_delta = dict(state.get("packet_delta") or {})
    next_gates = string_list(state.get("next_verification_gate"))
    semantic_proposal_supplied = bool(state.get("semantic_proposal_supplied"))
    new_packet = (
        dict(composed_packet)
        if semantic_proposal_supplied
        else merge_packet_delta(
            composed_packet,
            packet_delta,
            next_gates=next_gates,
        )
    )
    source_nodes = [
        item for item in json_list(state.get("source_nodes")) if isinstance(item, dict)
    ]
    if not semantic_proposal_supplied:
        new_packet = enrich_packet_from_source_nodes(
            new_packet,
            source_nodes,
            string_list(packet_delta.get("newly_required_reads")),
        )
    composition_runtime = state.get("composition_runtime")
    runtime_map = (
        dict(composition_runtime) if isinstance(composition_runtime, Mapping) else None
    )
    if semantic_proposal_supplied:
        prior_runtime_map = runtime_map
        composed_plan = new_packet.get("composition_plan")
        if isinstance(composed_plan, Mapping):
            composed_plan = deepcopy(dict(composed_plan))
            new_packet["composition_plan"] = composed_plan
            runtime_evidence = state.get("runtime_evidence")
            evidence_map = (
                dict(runtime_evidence) if isinstance(runtime_evidence, Mapping) else {}
            )
            evidence_map["requested_phase"] = ""
            prior_plan = (
                prior_runtime_map.get("composition_plan")
                if isinstance(prior_runtime_map, Mapping)
                else None
            )
            carried_fields = _carry_compatible_runtime_evidence(
                composed_plan,
                prior_plan if isinstance(prior_plan, Mapping) else None,
            )
            runtime_map = advance_composition_runtime(composed_plan, evidence_map)
            if carried_fields:
                runtime_map["continuity"] = {
                    "graph_digest": _graph_digest(composed_plan),
                    "carried_fields": carried_fields,
                }
            if prior_runtime_map is not None:
                prior_public = {
                    key: value
                    for key, value in prior_runtime_map.items()
                    if key != "composition_plan"
                }
                runtime_map["prior_graph_transition"] = prior_public
                runtime_map["phase_advance"] = dict(
                    prior_runtime_map.get("phase_advance") or {}
                )
                combined_trace = [
                    item
                    for item in json_list(prior_runtime_map.get("phase_trace"))
                    if isinstance(item, Mapping)
                ] + [
                    item
                    for item in json_list(runtime_map.get("phase_trace"))
                    if isinstance(item, Mapping)
                ]
                runtime_map["phase_trace"] = combined_trace[-50:]
                runtime_map["warnings"] = ordered_unique(
                    string_list(prior_runtime_map.get("warnings"))
                    + string_list(runtime_map.get("warnings"))
                )
                runtime_plan = runtime_map.get("composition_plan")
                if isinstance(runtime_plan, dict):
                    runtime_state = runtime_plan.get("runtime_state")
                    if isinstance(runtime_state, dict):
                        runtime_state["phase_trace"] = runtime_map["phase_trace"]
    if runtime_map is not None:
        runtime_plan = runtime_map.get("composition_plan")
        if isinstance(runtime_plan, dict):
            metadata_packet = (
                composed_packet if semantic_proposal_supplied else previous_packet
            )
            bound_nodes, source_issues = _bind_runtime_plan_sources(
                runtime_plan,
                source_nodes,
                metadata_packet,
            )
            if source_issues:
                new_packet = _reject_stale_runtime_plan(
                    new_packet,
                    plan=runtime_plan,
                    issues=source_issues,
                    metadata_packet=metadata_packet,
                )
            else:
                new_packet = _apply_runtime_plan(
                    new_packet,
                    plan=runtime_plan,
                    source_nodes=bound_nodes,
                    metadata_packet=metadata_packet,
                )
                supporting_nodes = [
                    node
                    for node in source_nodes
                    if not source_role_is_activation_eligible(node_source_role(node))
                ]
                plan_state = runtime_plan.get("runtime_state")
                plan_state_map = (
                    dict(plan_state) if isinstance(plan_state, Mapping) else {}
                )
                supporting_reads = string_list(
                    packet_delta.get("newly_required_reads")
                ) + string_list(plan_state_map.get("files_read"))
                new_packet = enrich_packet_from_source_nodes(
                    new_packet,
                    supporting_nodes,
                    supporting_reads,
                )
            _apply_runtime_metadata(new_packet, runtime_map)
    runtime_identity = state.get("task_identity")
    if isinstance(runtime_identity, dict):
        new_packet["task_identity"] = dict(runtime_identity)
    new_packet = apply_validated_proposals(
        new_packet,
        [
            item
            for item in json_list(state.get("validated_changes"))
            if isinstance(item, dict)
        ],
    )
    receipt = new_packet.get("receipt_template")
    if isinstance(receipt, dict) and isinstance(new_packet.get("task_identity"), dict):
        receipt["task_identity"] = dict(new_packet["task_identity"])
    recompile_reason = resolve_recompile_reason(
        dict(arguments),
        dict(state),
    )
    packet_change = packet_diff(
        previous_packet,
        new_packet,
        packet_delta=packet_delta,
        recompile_reason=recompile_reason,
        graph_diff=(runtime_map.get("graph_diff") if runtime_map is not None else None),
        merge_graph_runtime=semantic_proposal_supplied,
    )
    recompiled = {
        "ok": bool(new_packet.get("ok", True)),
        "schema": RECOMPILED_PACKET_SCHEMA,
        "previous_packet_id": previous_packet_id or None,
        "recompile_reason": recompile_reason,
        "recompile_detail": recompile_detail(recompile_reason),
        "packet": new_packet,
        "packet_diff": packet_change,
        "agent_proposals": state.get("proposed_changes") or [],
        "validated_changes": state.get("validated_changes") or [],
        "suggested_phase": state.get("suggested_phase") or "",
        "task_identity": new_packet.get("task_identity"),
        "task_identity_delta": state.get("task_identity_delta"),
        "composition_runtime": (
            {
                key: value
                for key, value in runtime_map.items()
                if key != "composition_plan"
            }
            if runtime_map is not None
            else None
        ),
        "warnings": state.get("warnings") or [],
        "safety": {
            "stateless": True,
            "cache_trust": "advisory_untrusted",
            "instruction_override_policy": (
                "Recompiled packets never override system, developer, user, or project instructions."
            ),
        },
    }
    new_packet["packet_markdown"] = render_recompiled_packet_markdown(
        recompiled,
        compose_markdown=render_composed_packet_markdown,
    )
    recompiled["packet"] = new_packet
    return recompiled
