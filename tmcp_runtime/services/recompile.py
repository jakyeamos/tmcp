"""In-memory recompiled-packet finalization over adapter-composed packets."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from tmcp_runtime.domain.composition_planning import compile_semantic_composition
from tmcp_runtime.domain.composition_preflight import COMPOSITION_TRUST, stable_digest
from tmcp_runtime.domain.composition_runtime import advance_composition_runtime
from tmcp_runtime.domain.composition_runtime_capsules import (
    RUNTIME_CAPSULE_INVALID_PROVENANCE_STATUS,
    RUNTIME_CAPSULE_PROVENANCE_STATUS_FIELD,
    RuntimeCapsuleError,
    packet_has_runtime_capsule_provenance,
    rehydrate_runtime_capsule,
)
from tmcp_runtime.domain.composition_runtime_continuations import (
    RuntimeContinuationError,
    build_runtime_continuation,
    replay_runtime_continuation,
    runtime_evidence_is_meaningful,
    validate_runtime_continuation,
)
from tmcp_runtime.domain.host_composition_provenance import (
    host_composition_lineage_for_recompile,
    host_composition_receipt_provenance,
    validate_host_composition_lineage,
)
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
from tmcp_runtime.services.recompile_source_validation import (
    bind_runtime_plan_sources,
    reject_stale_runtime_plan,
)
from tmcp_runtime.services.sessions import has_session_runtime_continuation_trust


RECOMPILED_PACKET_SCHEMA = "tmcp-recompiled-packet-v0.1"


def _host_composition_plan(packet: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Locate the graph that can bind a historical host composition origin."""

    for field in ("composition_plan", "inert_composition_plan"):
        value = packet.get(field)
        if isinstance(value, Mapping):
            return value
    return None


def _validated_host_composition_lineage(
    packet: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, bool]:
    """Return only a closed, graph-bound host lineage from caller packet state."""

    raw = packet.get("host_composition")
    if not isinstance(raw, Mapping):
        return None, False
    try:
        return (
            validate_host_composition_lineage(
                raw,
                composition_plan=_host_composition_plan(packet),
            ),
            False,
        )
    except ValueError:
        return None, True


def _preflight_id(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    preflight_id = value.get("preflight_id")
    if not isinstance(preflight_id, str) or not preflight_id.strip():
        return None
    return preflight_id.strip()


def _attach_host_composition_lineage(
    packet: dict[str, Any],
    *,
    lineage: Mapping[str, Any],
    runtime_snapshot_status: str,
    current_preflight_id: str | None,
) -> None:
    """Retain the initial host origin as history after a runtime decision."""

    updated = host_composition_lineage_for_recompile(
        lineage,
        runtime_snapshot_status=runtime_snapshot_status,
        current_preflight_id=current_preflight_id,
        current_composition_plan=(
            packet.get("composition_plan")
            if isinstance(packet.get("composition_plan"), Mapping)
            else None
        ),
    )
    packet["host_composition"] = updated
    receipt = packet.get("receipt_template")
    if isinstance(receipt, Mapping):
        packet["receipt_template"] = {
            **dict(receipt),
            "host_composition_provenance": host_composition_receipt_provenance(
                updated
            ),
        }


def _omit_untrusted_host_composition_lineage(packet: dict[str, Any]) -> None:
    """Fail closed when caller-provided origin cannot bind to its prior graph."""

    packet.pop("host_composition", None)
    receipt = packet.get("receipt_template")
    if isinstance(receipt, Mapping):
        receipt_copy = dict(receipt)
        receipt_copy.pop("host_composition_provenance", None)
        packet["receipt_template"] = receipt_copy
    diagnostics = packet.get("composition_diagnostics")
    diagnostic_map = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
    diagnostic_map["host_composition_provenance"] = {
        "accepted": False,
        "status": "untrusted_or_unbound_origin_omitted",
    }
    packet["composition_diagnostics"] = diagnostic_map


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
    composition_preflight: Mapping[str, Any],
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
        preflight=composition_preflight,
        compiled={
            "accepted": True,
            "composition_plan": plan,
            "validation": {
                "warnings": json_list(validation_map.get("warnings")),
            },
        },
        instruction_builder=active_instructions_for_source_node,
    )


def _reject_runtime_reuse(
    packet: dict[str, Any],
    *,
    plan: Mapping[str, Any],
    status: str,
    issues: list[dict[str, Any]],
    required_action: str,
) -> dict[str, Any]:
    """Make a stale semantic plan inert while retaining it only for audit."""

    rejected = dict(packet)
    diagnostics = rejected.get("composition_diagnostics")
    diagnostic_map = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
    diagnostic_map["runtime_capsule_validation"] = {
        "accepted": False,
        "errors": issues,
        "required_action": required_action,
    }
    rejected["ok"] = False
    rejected["inert_composition_plan"] = deepcopy(dict(plan))
    rejected["composition_plan"] = None
    rejected["composition_plan_status"] = status
    if status in {
        "runtime_capsule_required",
        "runtime_capsule_invalid",
        "stale_source_provenance",
        "legacy_unbound_graph_requires_fresh_composition",
    }:
        rejected[RUNTIME_CAPSULE_PROVENANCE_STATUS_FIELD] = (
            RUNTIME_CAPSULE_INVALID_PROVENANCE_STATUS
        )
    rejected["composition_diagnostics"] = diagnostic_map
    rejected["deferred_atoms"] = ordered_unique(
        string_list(rejected.get("active_atoms"))
        + string_list(rejected.get("deferred_atoms"))
    )
    for field in (
        "active_atoms",
        "active_instructions",
        "required_reads",
        "tool_script_prompts",
        "stop_conditions",
    ):
        rejected[field] = []
    rejected["verification_gates"] = [required_action]
    receipt = rejected.get("receipt_template")
    if isinstance(receipt, Mapping):
        rejected["receipt_template"] = {**receipt, "activated_atoms": []}
    shortcut = rejected.get("shortcut_candidate")
    shortcut_map = dict(shortcut) if isinstance(shortcut, Mapping) else {}
    shortcut_map.update(
        {"status": "ineligible", "matched": False, "reason": required_action}
    )
    rejected["shortcut_candidate"] = shortcut_map
    return rejected


def _runtime_capsule_result(
    plan: Mapping[str, Any],
    *,
    composition_preflight: Mapping[str, Any] | None,
    source_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(composition_preflight, Mapping):
        return {
            "accepted": False,
            "issues": [{"code": "runtime_capsule_preflight_missing"}],
        }
    try:
        rehydrated = rehydrate_runtime_capsule(
            plan, composition_preflight, source_nodes
        )
    except RuntimeCapsuleError as exc:
        return {
            "accepted": False,
            "issues": [{"code": "runtime_capsule_invalid", "detail": str(exc)}],
        }
    if rehydrated.get("accepted") is not True:
        return rehydrated
    replay = _replay_runtime_capsule_plan(plan, rehydrated)
    if replay.get("accepted") is not True:
        return {
            "accepted": False,
            "issues": replay["issues"],
            "composition_preflight": None,
            "source_nodes": [],
            "aliases": [],
            "compiler_phase": "",
        }
    return {**rehydrated, "composition_plan": replay["composition_plan"]}


def _runtime_replay_proposal(
    plan: Mapping[str, Any], *, compiler_phase: str
) -> dict[str, Any]:
    """Project only compiler-owned semantic inputs from a persisted plan."""

    roles = [
        {
            field: deepcopy(role.get(field))
            for field in (
                "node_id",
                "role",
                "inputs",
                "outputs",
                "phase_affinity",
                "entry_gates",
                "exit_gates",
                "context_cost",
                "covers",
                "citations",
            )
        }
        for role in json_list(plan.get("skill_roles"))
        if isinstance(role, Mapping)
    ]
    relationships = [
        {
            field: deepcopy(edge.get(field))
            for field in ("from", "to", "type", "citations", "rationale")
        }
        for edge in json_list(plan.get("typed_edges"))
        if isinstance(edge, Mapping)
    ]
    coverage = plan.get("proposal_coverage")
    if not isinstance(coverage, Mapping):
        raise ValueError("runtime capsule lacks immutable proposal coverage.")
    coverage_map = dict(coverage)
    if any(
        not isinstance(coverage_map.get(field), list)
        or any(not isinstance(item, str) for item in coverage_map[field])
        for field in ("facets", "unresolved_gaps")
    ):
        raise ValueError("runtime capsule proposal coverage is malformed.")
    task_model = plan.get("task_model")
    return {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": str(plan.get("preflight_id") or ""),
        "current_phase": compiler_phase,
        "task_model": deepcopy(dict(task_model))
        if isinstance(task_model, Mapping)
        else {},
        "skill_roles": roles,
        "relationships": relationships,
        "coverage": {
            "facets": deepcopy(coverage_map.get("facets") or []),
            "unresolved_gaps": deepcopy(coverage_map.get("unresolved_gaps") or []),
        },
        "trust": COMPOSITION_TRUST,
    }


def _preflight_with_runtime_aliases(
    preflight: Mapping[str, Any], aliases: object
) -> dict[str, Any]:
    """Recreate original cited slice IDs for a permitted same-content rename."""

    replay = deepcopy(dict(preflight))
    alias_map = {
        str(item.get("from_node_id") or ""): str(item.get("to_node_id") or "")
        for item in json_list(aliases)
        if isinstance(item, Mapping)
        and str(item.get("from_node_id") or "")
        and str(item.get("to_node_id") or "")
    }
    slices = replay.get("candidate_source_slices")
    if not alias_map or not isinstance(slices, list):
        return replay
    for source_slice in slices:
        if not isinstance(source_slice, dict):
            continue
        original_node_id = alias_map.get(str(source_slice.get("source_node_id") or ""))
        if not original_node_id:
            continue
        source_slice["source_node_id"] = original_node_id
        source_slice["slice_id"] = "slice-" + stable_digest(
            [
                source_slice.get("source_digest"),
                source_slice.get("slice_digest"),
                source_slice.get("char_start"),
                source_slice.get("char_end"),
                original_node_id,
            ],
            20,
        )
    return replay


def _replay_runtime_capsule_plan(
    plan: Mapping[str, Any], rehydrated: Mapping[str, Any]
) -> dict[str, Any]:
    """Require source-rehydrated plans to equal a fresh compiler replay."""

    preflight = rehydrated.get("composition_preflight")
    compiler_phase = str(rehydrated.get("compiler_phase") or "")
    binding = plan.get("phase_capsule_binding")
    if (
        not isinstance(preflight, Mapping)
        or not compiler_phase
        or not isinstance(binding, Mapping)
    ):
        return {
            "accepted": False,
            "issues": [{"code": "runtime_capsule_compiler_replay_missing"}],
        }
    replay_preflight = _preflight_with_runtime_aliases(
        preflight, rehydrated.get("aliases")
    )
    try:
        replay = compile_semantic_composition(
            _runtime_replay_proposal(plan, compiler_phase=compiler_phase),
            replay_preflight,
            current_phase=compiler_phase,
        )
    except (TypeError, ValueError) as exc:
        return {
            "accepted": False,
            "issues": [
                {
                    "code": "runtime_capsule_compiler_replay_failed",
                    "detail": str(exc),
                }
            ],
        }
    replay_plan = replay.get("composition_plan")
    if not bool(replay.get("accepted")) or not isinstance(replay_plan, Mapping):
        return {
            "accepted": False,
            "issues": [
                {
                    "code": "runtime_capsule_compiler_replay_rejected",
                    "errors": json_list(dict(replay.get("validation") or {}).get("errors")),
                }
            ],
        }
    replay_binding = replay_plan.get("phase_capsule_binding")
    # A permitted same-content rename changes the runtime accounting envelope
    # (for example, its behavior-manifest locator) while leaving the compiler's
    # immutable graph and recipe identity intact.  The stored binding and
    # capsule were already independently validated by rehydration above; this
    # replay comparison therefore authenticates the compiler-owned graph, not
    # the location-derived accounting digest.
    if not isinstance(replay_binding, Mapping) or any(
        replay_binding.get(field) != binding.get(field)
        for field in (
            "composition_plan_id",
            "composition_plan_digest",
            "preflight_id",
            "compiler_phase",
            "graph_digest",
            "recipe_digest",
        )
    ):
        return {
            "accepted": False,
            "issues": [{"code": "runtime_capsule_compiler_replay_mismatch"}],
        }
    return {"accepted": True, "issues": [], "composition_plan": dict(replay_plan)}


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
    composition_preflight: Mapping[str, Any] | None = None,
    runtime_continuation_trust: object = None,
) -> dict[str, Any]:
    """Finalize a full recompile without reading, writing, or redacting data."""

    packet_delta = dict(state.get("packet_delta") or {})
    next_gates = string_list(state.get("next_verification_gate"))
    semantic_proposal_supplied = bool(state.get("semantic_proposal_supplied"))
    recompile_policy = state.get("composition_recompile_policy")
    policy_map = dict(recompile_policy) if isinstance(recompile_policy, Mapping) else {}
    requires_fresh_composition = bool(policy_map.get("requires_fresh_composition"))
    trusted_runtime_continuation = has_session_runtime_continuation_trust(
        runtime_continuation_trust
    )
    host_lineage, rejected_host_lineage = _validated_host_composition_lineage(
        previous_packet
    )
    host_runtime_status = "not_revalidated"
    host_current_preflight_id = _preflight_id(composition_preflight)
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
    semantic_validation = new_packet.get("semantic_proposal_validation")
    fresh_composition_rejected = semantic_proposal_supplied and (
        not isinstance(new_packet.get("composition_plan"), Mapping)
        or not isinstance(semantic_validation, Mapping)
        or semantic_validation.get("accepted") is not True
    )
    if fresh_composition_rejected:
        # An explicit fresh composition is authoritative.  Never let an older
        # capsule graph overwrite the compiler's rejected result.
        runtime_map = None
        host_runtime_status = "fresh_semantic_composition_rejected"
    elif semantic_proposal_supplied:
        host_runtime_status = "fresh_semantic_composition"
    if semantic_proposal_supplied and not fresh_composition_rejected:
        composed_plan = new_packet.get("composition_plan")
        if isinstance(composed_plan, Mapping):
            composed_plan = deepcopy(dict(composed_plan))
            new_packet["composition_plan"] = composed_plan
            runtime_evidence = state.get("runtime_evidence")
            evidence_map = (
                dict(runtime_evidence) if isinstance(runtime_evidence, Mapping) else {}
            )
            evidence_map["requested_phase"] = ""
            # A fresh proposal starts a fresh runtime evidence chain.  A packet's
            # prior runtime_state is agent-controlled input, not a trusted
            # checkpoint, so matching graph provenance is insufficient to carry
            # reads, commands, handoffs, or gate results into a new composition.
            runtime_map = advance_composition_runtime(composed_plan, evidence_map)
    runtime_plan = (
        runtime_map.get("composition_plan")
        if isinstance(runtime_map, Mapping)
        else None
    )
    previous_capsule_provenance = packet_has_runtime_capsule_provenance(
        previous_packet,
        plan=runtime_plan if isinstance(runtime_plan, Mapping) else None,
    )
    if (
        not semantic_proposal_supplied
        and previous_capsule_provenance
        and not isinstance(runtime_plan, Mapping)
    ):
        retained_plan = previous_packet.get("inert_composition_plan")
        if not isinstance(retained_plan, Mapping):
            retained_plan = previous_packet.get("composition_plan")
        new_packet = _reject_runtime_reuse(
            new_packet,
            plan=(retained_plan if isinstance(retained_plan, Mapping) else {}),
            status="runtime_capsule_required",
            issues=[{"code": "runtime_capsule_required"}],
            required_action=(
                "Prepare current sources and submit a fresh semantic proposal."
            ),
        )
        runtime_map = None
        host_runtime_status = "fresh_composition_required"
    elif (
        not semantic_proposal_supplied
        and policy_map.get("legacy_unbound_graph_requires_fresh_composition")
    ):
        legacy_plan = previous_packet.get("composition_plan")
        new_packet = _reject_runtime_reuse(
            new_packet,
            plan=legacy_plan if isinstance(legacy_plan, Mapping) else {},
            status="legacy_unbound_graph_requires_fresh_composition",
            issues=[{"code": "legacy_unbound_graph_requires_fresh_composition"}],
            required_action=(
                "Prepare current sources and submit a fresh semantic proposal."
            ),
        )
        runtime_map = None
        host_runtime_status = "fresh_composition_required"
    elif requires_fresh_composition and not semantic_proposal_supplied:
        prior_plan = previous_packet.get("composition_plan")
        if isinstance(prior_plan, Mapping):
            reason = str(policy_map.get("reason") or "task_identity_shift")
            status = (
                "redirect_requires_fresh_composition"
                if reason == "user_redirect"
                else "task_identity_requires_fresh_composition"
            )
            required_action = str(policy_map.get("required_action") or "").strip()
            new_packet = _reject_runtime_reuse(
                new_packet,
                plan=prior_plan,
                status=status,
                issues=[{"code": reason}],
                required_action=(
                    required_action
                    or "Prepare current sources and submit a fresh semantic proposal."
                ),
            )
        runtime_map = None
        host_runtime_status = "fresh_composition_required"
    elif runtime_map is not None:
        runtime_plan = runtime_map.get("composition_plan")
        if isinstance(runtime_plan, dict):
            metadata_packet = (
                composed_packet if semantic_proposal_supplied else previous_packet
            )
            persisted_plan = previous_packet.get("composition_plan")
            capsule_plan = (
                runtime_plan
                if semantic_proposal_supplied
                else persisted_plan
                if isinstance(persisted_plan, Mapping)
                else runtime_plan
            )
            has_capsule_provenance = packet_has_runtime_capsule_provenance(
                previous_packet,
                plan=capsule_plan,
            )
            phase_capsule_binding = capsule_plan.get("phase_capsule_binding")
            runtime_capsule = capsule_plan.get("runtime_capsule")
            applied = False
            if has_capsule_provenance:
                if not isinstance(phase_capsule_binding, Mapping) or not isinstance(
                    runtime_capsule, Mapping
                ):
                    new_packet = _reject_runtime_reuse(
                        new_packet,
                        plan=runtime_plan,
                        status="runtime_capsule_required",
                        issues=[{"code": "runtime_capsule_required"}],
                        required_action=(
                            "Prepare current sources and submit a fresh semantic proposal."
                        ),
                    )
                    if not semantic_proposal_supplied:
                        host_runtime_status = "runtime_capsule_rejected"
                else:
                    capsule_result = _runtime_capsule_result(
                        capsule_plan,
                        composition_preflight=composition_preflight,
                        source_nodes=source_nodes,
                    )
                    if capsule_result.get("accepted") is not True:
                        capsule_issues = [
                            item
                            for item in json_list(capsule_result.get("issues"))
                            if isinstance(item, dict)
                        ]
                        stale = any(
                            str(item.get("code") or "").startswith(
                                "runtime_capsule_source_"
                            )
                            for item in capsule_issues
                        )
                        new_packet = _reject_runtime_reuse(
                            new_packet,
                            plan=runtime_plan,
                            status=(
                                "stale_source_provenance"
                                if stale
                                else "runtime_capsule_invalid"
                            ),
                            issues=capsule_issues,
                            required_action=(
                                "Prepare current sources and submit a fresh semantic proposal."
                            ),
                        )
                        if not semantic_proposal_supplied:
                            host_runtime_status = "runtime_capsule_rejected"
                    else:
                        rehydrated_preflight = capsule_result.get(
                            "composition_preflight"
                        )
                        rehydrated_nodes = capsule_result.get("source_nodes")
                        replayed_plan = capsule_result.get("composition_plan")
                        if (
                            isinstance(rehydrated_preflight, Mapping)
                            and isinstance(rehydrated_nodes, list)
                            and isinstance(replayed_plan, Mapping)
                        ):
                            evidence = state.get("runtime_evidence")
                            evidence_map = (
                                dict(evidence) if isinstance(evidence, Mapping) else {}
                            )
                            embedded_continuation = capsule_plan.get(
                                "runtime_continuation"
                            )
                            prior_continuation = (
                                embedded_continuation
                                if trusted_runtime_continuation
                                else None
                            )
                            resumed = False
                            validated_continuation: dict[str, Any] | None = None
                            continuation_reason = (
                                "untrusted_continuation_discarded"
                                if embedded_continuation is not None
                                and not trusted_runtime_continuation
                                else "no_validated_continuation"
                            )
                            continuation_error = ""
                            meaningful_evidence = runtime_evidence_is_meaningful(
                                evidence_map
                            )
                            # State derived from the caller's previous packet is
                            # intentionally discarded here.  It can select no
                            # phase, gate, handoff, read, or trace outcome; only
                            # a separately validated continuation may resume.
                            runtime_map = None
                            if prior_continuation is not None:
                                try:
                                    validated_continuation = (
                                        validate_runtime_continuation(
                                            prior_continuation,
                                            composition_plan=replayed_plan,
                                        )
                                    )
                                    runtime_map = replay_runtime_continuation(
                                        replayed_plan, validated_continuation
                                    )
                                    resumed = True
                                    continuation_reason = (
                                        "capsule_bound_continuation"
                                    )
                                except RuntimeContinuationError as exc:
                                    # Packet runtime_state is deliberately not a
                                    # checkpoint.  A malformed continuation is
                                    # discarded and the compiler graph remains
                                    # safe at its bound phase.
                                    runtime_map = None
                                    continuation_reason = (
                                        "invalid_continuation_discarded"
                                    )
                                    continuation_error = str(exc)
                            if runtime_map is None:
                                runtime_map = advance_composition_runtime(
                                    replayed_plan, evidence_map
                                )
                            elif meaningful_evidence:
                                resumed_plan = runtime_map.get("composition_plan")
                                if isinstance(resumed_plan, Mapping):
                                    runtime_map = advance_composition_runtime(
                                        resumed_plan, evidence_map
                                    )
                            runtime_plan = runtime_map.get("composition_plan")
                            if isinstance(runtime_plan, Mapping):
                                runtime_plan = dict(runtime_plan)
                                # Do not accidentally retain an older chain if
                                # the current transition cannot be persisted.
                                # In particular, a continuation that reaches
                                # its bounded replay limit must not survive as
                                # a suffix-only checkpoint.
                                runtime_plan.pop("runtime_continuation", None)
                                continuation = None
                                if trusted_runtime_continuation:
                                    try:
                                        continuation = (
                                            validated_continuation
                                            if resumed and not meaningful_evidence
                                            else build_runtime_continuation(
                                                runtime_plan,
                                                runtime_map,
                                                prior=(
                                                    validated_continuation
                                                    if resumed
                                                    else None
                                                ),
                                            )
                                        )
                                    except RuntimeContinuationError as exc:
                                        continuation_reason = (
                                            "continuation_not_persisted"
                                        )
                                        continuation_error = str(exc)
                                if continuation is not None:
                                    runtime_plan = {
                                        **dict(runtime_plan),
                                        "runtime_continuation": continuation,
                                    }
                                runtime_map = {
                                    **runtime_map,
                                    "composition_plan": runtime_plan,
                                }
                            runtime_plan = runtime_map.get("composition_plan")
                            if not isinstance(runtime_plan, dict):
                                new_packet = _reject_runtime_reuse(
                                    new_packet,
                                    plan=replayed_plan,
                                    status="runtime_capsule_invalid",
                                    issues=[
                                        {
                                            "code": "runtime_capsule_runtime_replay_failed"
                                        }
                                    ],
                                    required_action=(
                                        "Prepare current sources and submit a fresh semantic proposal."
                                    ),
                                )
                                if not semantic_proposal_supplied:
                                    host_runtime_status = "runtime_capsule_rejected"
                            else:
                                new_packet = _apply_runtime_plan(
                                    new_packet,
                                    plan=runtime_plan,
                                    source_nodes=[
                                        item
                                        for item in rehydrated_nodes
                                        if isinstance(item, dict)
                                    ],
                                    metadata_packet=metadata_packet,
                                    composition_preflight=rehydrated_preflight,
                                )
                                diagnostics = dict(
                                    new_packet.get("composition_diagnostics") or {}
                                )
                                diagnostics["runtime_capsule_validation"] = {
                                    "accepted": True,
                                    "aliases": capsule_result.get("aliases") or [],
                                    "compiler_replay": True,
                                    "compiler_phase": capsule_result.get(
                                        "compiler_phase"
                                    ),
                                    "runtime_state_replay": {
                                        "resumed": resumed,
                                        "reason": continuation_reason,
                                        "error": continuation_error or None,
                                    },
                                }
                                new_packet["composition_diagnostics"] = diagnostics
                                applied = True
                                if not semantic_proposal_supplied:
                                    host_runtime_status = "runtime_capsule_revalidated"
                                    host_current_preflight_id = _preflight_id(
                                        rehydrated_preflight
                                    )
            else:
                bound_nodes, source_issues = bind_runtime_plan_sources(
                    runtime_plan,
                    source_nodes,
                    metadata_packet,
                )
                if source_issues:
                    new_packet = reject_stale_runtime_plan(
                        new_packet,
                        plan=runtime_plan,
                        issues=source_issues,
                        metadata_packet=metadata_packet,
                    )
                    if not semantic_proposal_supplied:
                        host_runtime_status = "runtime_capsule_rejected"
                else:
                    new_packet = _apply_runtime_plan(
                        new_packet,
                        plan=runtime_plan,
                        source_nodes=bound_nodes,
                        metadata_packet=metadata_packet,
                        composition_preflight=_runtime_preflight(
                            runtime_plan, source_nodes, metadata_packet
                        ),
                    )
                    applied = True
            if applied:
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
    if host_lineage is not None:
        _attach_host_composition_lineage(
            new_packet,
            lineage=host_lineage,
            runtime_snapshot_status=host_runtime_status,
            current_preflight_id=host_current_preflight_id,
        )
    elif rejected_host_lineage:
        _omit_untrusted_host_composition_lineage(new_packet)
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
        "composition_recompile_policy": policy_map or None,
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
