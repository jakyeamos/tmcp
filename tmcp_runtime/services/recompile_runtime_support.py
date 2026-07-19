"""Private, deterministic runtime helpers for packet recompilation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from tmcp_runtime.domain.composition_planning import compile_semantic_composition
from tmcp_runtime.domain.composition_preflight import COMPOSITION_TRUST, stable_digest
from tmcp_runtime.domain.composition_runtime_capsules import (
    RUNTIME_CAPSULE_INVALID_PROVENANCE_STATUS,
    RUNTIME_CAPSULE_PROVENANCE_STATUS_FIELD,
    RuntimeCapsuleError,
    rehydrate_runtime_capsule,
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
from tmcp_runtime.services.compose import active_instructions_for_source_node
from tmcp_runtime.services.semantic_compose import apply_semantic_composition


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
