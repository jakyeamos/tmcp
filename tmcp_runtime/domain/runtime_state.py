"""Pure runtime-state reduction over adapter-supplied safe inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tmcp_runtime.domain.composition import (
    contextual_atoms_and_gates,
    normalize_cache_policy,
)
from tmcp_runtime.domain.families import (
    runtime_family_packet_delta,
    runtime_family_seed_context,
)
from tmcp_runtime.domain.harvest_nodes import (
    json_list,
    node_signal_text,
    ordered_unique,
    string_list,
)
from tmcp_runtime.domain.recompile import parse_previous_packet
from tmcp_runtime.domain.routes import (
    derive_task_identity,
    task_identity_delta,
    validate_proposed_changes,
)


def derive_runtime_state(
    arguments: Mapping[str, Any],
    *,
    source_nodes: list[dict[str, Any]],
    cache_warnings: list[str],
) -> dict[str, Any]:
    """Derive runtime state without reading files, caches, or transport state."""

    objective = str(arguments.get("objective") or "").strip()
    if not objective:
        raise ValueError("tmcp_runtime_next requires objective.")
    phase = str(arguments.get("current_phase") or "start")
    cache_policy = normalize_cache_policy(arguments.get("cache_policy"))
    latest_user_message = str(arguments.get("latest_user_message") or "")
    files_changed = string_list(arguments.get("files_changed"))
    failures = string_list(arguments.get("failures"))
    browser_evidence = string_list(arguments.get("browser_evidence"))
    context = {
        "files_changed": files_changed,
        "failures": failures,
        "browser_evidence": browser_evidence,
    }
    combined_objective = " ".join(
        part for part in (objective, latest_user_message) if part
    ).strip()
    activated_atoms, newly_required_reads, next_gates = contextual_atoms_and_gates(
        combined_objective, phase, context
    )
    stale_atoms: list[str] = []
    warnings: list[str] = []
    family_delta: dict[str, Any] = {}
    family_context: dict[str, Any] | None = None
    suggested_phase = ""
    if source_nodes:
        family_context, seed_node = runtime_family_seed_context(
            source_nodes,
            combined_objective,
            phase,
            node_signal_text=node_signal_text,
        )
        family_delta = runtime_family_packet_delta(
            current_phase=phase,
            family_context=family_context,
            seed_node=seed_node,
            source_nodes=source_nodes,
            objective=combined_objective,
            context=context,
            latest_user_message=latest_user_message,
        )
        if family_delta:
            activated_atoms = ordered_unique(
                activated_atoms + string_list(family_delta.get("activated_atoms"))
            )
            newly_required_reads = ordered_unique(
                newly_required_reads
                + string_list(family_delta.get("newly_required_reads"))
            )
            next_gates = ordered_unique(
                next_gates + string_list(family_delta.get("verification_gates"))
            )
            stale_atoms = ordered_unique(
                stale_atoms + string_list(family_delta.get("deactivated_atoms"))
            )
            suggested_phase = str(family_delta.get("suggested_phase") or "")
    if any(
        term in latest_user_message.lower()
        for term in ("actually", "instead", "new goal", "different")
    ):
        stale_atoms.append("previous-objective-specific-atoms")
        warnings.append(
            "Latest user message may redirect the objective; stale atoms should be rechecked before use."
        )
    if cache_policy != "none":
        warnings.extend(cache_warnings)
    if not next_gates:
        next_gates.append("Read the next required source before changing behavior.")
    identity_context = dict(context)
    identity_context["latest_user_message"] = latest_user_message
    resolved_family_context = family_context
    if not resolved_family_context:
        packet_family_context = family_delta.get("family_context")
        if isinstance(packet_family_context, dict) and packet_family_context:
            resolved_family_context = packet_family_context
    current_task_identity = derive_task_identity(
        combined_objective,
        identity_context,
        resolved_family_context,
    )
    previous_task_identity = arguments.get("previous_task_identity")
    if not isinstance(previous_task_identity, dict):
        previous_packet = parse_previous_packet(dict(arguments))
        if isinstance(previous_packet, dict):
            previous_task_identity = previous_packet.get("task_identity")
    identity_delta: dict[str, Any] | None = None
    if isinstance(previous_task_identity, dict):
        delta_reason = "runtime_context_changed"
        if any(
            term in latest_user_message.lower()
            for term in ("actually", "instead", "new goal", "different")
        ):
            delta_reason = "user_redirect"
        elif suggested_phase:
            delta_reason = "phase_transition"
        elif files_changed:
            delta_reason = "implementation_phase_detected"
        identity_delta = task_identity_delta(
            previous_task_identity,
            current_task_identity,
            reason=delta_reason,
        )
    packet_delta = {
        "activated_atoms": activated_atoms,
        "deactivated_atoms": stale_atoms,
        "stale_atoms": stale_atoms,
        "newly_required_reads": newly_required_reads,
        "suggested_phase": suggested_phase,
        "suggested_skills": string_list(family_delta.get("suggested_skills")),
        "deferred_skills": string_list(family_delta.get("deferred_skills")),
        "family_context": family_delta.get("family_context", {}),
    }
    proposed_changes = [
        item
        for item in json_list(arguments.get("proposed_changes"))
        if isinstance(item, dict)
    ]
    validated_changes, proposal_warnings = validate_proposed_changes(proposed_changes)
    warnings.extend(proposal_warnings)
    return {
        "objective": objective,
        "combined_objective": combined_objective,
        "project_path": str(arguments.get("project_path") or "."),
        "phase": phase,
        "suggested_phase": suggested_phase,
        "cache_policy": cache_policy,
        "context": context,
        "latest_user_message": latest_user_message,
        "source_nodes": source_nodes,
        "task_identity": current_task_identity,
        "task_identity_delta": identity_delta,
        "packet_delta": packet_delta,
        "next_verification_gate": next_gates,
        "warnings": ordered_unique(warnings),
        "proposed_changes": proposed_changes,
        "validated_changes": validated_changes,
    }
