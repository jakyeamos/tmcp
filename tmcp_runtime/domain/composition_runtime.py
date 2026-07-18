"""Pure graph-aware runtime transitions for semantic composition plans."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .composition_preflight import (
    COMPOSITION_PLAN_SCHEMA,
    COMPOSITION_TRUST,
    json_list,
    ordered_unique,
    stable_digest,
    string_list,
)
from .composition_runtime_evidence import (
    COMPOSITION_RUNTIME_EVIDENCE_SCHEMA,
    composition_gate_catalog,
    composition_handoff_catalog,
    explicit_phase_override,
    evaluate_composition_gates,
    evaluate_composition_handoffs,
    evidence_summary as _summary,
    normalize_runtime_evidence,
)


COMPOSITION_RUNTIME_SCHEMA = "tmcp-composition-runtime-v0.1"

__all__ = [
    "COMPOSITION_RUNTIME_EVIDENCE_SCHEMA",
    "COMPOSITION_RUNTIME_SCHEMA",
    "advance_composition_runtime",
    "composition_gate_catalog",
    "composition_handoff_catalog",
    "evaluate_composition_gates",
    "evaluate_composition_handoffs",
    "normalize_runtime_evidence",
]


def _require_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema") != COMPOSITION_PLAN_SCHEMA:
        raise ValueError(f"Expected {COMPOSITION_PLAN_SCHEMA}.")
    stages = [
        item
        for item in json_list(plan.get("ordered_stages"))
        if isinstance(item, Mapping)
    ]
    if not stages:
        raise ValueError("Composition plan requires at least one ordered stage.")
    seen_stage_ids: set[str] = set()
    for index, stage in enumerate(stages):
        stage_id = str(stage.get("stage_id") or "").strip()
        phase = str(stage.get("phase") or "").strip()
        if not stage_id or not phase:
            raise ValueError(
                f"Composition stage {index + 1} requires a stage_id and phase."
            )
        if stage_id in seen_stage_ids:
            raise ValueError(f"Composition plan has duplicate stage_id {stage_id!r}.")
        seen_stage_ids.add(stage_id)
        if not isinstance(stage.get("node_ids"), list):
            raise ValueError(
                f"Composition stage {stage_id!r} requires a node_ids list."
            )


def _stage_index(
    stages: list[dict[str, Any]], phase: str, previous_stage_id: str
) -> int:
    for index, stage in enumerate(stages):
        if previous_stage_id and stage.get("stage_id") == previous_stage_id:
            return index
    for index, stage in enumerate(stages):
        if stage.get("phase") == phase:
            return index
    return 0


def _requested_stage_index(
    stages: list[dict[str, Any]], requested_phase: str, current_index: int
) -> int | None:
    matches = [
        index
        for index, stage in enumerate(stages)
        if stage.get("phase") == requested_phase
    ]
    if not matches:
        return None
    later = [index for index in matches if index > current_index]
    if stages[current_index].get("phase") == requested_phase:
        return later[0] if later else current_index
    return later[0] if later else matches[0]


def _transition_gate_ids(
    catalog: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    current_index: int,
    target_index: int,
) -> list[str]:
    if target_index <= current_index:
        return []
    exit_stage_ids = {
        str(stages[index]["stage_id"]) for index in range(current_index, target_index)
    }
    entry_stage_ids = {
        str(stages[index]["stage_id"])
        for index in range(current_index + 1, target_index + 1)
    }
    return [
        str(item["gate_id"])
        for item in catalog
        if (item["kind"] == "exit" and item["owner_stage_id"] in exit_stage_ids)
        or (item["kind"] == "entry" and item["owner_stage_id"] in entry_stage_ids)
    ]


def _transition_handoff_ids(
    catalog: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    current_index: int,
    target_index: int,
) -> list[str]:
    if target_index <= current_index:
        return []
    entry_stage_ids = {
        str(stages[index]["stage_id"])
        for index in range(current_index + 1, target_index + 1)
    }
    return [
        str(item["handoff_id"])
        for item in catalog
        if str(item.get("consumer_stage_id") or "") in entry_stage_ids
    ]


def _relationship_entries(
    plan: Mapping[str, Any], active_nodes: set[str], available_nodes: set[str]
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for edge in json_list(plan.get("typed_edges")):
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source not in available_nodes or target not in available_nodes:
            continue
        if source not in active_nodes and target not in active_nodes:
            continue
        relationship_id = "relationship-" + stable_digest(
            [
                source,
                edge.get("type"),
                target,
                sorted(string_list(edge.get("citations"))),
            ],
            16,
        )
        entries.append({"relationship_id": relationship_id, **dict(edge)})
    return entries


def _instruction_entries(stage: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for instruction in json_list(stage.get("bridge_instructions")):
        if not isinstance(instruction, Mapping):
            continue
        instruction_id = "instruction-" + stable_digest(
            [
                instruction.get("node_id"),
                instruction.get("instruction"),
                sorted(string_list(instruction.get("citations"))),
            ],
            16,
        )
        entries.append({"instruction_id": instruction_id, **dict(instruction)})
    return entries


def _runtime_observations(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for field in (
        "files_read",
        "files_changed",
        "commands_run",
        "failures",
        "browser_evidence",
        "user_overrides",
    ):
        for index, value in enumerate(json_list(evidence.get(field))):
            observations.append(
                {
                    "kind": field,
                    "index": index,
                    "summary": _summary(value),
                    "structured": isinstance(value, Mapping),
                }
            )
    for field in ("verification_results", "gate_results", "handoff_results"):
        for index, value in enumerate(json_list(evidence.get(field))):
            observations.append(
                {
                    "kind": field,
                    "index": index,
                    "summary": _summary(value),
                    "structured": True,
                }
            )
    if evidence.get("latest_user_message"):
        observations.append(
            {
                "kind": "latest_user_message",
                "index": 0,
                "summary": _summary(evidence["latest_user_message"]),
                "structured": False,
            }
        )
    if evidence.get("user_redirect"):
        observations.append(
            {
                "kind": "user_redirect",
                "index": 0,
                "summary": _summary(evidence["user_redirect"]),
                "structured": True,
            }
        )
    observations.extend(json_list(evidence.get("unstructured_evidence")))
    return observations


def _id_diff(previous: list[str], current: list[str]) -> dict[str, list[str]]:
    previous_set = set(previous)
    current_set = set(current)
    return {
        "added": sorted(current_set.difference(previous_set)),
        "dropped": sorted(previous_set.difference(current_set)),
        "unchanged": sorted(previous_set.intersection(current_set)),
    }


def advance_composition_runtime(
    previous_plan: Mapping[str, Any], runtime_evidence: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply runtime evidence while preserving and gate-checking the skill graph."""

    _require_plan(previous_plan)
    normalized = normalize_runtime_evidence(runtime_evidence)
    gate_evaluation = evaluate_composition_gates(previous_plan, normalized)
    handoff_evaluation = evaluate_composition_handoffs(previous_plan, normalized)
    stages = [
        dict(item)
        for item in json_list(previous_plan.get("ordered_stages"))
        if isinstance(item, Mapping)
    ]
    previous_state = previous_plan.get("runtime_state")
    state = dict(previous_state) if isinstance(previous_state, Mapping) else {}
    current_phase = str(
        previous_plan.get("current_phase") or stages[0].get("phase") or "start"
    )
    current_index = _stage_index(
        stages, current_phase, str(state.get("current_stage_id") or "")
    )
    requested_phase = str(normalized.get("requested_phase") or "")
    target_index = current_index
    warnings: list[str] = []
    blocked_reason = ""
    if requested_phase:
        requested_index = _requested_stage_index(stages, requested_phase, current_index)
        if requested_index is None:
            blocked_reason = "unknown_requested_phase"
            warnings.append(
                f"Requested phase `{requested_phase}` is not present in the composition plan."
            )
        else:
            target_index = requested_index
    required_gate_ids = _transition_gate_ids(
        gate_evaluation["catalog"], stages, current_index, target_index
    )
    required_handoff_ids = _transition_handoff_ids(
        handoff_evaluation["catalog"], stages, current_index, target_index
    )
    passed_ids = set(string_list(gate_evaluation["passed_gate_ids"]))
    pending_required = [
        gate_id for gate_id in required_gate_ids if gate_id not in passed_ids
    ]
    available_handoff_ids = set(
        string_list(handoff_evaluation["available_handoff_ids"])
    )
    failed_handoff_ids = set(string_list(handoff_evaluation["failed_handoff_ids"]))
    pending_required_handoffs = [
        handoff_id
        for handoff_id in required_handoff_ids
        if handoff_id not in available_handoff_ids
    ]
    failed_required_handoffs = [
        handoff_id
        for handoff_id in required_handoff_ids
        if handoff_id in failed_handoff_ids
    ]
    invalid_handoff_contracts = [
        item
        for item in json_list(handoff_evaluation.get("invalid_contracts"))
        if isinstance(item, Mapping)
    ]
    if target_index > current_index and pending_required:
        blocked_reason = "required_gates_not_passed"
    if target_index > current_index and pending_required_handoffs:
        blocked_reason = "required_handoffs_not_available"
    if target_index > current_index and failed_required_handoffs:
        blocked_reason = "required_handoffs_failed"
    if target_index > current_index and invalid_handoff_contracts:
        blocked_reason = "invalid_handoff_contracts"
    if target_index > current_index and normalized["failures"]:
        blocked_reason = "runtime_failures_present"
    if target_index > current_index and pending_required_handoffs:
        warnings.append(
            "Composition phase advancement is waiting for typed producer-to-consumer handoff evidence."
        )
    if target_index > current_index and failed_required_handoffs:
        warnings.append(
            "Composition phase advancement is blocked by a failed typed handoff."
        )
    if target_index > current_index and invalid_handoff_contracts:
        warnings.append(
            "Composition phase advancement is blocked because a handoff contract is malformed."
        )
    override = explicit_phase_override(
        list(normalized["user_overrides"]),
        str(normalized.get("latest_user_message") or ""),
    )
    override_applied = bool(
        blocked_reason
        in {
            "required_gates_not_passed",
            "required_handoffs_not_available",
            "required_handoffs_failed",
            "invalid_handoff_contracts",
            "runtime_failures_present",
        }
        and override
        and requested_phase
    )
    advancement_allowed = not blocked_reason or override_applied
    resolved_index = target_index if advancement_allowed else current_index
    resolved_stage = stages[resolved_index]
    resolved_phase = str(resolved_stage.get("phase") or current_phase)
    roles = [
        item
        for item in json_list(previous_plan.get("skill_roles"))
        if isinstance(item, Mapping)
    ]
    governing_node_ids = ordered_unique(
        [
            str(role.get("node_id") or "")
            for role in roles
            if role.get("source_role") == "governing_instruction"
        ]
    )
    governing_nodes = set(governing_node_ids)
    active_skill_ids = [
        node_id
        for node_id in string_list(resolved_stage.get("node_ids"))
        if node_id not in governing_nodes
    ]
    active_nodes = set(active_skill_ids).union(governing_nodes)
    available_nodes = {
        node_id
        for stage in stages[: resolved_index + 1]
        for node_id in string_list(stage.get("node_ids"))
    }.union(governing_nodes)
    active_relationships = _relationship_entries(
        previous_plan, active_nodes, available_nodes
    )
    active_instructions = _instruction_entries(resolved_stage)
    active_handoffs = [
        item
        for item in handoff_evaluation["catalog"]
        if str(item.get("consumer_stage_id") or "")
        == str(resolved_stage.get("stage_id") or "")
    ]
    deferred_skills = [
        {
            "node_id": node_id,
            "stage_id": str(stage.get("stage_id") or ""),
            "phase": str(stage.get("phase") or ""),
            "entry_conditions": string_list(stage.get("entry_conditions")),
        }
        for stage in stages[resolved_index + 1 :]
        for node_id in string_list(stage.get("node_ids"))
        if node_id not in governing_nodes
    ]
    fulfilled = [
        item
        for item in gate_evaluation["evaluated_gates"]
        if item["status"] == "passed"
    ]
    previous_fulfilled_ids = {
        str(item.get("gate_id"))
        for item in json_list(state.get("fulfilled_obligations"))
        if isinstance(item, Mapping)
    }
    newly_fulfilled = [
        item for item in fulfilled if item["gate_id"] not in previous_fulfilled_ids
    ]
    previous_active_skills = [
        node_id
        for node_id in string_list(state.get("active_skill_ids"))
        if node_id not in governing_nodes
    ] or [
        node_id
        for node_id in string_list(stages[current_index].get("node_ids"))
        if node_id not in governing_nodes
    ]
    previous_active_nodes = set(previous_active_skills).union(governing_nodes)
    previous_available_nodes = {
        node_id
        for stage in stages[: current_index + 1]
        for node_id in string_list(stage.get("node_ids"))
    }.union(governing_nodes)
    previous_relationship_ids = string_list(state.get("active_relationship_ids")) or [
        str(item["relationship_id"])
        for item in _relationship_entries(
            previous_plan, previous_active_nodes, previous_available_nodes
        )
    ]
    previous_instruction_ids = string_list(state.get("active_instruction_ids")) or [
        str(item["instruction_id"])
        for item in _instruction_entries(stages[current_index])
    ]
    previous_active_handoff_ids = string_list(state.get("active_handoff_ids")) or [
        str(item["handoff_id"])
        for item in handoff_evaluation["catalog"]
        if str(item.get("consumer_stage_id") or "")
        == str(stages[current_index].get("stage_id") or "")
    ]
    relationship_ids = [str(item["relationship_id"]) for item in active_relationships]
    instruction_ids = [str(item["instruction_id"]) for item in active_instructions]
    active_handoff_ids = [str(item["handoff_id"]) for item in active_handoffs]
    previous_available_handoff_ids = set(
        string_list(state.get("available_handoff_ids"))
    )
    newly_available_handoffs = [
        item
        for item in handoff_evaluation["evaluated_handoffs"]
        if item["status"] == "available"
        and str(item["handoff_id"]) not in previous_available_handoff_ids
    ]
    previous_files_read = string_list(state.get("files_read"))
    all_files_read = ordered_unique(
        previous_files_read + string_list(normalized["files_read"])
    )
    if resolved_index > current_index:
        trace_status = "advanced_with_override" if override_applied else "advanced"
    elif resolved_index < current_index:
        trace_status = "reverted"
    elif blocked_reason:
        trace_status = "blocked"
    else:
        trace_status = "unchanged"
    phase_trace = [
        item
        for item in json_list(state.get("phase_trace"))
        if isinstance(item, Mapping)
    ]
    phase_trace.append(
        {
            "sequence": len(phase_trace) + 1,
            "from_phase": current_phase,
            "to_phase": resolved_phase,
            "from_stage_id": str(stages[current_index].get("stage_id") or ""),
            "to_stage_id": str(resolved_stage.get("stage_id") or ""),
            "requested_phase": requested_phase,
            "status": trace_status,
            "reason": blocked_reason or "runtime_evidence_recorded",
            "required_gate_ids": required_gate_ids,
            "pending_gate_ids": pending_required,
            "required_handoff_ids": required_handoff_ids,
            "pending_handoff_ids": pending_required_handoffs,
            "failed_handoff_ids": failed_required_handoffs,
            "override": override if override_applied else None,
        }
    )
    observations = [
        item
        for item in json_list(state.get("runtime_observations"))
        if isinstance(item, Mapping)
    ] + _runtime_observations(normalized)
    updated_plan = copy.deepcopy(dict(previous_plan))
    updated_plan["current_phase"] = resolved_phase
    for role in json_list(updated_plan.get("skill_roles")):
        if isinstance(role, dict):
            role["activation"] = (
                "active" if str(role.get("node_id")) in active_nodes else "deferred"
            )
    for stage in json_list(updated_plan.get("ordered_stages")):
        if isinstance(stage, dict):
            stage["status"] = (
                "active"
                if str(stage.get("stage_id")) == str(resolved_stage.get("stage_id"))
                else "deferred"
            )
    runtime_state = {
        "current_stage_id": str(resolved_stage.get("stage_id") or ""),
        "active_skill_ids": active_skill_ids,
        "active_governing_node_ids": governing_node_ids,
        "active_relationship_ids": relationship_ids,
        "active_instruction_ids": instruction_ids,
        "active_handoff_ids": active_handoff_ids,
        "available_handoff_ids": string_list(
            handoff_evaluation["available_handoff_ids"]
        ),
        "handoff_results": [
            dict(item)
            for item in handoff_evaluation["evaluated_handoffs"]
            if isinstance(item, Mapping)
        ],
        "fulfilled_obligations": fulfilled,
        "phase_trace": phase_trace[-50:],
        "runtime_observations": observations[-100:],
        "files_read": all_files_read,
        "files_changed": ordered_unique(
            string_list(state.get("files_changed"))
            + string_list(normalized["files_changed"])
        ),
        "commands_run": ordered_unique(
            string_list(state.get("commands_run"))
            + string_list(normalized["commands_run"])
        ),
        "browser_evidence_count": int(state.get("browser_evidence_count") or 0)
        + len(normalized["browser_evidence"]),
    }
    updated_plan["runtime_state"] = runtime_state
    graph_diff = {
        "phase_change": (
            {"from": current_phase, "to": resolved_phase}
            if current_phase != resolved_phase
            else None
        ),
        "skills": {
            **_id_diff(previous_active_skills, active_skill_ids),
            "deferred": [item["node_id"] for item in deferred_skills],
        },
        "relationships": {
            **_id_diff(previous_relationship_ids, relationship_ids),
            "active": active_relationships,
        },
        "instructions": {
            **_id_diff(previous_instruction_ids, instruction_ids),
            "active": active_instructions,
        },
        "conflicts": {
            "active": [
                item
                for item in active_relationships
                if item.get("type") == "conflicts_with"
            ]
        },
        "reads": {
            "added": [
                path for path in all_files_read if path not in previous_files_read
            ],
            "all": all_files_read,
        },
        "gates": {
            "newly_fulfilled": [item["gate_id"] for item in newly_fulfilled],
            "failed": gate_evaluation["failed_gate_ids"],
            "pending": gate_evaluation["pending_gate_ids"],
            "bypassed": pending_required if override_applied else [],
        },
        "handoffs": {
            **_id_diff(previous_active_handoff_ids, active_handoff_ids),
            "active": active_handoffs,
            "newly_available": [
                str(item["handoff_id"]) for item in newly_available_handoffs
            ],
            "available": string_list(handoff_evaluation["available_handoff_ids"]),
            "failed": string_list(handoff_evaluation["failed_handoff_ids"]),
            "pending": string_list(handoff_evaluation["pending_handoff_ids"]),
            "bypassed": pending_required_handoffs if override_applied else [],
            "invalid_contracts": invalid_handoff_contracts,
        },
        "fulfilled_obligations": {
            "added": [item["gate_id"] for item in newly_fulfilled],
            "all": [item["gate_id"] for item in fulfilled],
        },
    }
    return {
        "schema": COMPOSITION_RUNTIME_SCHEMA,
        "composition_plan": updated_plan,
        "current_phase": resolved_phase,
        "current_stage_id": runtime_state["current_stage_id"],
        "phase_advance": {
            "requested_phase": requested_phase,
            "allowed": advancement_allowed,
            "blocked_reason": blocked_reason if not advancement_allowed else "",
            "required_gate_ids": required_gate_ids,
            "pending_gate_ids": pending_required,
            "required_handoff_ids": required_handoff_ids,
            "pending_handoff_ids": pending_required_handoffs,
            "failed_handoff_ids": failed_required_handoffs,
            "override_applied": override_applied,
        },
        "active_skill_ids": active_skill_ids,
        "active_governing_node_ids": governing_node_ids,
        "active_bridge_instructions": active_instructions,
        "deferred_skills": deferred_skills,
        "gate_evaluation": gate_evaluation,
        "handoff_evaluation": handoff_evaluation,
        "fulfilled_obligations": fulfilled,
        "phase_trace": runtime_state["phase_trace"],
        "runtime_observations": runtime_state["runtime_observations"],
        "graph_diff": graph_diff,
        "warnings": warnings,
        "trust": COMPOSITION_TRUST,
    }
