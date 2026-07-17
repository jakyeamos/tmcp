"""Pure runtime-state reduction over adapter-supplied safe inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tmcp_runtime.domain.composition import (
    contextual_atoms_and_gates,
    normalize_cache_policy,
)
from tmcp_runtime.domain.composition_runtime import advance_composition_runtime
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
    reported_phase = phase
    cache_policy = normalize_cache_policy(arguments.get("cache_policy"))
    latest_user_message = str(arguments.get("latest_user_message") or "")
    previous_packet = parse_previous_packet(dict(arguments))
    previous_plan = (
        previous_packet.get("composition_plan")
        if isinstance(previous_packet, dict)
        else None
    )
    semantic_proposal_supplied = isinstance(
        arguments.get("semantic_proposal"), Mapping
    ) or bool(str(arguments.get("project_recipe_id") or "").strip())
    if isinstance(previous_plan, Mapping):
        plan_phase = str(previous_plan.get("current_phase") or "")
        if plan_phase:
            phase = plan_phase
    files_read = string_list(arguments.get("files_read"))
    files_changed = string_list(arguments.get("files_changed"))
    commands_run = string_list(arguments.get("commands_run"))
    failures = string_list(arguments.get("failures"))
    browser_evidence = string_list(arguments.get("browser_evidence"))
    context = {
        "files_read": files_read,
        "files_changed": files_changed,
        "commands_run": commands_run,
        "verification_results": arguments.get("verification_results") or [],
        "gate_results": arguments.get("gate_results") or [],
        "failures": failures,
        "browser_evidence": browser_evidence,
        "user_overrides": arguments.get("user_overrides") or [],
    }
    combined_objective = " ".join(
        part for part in (objective, latest_user_message) if part
    ).strip()
    activated_atoms, newly_required_reads, next_gates = contextual_atoms_and_gates(
        combined_objective, phase, context
    )
    contextual_atoms = list(activated_atoms)
    contextual_reads = list(newly_required_reads)
    contextual_gates = list(next_gates)
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
    proposal = arguments.get("semantic_proposal")
    proposal_phase = (
        str(proposal.get("current_phase") or "")
        if isinstance(proposal, Mapping)
        else ""
    )
    requested_phase = str(
        arguments.get("requested_phase")
        or (
            reported_phase
            if "current_phase" in arguments and reported_phase != phase
            else ""
        )
        or (proposal_phase if proposal_phase != phase else "")
        or suggested_phase
    )
    runtime_evidence = {
        "files_read": arguments.get("files_read"),
        "files_changed": arguments.get("files_changed"),
        "commands_run": arguments.get("commands_run"),
        "verification_results": arguments.get("verification_results"),
        "gate_results": arguments.get("gate_results"),
        "failures": arguments.get("failures"),
        "browser_evidence": arguments.get("browser_evidence"),
        "user_overrides": arguments.get("user_overrides"),
        "latest_user_message": latest_user_message,
        "requested_phase": requested_phase,
    }
    composition_runtime: dict[str, Any] | None = None
    if isinstance(previous_plan, Mapping):
        composition_runtime = advance_composition_runtime(
            previous_plan,
            runtime_evidence,
        )
        graph_diff = dict(composition_runtime.get("graph_diff") or {})
        skill_diff = dict(graph_diff.get("skills") or {})
        suggested_phase = str(composition_runtime.get("current_phase") or phase)
        if suggested_phase == phase:
            suggested_phase = ""
        activated_atoms = contextual_atoms
        newly_required_reads = contextual_reads
        next_gates = contextual_gates
        stale_atoms = []
        gate_evaluation = dict(composition_runtime.get("gate_evaluation") or {})
        pending_gate_ids = set(string_list(gate_evaluation.get("pending_gate_ids")))
        current_stage_id = str(composition_runtime.get("current_stage_id") or "")
        next_gates = ordered_unique(
            next_gates
            + [
                str(gate.get("name") or "")
                for gate in json_list(gate_evaluation.get("catalog"))
                if isinstance(gate, dict)
                and str(gate.get("gate_id") or "") in pending_gate_ids
                and str(gate.get("owner_stage_id") or "") == current_stage_id
            ]
        )
        family_delta["suggested_skills"] = string_list(skill_diff.get("added"))
        family_delta["deferred_skills"] = string_list(skill_diff.get("deferred"))
        warnings.extend(string_list(composition_runtime.get("warnings")))
        phase_advance = dict(composition_runtime.get("phase_advance") or {})
        if phase_advance.get("blocked_reason"):
            warnings.append(
                "Composition phase advancement was blocked until its named gates pass."
            )
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
    identity_context: dict[str, Any] = dict(context)
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
        "runtime_evidence": runtime_evidence,
        "latest_user_message": latest_user_message,
        "source_nodes": source_nodes,
        "previous_composition_plan": previous_plan,
        "composition_runtime": composition_runtime,
        "semantic_proposal_supplied": semantic_proposal_supplied,
        "task_identity": current_task_identity,
        "task_identity_delta": identity_delta,
        "packet_delta": packet_delta,
        "next_verification_gate": next_gates,
        "warnings": ordered_unique(warnings),
        "proposed_changes": proposed_changes,
        "validated_changes": validated_changes,
    }
