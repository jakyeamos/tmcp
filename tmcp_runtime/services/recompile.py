"""In-memory recompiled-packet finalization over adapter-composed packets."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from tmcp_runtime.domain.composition_runtime import advance_composition_runtime
from tmcp_runtime.domain.composition_runtime_capsules import (
    packet_has_runtime_capsule_provenance,
)
from tmcp_runtime.domain.composition_runtime_continuations import (
    RuntimeContinuationError,
    build_runtime_continuation,
    replay_runtime_continuation,
    runtime_evidence_is_meaningful,
    validate_runtime_continuation,
)
from tmcp_runtime.domain.harvest_nodes import (
    json_list,
    node_source_role,
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
from tmcp_runtime.services.compose import enrich_packet_from_source_nodes
from tmcp_runtime.services.recompile_runtime_support import (
    _apply_runtime_metadata,
    _apply_runtime_plan,
    _attach_host_composition_lineage,
    _omit_untrusted_host_composition_lineage,
    _preflight_id,
    _reject_runtime_reuse,
    _runtime_capsule_result,
    _runtime_preflight,
    _validated_host_composition_lineage,
)
from tmcp_runtime.services.recompile_source_validation import (
    bind_runtime_plan_sources,
    reject_stale_runtime_plan,
)
from tmcp_runtime.services.sessions import has_session_runtime_continuation_trust


RECOMPILED_PACKET_SCHEMA = "tmcp-recompiled-packet-v0.1"


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
