"""Pure runtime-state reduction over adapter-supplied safe inputs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from tmcp_runtime.domain.composition import (
    contextual_atoms_and_gates,
    validate_project_recipe_cache_policy,
)
from tmcp_runtime.domain.composition_runtime import advance_composition_runtime
from tmcp_runtime.domain.composition_runtime_capsules import (
    packet_has_runtime_capsule_provenance,
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


_REDIRECT_PATTERNS = (
    re.compile(r"\b(?:new|different)\s+(?:goal|task|objective|request|direction)\b", re.I),
    re.compile(r"\b(?:switch|pivot|redirect|move)\s+(?:to|away\s+from)\b", re.I),
    re.compile(r"\b(?:rather\s+than|instead\s+of)\b", re.I),
    re.compile(r"^\s*actually[,\s]+[^.?!]{0,240}\binstead\b", re.I),
    re.compile(
        r"^\s*(?:actually|instead)[,\s]+(?:i|we|let['’]?s|please|want|need|focus|work|do|make|change|start)\b",
        re.I,
    ),
)


def _has_likely_user_redirect(message: str) -> bool:
    """Detect directive-shaped redirects without treating ordinary wording as one."""

    return any(pattern.search(message) is not None for pattern in _REDIRECT_PATTERNS)


def _reported_phase_is_forward_request(
    plan: Mapping[str, Any] | None,
    *,
    current_phase: str,
    reported_phase: str,
) -> bool:
    """Treat a stale `current_phase` as state, not an implicit rollback request."""

    if not isinstance(plan, Mapping) or not reported_phase or reported_phase == current_phase:
        return False
    stages = [
        item
        for item in json_list(plan.get("ordered_stages"))
        if isinstance(item, Mapping)
    ]
    current_indexes = [
        index for index, stage in enumerate(stages) if stage.get("phase") == current_phase
    ]
    reported_indexes = [
        index for index, stage in enumerate(stages) if stage.get("phase") == reported_phase
    ]
    return bool(current_indexes and reported_indexes and max(reported_indexes) > max(current_indexes))


def _composition_recompile_policy(
    previous_packet: Mapping[str, Any] | None,
    previous_plan: Mapping[str, Any] | None,
    *,
    semantic_proposal_supplied: bool,
    has_explicit_user_redirect: bool,
    latest_user_message: str,
    task_identity_delta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Decide whether a persisted semantic graph may be reused safely."""

    protected_plan = isinstance(previous_packet, Mapping) and (
        packet_has_runtime_capsule_provenance(
            previous_packet,
            plan=previous_plan,
        )
    )
    runtime_capsule_present = isinstance(previous_plan, Mapping) and isinstance(
        previous_plan.get("runtime_capsule"), Mapping
    )
    legacy_unbound_graph = (
        isinstance(previous_plan, Mapping)
        and previous_plan.get("schema") == "tmcp-composition-plan-v0.1"
        and not protected_plan
    )
    heuristic_redirect = _has_likely_user_redirect(latest_user_message)
    material_identity_shift = isinstance(task_identity_delta, Mapping) and any(
        bool(task_identity_delta.get(field))
        for field in (
            "changed_routes",
            "changed_facets",
            "changed_validated_routes",
            "routing_status_changed",
        )
    )
    reason = (
        "user_redirect"
        if has_explicit_user_redirect or heuristic_redirect
        else "task_identity_shift"
        if material_identity_shift
        else ""
    )
    return {
        "schema": "tmcp-composition-recompile-policy-v0.1",
        "protected_plan": protected_plan,
        "runtime_capsule_present": runtime_capsule_present,
        "legacy_unbound_graph": legacy_unbound_graph,
        "legacy_unbound_graph_requires_fresh_composition": bool(
            legacy_unbound_graph and not semantic_proposal_supplied
        ),
        "requires_fresh_composition": bool(protected_plan and reason),
        "fresh_composition_supplied": semantic_proposal_supplied,
        "reason": reason,
        "required_action": (
            "Prepare current sources and submit a fresh semantic proposal or reviewed project recipe."
            if protected_plan and reason
            else ""
        ),
    }


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
    cache_policy = validate_project_recipe_cache_policy(
        cache_policy=arguments.get("cache_policy"),
        project_recipe_id=arguments.get("project_recipe_id"),
    )
    latest_user_message = str(arguments.get("latest_user_message") or "")
    previous_packet = parse_previous_packet(dict(arguments))
    previous_plan = (
        previous_packet.get("composition_plan")
        if isinstance(previous_packet, dict)
        else None
    )
    legacy_unbound_graph = (
        isinstance(previous_plan, Mapping)
        and previous_plan.get("schema") == "tmcp-composition-plan-v0.1"
        and not packet_has_runtime_capsule_provenance(
            previous_packet if isinstance(previous_packet, Mapping) else {},
            plan=previous_plan,
        )
    )
    semantic_proposal_supplied = isinstance(
        arguments.get("semantic_proposal"), Mapping
    ) or bool(str(arguments.get("project_recipe_id") or "").strip())
    if isinstance(previous_plan, Mapping) and not legacy_unbound_graph:
        plan_phase = str(previous_plan.get("current_phase") or "")
        if plan_phase:
            phase = plan_phase
    files_read = string_list(arguments.get("files_read"))
    files_changed = string_list(arguments.get("files_changed"))
    commands_run = string_list(arguments.get("commands_run"))
    failures = string_list(arguments.get("failures"))
    browser_evidence = string_list(arguments.get("browser_evidence"))
    handoff_results = arguments.get("handoff_results") or []
    user_redirect = arguments.get("user_redirect")
    context = {
        "files_read": files_read,
        "files_changed": files_changed,
        "commands_run": commands_run,
        "verification_results": arguments.get("verification_results") or [],
        "gate_results": arguments.get("gate_results") or [],
        "failures": failures,
        "browser_evidence": browser_evidence,
        "handoff_results": handoff_results,
        "user_redirect": user_redirect,
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
            if "current_phase" in arguments
            and _reported_phase_is_forward_request(
                previous_plan if isinstance(previous_plan, Mapping) else None,
                current_phase=phase,
                reported_phase=reported_phase,
            )
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
        "handoff_results": handoff_results,
        "user_overrides": arguments.get("user_overrides"),
        "user_redirect": user_redirect,
        "latest_user_message": latest_user_message,
        "requested_phase": requested_phase,
    }
    composition_runtime: dict[str, Any] | None = None
    if isinstance(previous_plan, Mapping) and not legacy_unbound_graph:
        try:
            composition_runtime = advance_composition_runtime(
                previous_plan,
                runtime_evidence,
            )
        except (IndexError, TypeError, ValueError):
            if not packet_has_runtime_capsule_provenance(
                previous_packet if isinstance(previous_packet, Mapping) else {},
                plan=previous_plan,
            ):
                raise
            # Defer malformed capsule plans to the recompile finalizer so it can
            # emit the established inert recovery packet instead of crashing.
            composition_runtime = {
                "composition_plan": None,
                "current_phase": phase,
                "graph_diff": {},
                "gate_evaluation": {},
                "phase_advance": {
                    "blocked_reason": "runtime_capsule_validation_pending"
                },
                "warnings": [
                    "Composition runtime state is malformed and must be revalidated."
                ],
            }
    elif legacy_unbound_graph:
        warnings.append(
            "An unbound legacy composition graph requires a fresh semantic proposal."
        )
    has_explicit_user_redirect = bool(
        (isinstance(user_redirect, Mapping) and user_redirect)
        or (isinstance(user_redirect, str) and user_redirect.strip())
    )
    if has_explicit_user_redirect or _has_likely_user_redirect(latest_user_message):
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
        if has_explicit_user_redirect or _has_likely_user_redirect(latest_user_message):
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
    composition_recompile_policy = _composition_recompile_policy(
        previous_packet if isinstance(previous_packet, Mapping) else None,
        previous_plan if isinstance(previous_plan, Mapping) else None,
        semantic_proposal_supplied=semantic_proposal_supplied,
        has_explicit_user_redirect=has_explicit_user_redirect,
        latest_user_message=latest_user_message,
        task_identity_delta=identity_delta,
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
        "composition_recompile_policy": composition_recompile_policy,
        "packet_delta": packet_delta,
        "next_verification_gate": next_gates,
        "warnings": ordered_unique(warnings),
        "proposed_changes": proposed_changes,
        "validated_changes": validated_changes,
    }
