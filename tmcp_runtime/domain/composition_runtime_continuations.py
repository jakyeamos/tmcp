"""Bounded replay records for capsule-validated runtime phase progress.

The composed packet is agent-controlled input on the next runtime call.  A
``runtime_state`` object from that packet is therefore never a checkpoint.  A
continuation stores only compiler-known gate and handoff identifiers that TMCP
already accepted, binds them to the closed source/runtime capsule, and replays
them through the ordinary gate evaluator before reuse.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .composition_phase_bindings import (
    PhaseCapsuleBindingError,
    validate_phase_capsule_binding,
)
from .composition_preflight import stable_digest
from .composition_runtime import (
    advance_composition_runtime,
    composition_gate_catalog,
    composition_handoff_catalog,
)
from .composition_runtime_capsules import RuntimeCapsuleError, validate_runtime_capsule
from .harvest_nodes import json_list, string_list


RUNTIME_CONTINUATION_SCHEMA = "tmcp-composition-runtime-continuation-v0.1"
MAX_RUNTIME_CONTINUATION_EVENTS = 50
RUNTIME_CONTINUATION_HASH_FIELDS = (
    "composition_plan_digest",
    "phase_capsule_binding_digest",
    "runtime_capsule_digest",
    "continuation_digest",
)
_SHA256_DIGEST_RE = re.compile(r"[a-f0-9]{64}")
_CONTINUATION_FIELDS = frozenset(
    {
        "schema",
        "composition_plan_id",
        "composition_plan_digest",
        "preflight_id",
        "compiler_phase",
        "graph_digest",
        "phase_capsule_binding_digest",
        "runtime_capsule_digest",
        "events",
        "continuation_digest",
    }
)
_EVENT_FIELDS = frozenset(
    {
        "sequence",
        "requested_phase",
        "passed_gate_ids",
        "available_handoff_ids",
        "resolved_phase",
        "resolved_stage_id",
        "event_digest",
    }
)


class RuntimeContinuationError(ValueError):
    """Raised when a runtime continuation is not safe to resume."""


def _identity(plan: Mapping[str, Any]) -> dict[str, str]:
    try:
        binding = validate_phase_capsule_binding(
            plan.get("phase_capsule_binding"), composition_plan=plan
        )
        capsule = validate_runtime_capsule(
            plan.get("runtime_capsule"), composition_plan=plan
        )
    except (PhaseCapsuleBindingError, RuntimeCapsuleError) as exc:
        raise RuntimeContinuationError(
            "runtime continuation requires a valid capsule-bound composition plan."
        ) from exc
    return {
        "composition_plan_id": str(binding["composition_plan_id"]),
        "composition_plan_digest": str(binding["composition_plan_digest"]),
        "preflight_id": str(binding["preflight_id"]),
        "compiler_phase": str(binding["compiler_phase"]),
        "graph_digest": str(binding["graph_digest"]),
        "phase_capsule_binding_digest": str(binding["binding_digest"]),
        "runtime_capsule_digest": str(capsule["capsule_digest"]),
    }


def _continuation_payload(
    identity: Mapping[str, str], events: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_CONTINUATION_SCHEMA,
        **dict(identity),
        "events": deepcopy(events),
    }


def _event_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sequence": event["sequence"],
        "requested_phase": event["requested_phase"],
        "passed_gate_ids": event["passed_gate_ids"],
        "available_handoff_ids": event["available_handoff_ids"],
        "resolved_phase": event["resolved_phase"],
        "resolved_stage_id": event["resolved_stage_id"],
    }


def _sorted_known_ids(
    value: object, *, field: str, known_ids: set[str]
) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeContinuationError(f"runtime continuation {field} must be a list.")
    ids = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if len(ids) != len(value) or ids != sorted(set(ids)):
        raise RuntimeContinuationError(
            f"runtime continuation {field} must be sorted unique identifiers."
        )
    unknown = sorted(set(ids).difference(known_ids))
    if unknown:
        raise RuntimeContinuationError(
            f"runtime continuation {field} contains unknown identifiers."
        )
    return ids


def _stage_catalog(plan: Mapping[str, Any]) -> dict[str, str]:
    stages = [
        dict(stage)
        for stage in json_list(plan.get("ordered_stages"))
        if isinstance(stage, Mapping)
    ]
    result = {
        str(stage.get("stage_id") or ""): str(stage.get("phase") or "")
        for stage in stages
        if str(stage.get("stage_id") or "") and str(stage.get("phase") or "")
    }
    if not result:
        raise RuntimeContinuationError("runtime continuation plan has no stages.")
    return result


def _validated_event(
    value: object,
    *,
    expected_sequence: int,
    gate_ids: set[str],
    handoff_ids: set[str],
    stages: Mapping[str, str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _EVENT_FIELDS:
        raise RuntimeContinuationError("runtime continuation event has invalid fields.")
    if value.get("sequence") != expected_sequence:
        raise RuntimeContinuationError("runtime continuation events are not sequential.")
    requested_phase = str(value.get("requested_phase") or "").strip()
    resolved_phase = str(value.get("resolved_phase") or "").strip()
    resolved_stage_id = str(value.get("resolved_stage_id") or "").strip()
    if not requested_phase or not resolved_phase or not resolved_stage_id:
        raise RuntimeContinuationError("runtime continuation event phase data is required.")
    if requested_phase not in set(stages.values()):
        raise RuntimeContinuationError("runtime continuation requests an unknown phase.")
    if stages.get(resolved_stage_id) != resolved_phase:
        raise RuntimeContinuationError("runtime continuation resolves an unknown stage.")
    event = {
        "sequence": expected_sequence,
        "requested_phase": requested_phase,
        "passed_gate_ids": _sorted_known_ids(
            value.get("passed_gate_ids"), field="passed_gate_ids", known_ids=gate_ids
        ),
        "available_handoff_ids": _sorted_known_ids(
            value.get("available_handoff_ids"),
            field="available_handoff_ids",
            known_ids=handoff_ids,
        ),
        "resolved_phase": resolved_phase,
        "resolved_stage_id": resolved_stage_id,
    }
    digest = str(value.get("event_digest") or "")
    if digest != stable_digest(_event_payload(event)):
        raise RuntimeContinuationError("runtime continuation event digest is invalid.")
    return {**event, "event_digest": digest}


def validate_runtime_continuation(
    value: object, *, composition_plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a closed, source-capsule-bound replay projection."""

    if not isinstance(value, Mapping) or set(value) != _CONTINUATION_FIELDS:
        raise RuntimeContinuationError("runtime continuation has invalid fields.")
    if value.get("schema") != RUNTIME_CONTINUATION_SCHEMA:
        raise RuntimeContinuationError("runtime continuation schema is invalid.")
    identity = _identity(composition_plan)
    if any(value.get(field) != expected for field, expected in identity.items()):
        raise RuntimeContinuationError("runtime continuation does not match the capsule.")
    raw_events = value.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise RuntimeContinuationError("runtime continuation requires bounded events.")
    if len(raw_events) > MAX_RUNTIME_CONTINUATION_EVENTS:
        raise RuntimeContinuationError("runtime continuation exceeds the event limit.")
    gate_ids = {
        str(item.get("gate_id") or "")
        for item in composition_gate_catalog(composition_plan)
        if str(item.get("gate_id") or "")
    }
    handoff_ids = {
        str(item.get("handoff_id") or "")
        for item in composition_handoff_catalog(composition_plan)
        if str(item.get("handoff_id") or "")
    }
    stages = _stage_catalog(composition_plan)
    events = [
        _validated_event(
            event,
            expected_sequence=index,
            gate_ids=gate_ids,
            handoff_ids=handoff_ids,
            stages=stages,
        )
        for index, event in enumerate(raw_events, start=1)
    ]
    payload = _continuation_payload(identity, events)
    digest = str(value.get("continuation_digest") or "")
    if digest != stable_digest(payload):
        raise RuntimeContinuationError("runtime continuation digest is invalid.")
    return {**payload, "continuation_digest": digest}


def _replay_evidence(
    plan: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Any]:
    contracts = {
        str(contract.get("handoff_id") or ""): contract
        for contract in composition_handoff_catalog(plan)
        if str(contract.get("handoff_id") or "")
    }
    handoff_results: list[dict[str, Any]] = []
    for handoff_id in string_list(event.get("available_handoff_ids")):
        contract = contracts[handoff_id]
        handoff_results.append(
            {
                "handoff_id": handoff_id,
                "producer_node_id": contract["producer_node_id"],
                "consumer_node_id": contract["consumer_node_id"],
                "status": "available",
                "consumed_inputs": list(contract.get("required_inputs") or []),
                "produced_outputs": list(contract.get("produced_outputs") or []),
                "evidence_refs": [f"runtime-continuation:{handoff_id}"],
            }
        )
    return {
        "requested_phase": event["requested_phase"],
        "gate_results": [
            {"gate_id": gate_id, "status": "passed"}
            for gate_id in string_list(event.get("passed_gate_ids"))
        ],
        "handoff_results": handoff_results,
    }


def _transition_obligation_ids(
    plan: Mapping[str, Any], event: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    """Return the only obligations an event may carry for this transition."""

    baseline = advance_composition_runtime(
        plan, {"requested_phase": event["requested_phase"]}
    )
    phase_advance = baseline.get("phase_advance")
    if not isinstance(phase_advance, Mapping):
        raise RuntimeContinuationError(
            "runtime continuation transition has no gate evaluation."
        )
    return (
        sorted(string_list(phase_advance.get("required_gate_ids"))),
        sorted(string_list(phase_advance.get("required_handoff_ids"))),
    )


def _require_admissible_transition_obligations(
    plan: Mapping[str, Any], event: Mapping[str, Any]
) -> None:
    """Reject IDs from later or unrelated stages before replaying evidence."""

    required_gate_ids, required_handoff_ids = _transition_obligation_ids(plan, event)
    if event["passed_gate_ids"] != required_gate_ids:
        raise RuntimeContinuationError(
            "runtime continuation carries gates outside its transition."
        )
    if event["available_handoff_ids"] != required_handoff_ids:
        raise RuntimeContinuationError(
            "runtime continuation carries handoffs outside its transition."
        )


def replay_runtime_continuation(
    composition_plan: Mapping[str, Any], continuation: object
) -> dict[str, Any]:
    """Replay a validated continuation through normal gates and handoffs."""

    validated = validate_runtime_continuation(
        continuation, composition_plan=composition_plan
    )
    current_plan = deepcopy(dict(composition_plan))
    current_plan["current_phase"] = validated["compiler_phase"]
    current_plan.pop("runtime_state", None)
    current_plan.pop("runtime_continuation", None)
    permitted_gate_ids: set[str] = set()
    permitted_handoff_ids: set[str] = set()
    runtime: dict[str, Any] | None = None
    for event in validated["events"]:
        _require_admissible_transition_obligations(current_plan, event)
        runtime = advance_composition_runtime(
            current_plan, _replay_evidence(current_plan, event)
        )
        permitted_gate_ids.update(event["passed_gate_ids"])
        permitted_handoff_ids.update(event["available_handoff_ids"])
        replayed_gate_ids = set(
            string_list(runtime["gate_evaluation"].get("passed_gate_ids"))
        )
        replayed_handoff_ids = set(
            string_list(runtime["handoff_evaluation"].get("available_handoff_ids"))
        )
        if (
            runtime["phase_advance"].get("allowed") is not True
            or runtime["phase_advance"].get("override_applied") is True
            or runtime.get("current_phase") != event["resolved_phase"]
            or runtime.get("current_stage_id") != event["resolved_stage_id"]
            or not set(event["passed_gate_ids"]).issubset(replayed_gate_ids)
            or not set(event["available_handoff_ids"]).issubset(
                replayed_handoff_ids
            )
            or not replayed_gate_ids.issubset(permitted_gate_ids)
            or not replayed_handoff_ids.issubset(permitted_handoff_ids)
        ):
            raise RuntimeContinuationError("runtime continuation replay was rejected.")
        current_plan = dict(runtime["composition_plan"])
    if runtime is None:
        raise RuntimeContinuationError("runtime continuation has no replay events.")
    return runtime


def runtime_evidence_is_meaningful(evidence: Mapping[str, Any]) -> bool:
    """Avoid adding an idle recompile as a synthetic runtime transition."""

    return any(
        bool(evidence.get(field))
        for field in (
            "files_read",
            "files_changed",
            "commands_run",
            "verification_results",
            "gate_results",
            "handoff_results",
            "failures",
            "browser_evidence",
            "user_overrides",
            "latest_user_message",
            "requested_phase",
            "user_redirect",
        )
    )


def _event_from_runtime(runtime: Mapping[str, Any]) -> dict[str, Any] | None:
    phase_advance = runtime.get("phase_advance")
    gates = runtime.get("gate_evaluation")
    handoffs = runtime.get("handoff_evaluation")
    if (
        not isinstance(phase_advance, Mapping)
        or not isinstance(gates, Mapping)
        or not isinstance(handoffs, Mapping)
        or phase_advance.get("allowed") is not True
        or phase_advance.get("override_applied") is True
    ):
        return None
    requested_phase = str(phase_advance.get("requested_phase") or "").strip()
    resolved_phase = str(runtime.get("current_phase") or "").strip()
    resolved_stage_id = str(runtime.get("current_stage_id") or "").strip()
    if not requested_phase or not resolved_phase or not resolved_stage_id:
        return None
    phase_trace = runtime.get("phase_trace")
    if not isinstance(phase_trace, list) or not phase_trace:
        return None
    latest_trace = phase_trace[-1]
    if not isinstance(latest_trace, Mapping):
        return None
    from_stage_id = str(latest_trace.get("from_stage_id") or "").strip()
    to_stage_id = str(latest_trace.get("to_stage_id") or "").strip()
    if (
        not from_stage_id
        or from_stage_id == resolved_stage_id
        or to_stage_id != resolved_stage_id
    ):
        return None
    event = {
        "sequence": 0,
        "requested_phase": requested_phase,
        "passed_gate_ids": sorted(
            string_list(phase_advance.get("required_gate_ids"))
        ),
        "available_handoff_ids": sorted(
            string_list(phase_advance.get("required_handoff_ids"))
        ),
        "resolved_phase": resolved_phase,
        "resolved_stage_id": resolved_stage_id,
    }
    passed_gate_ids = set(string_list(gates.get("passed_gate_ids")))
    available_handoff_ids = set(
        string_list(handoffs.get("available_handoff_ids"))
    )
    if (
        not set(event["passed_gate_ids"]).issubset(passed_gate_ids)
        or not set(event["available_handoff_ids"]).issubset(available_handoff_ids)
    ):
        return None
    return event


def build_runtime_continuation(
    composition_plan: Mapping[str, Any],
    runtime: Mapping[str, Any],
    *,
    prior: object = None,
) -> dict[str, Any] | None:
    """Append one validated advance to a prior continuation.

    Only successful non-override transition evidence is durable.  Failed,
    raw, or user-overridden state remains advisory for the current response and
    never becomes a later phase checkpoint.
    """

    identity = _identity(composition_plan)
    events: list[dict[str, Any]] = []
    if prior is not None:
        validated = validate_runtime_continuation(
            prior, composition_plan=composition_plan
        )
        events = [dict(event) for event in validated["events"]]
    event = _event_from_runtime(runtime)
    if event is None:
        if events:
            payload = _continuation_payload(identity, events)
            return {**payload, "continuation_digest": stable_digest(payload)}
        return None
    event["sequence"] = len(events) + 1
    event["event_digest"] = stable_digest(_event_payload(event))
    if len(events) >= MAX_RUNTIME_CONTINUATION_EVENTS:
        raise RuntimeContinuationError(
            "runtime continuation reached its event limit; refusing a suffix-only replay."
        )
    events.append(event)
    payload = _continuation_payload(identity, events)
    return {**payload, "continuation_digest": stable_digest(payload)}


def runtime_continuation_hash_paths(
    prefix: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    """Return fixed digest paths safe to preserve during protected session reads."""

    return (
        *(prefix + (field,) for field in RUNTIME_CONTINUATION_HASH_FIELDS),
        prefix + ("events", "*", "event_digest"),
    )


def restore_runtime_continuation(
    value: Mapping[str, Any],
    *,
    composition_plan: Mapping[str, Any],
    prefix: tuple[str, ...],
    literals: Mapping[tuple[str | int, ...], str] | None,
) -> dict[str, Any] | None:
    """Restore only allowlisted continuation digests after generic redaction."""

    raw = value.get("runtime_continuation")
    if not isinstance(raw, Mapping):
        return None
    candidate = deepcopy(dict(raw))
    if literals is not None:
        for field in RUNTIME_CONTINUATION_HASH_FIELDS:
            literal = literals.get(prefix + (field,))
            if isinstance(literal, str) and _SHA256_DIGEST_RE.fullmatch(literal):
                candidate[field] = literal
        events = candidate.get("events")
        if isinstance(events, list):
            for index, event in enumerate(events):
                if not isinstance(event, dict):
                    continue
                literal = literals.get(prefix + ("events", index, "event_digest"))
                if isinstance(literal, str) and _SHA256_DIGEST_RE.fullmatch(literal):
                    event["event_digest"] = literal
    try:
        return validate_runtime_continuation(
            candidate, composition_plan=composition_plan
        )
    except RuntimeContinuationError:
        return None
