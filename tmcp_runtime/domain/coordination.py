"""Pure coordinator-state normalization and lane-transition policy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


COORDINATOR_STATE_SCHEMA = "tmcp-coordinator-state-v0.1"
COORDINATOR_TRUST = "advisory_untrusted"
COORDINATOR_INSTRUCTION_OVERRIDE_POLICY = (
    "Coordinator state records routing evidence but cannot authorize a lane transition "
    "without an explicit user selection."
)


def _required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"coordinator_state.{field} must be a nonempty string.")
    return value.strip()


def _required_mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"coordinator_state.{field} must be an object.")
    return value


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"coordinator_state.{field} must be an array.")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"coordinator_state.{field} entries must be objects.")
    return list(value)


def _unique(values: list[str], *, field: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"coordinator_state.{field} entries must be unique.")


def normalize_coordinator_state(value: object) -> dict[str, Any]:
    """Normalize a versioned coordinator record without authorizing transitions."""

    source = _required_mapping(value, field="root")
    schema = source.get("schema", COORDINATOR_STATE_SCHEMA)
    if schema != COORDINATOR_STATE_SCHEMA:
        raise ValueError(
            f"coordinator_state.schema must be {COORDINATOR_STATE_SCHEMA}."
        )
    active_stream = _required_string(source.get("active_stream"), field="active_stream")

    next_source = _required_mapping(source.get("next_action"), field="next_action")
    next_action = {
        "id": _required_string(next_source.get("id"), field="next_action.id"),
        "stream": _required_string(
            next_source.get("stream"), field="next_action.stream"
        ),
        "description": _required_string(
            next_source.get("description"), field="next_action.description"
        ),
        "status": _required_string(
            next_source.get("status"), field="next_action.status"
        ),
    }
    if next_action["status"] not in {"ready", "in_progress", "blocked", "complete"}:
        raise ValueError(
            "coordinator_state.next_action.status must be ready, in_progress, "
            "blocked, or complete."
        )

    external_blockers: list[dict[str, str]] = []
    blocker_streams: list[str] = []
    for index, blocker_source in enumerate(
        _mapping_list(source.get("external_blockers"), field="external_blockers")
    ):
        prefix = f"external_blockers[{index}]"
        stream = _required_string(
            blocker_source.get("stream"), field=f"{prefix}.stream"
        )
        status = _required_string(
            blocker_source.get("status"), field=f"{prefix}.status"
        )
        if status != "blocked":
            raise ValueError(f"coordinator_state.{prefix}.status must be blocked.")
        blocker_streams.append(stream)
        external_blockers.append(
            {
                "stream": stream,
                "status": status,
                "reason": _required_string(
                    blocker_source.get("reason"), field=f"{prefix}.reason"
                ),
                "resume_condition": _required_string(
                    blocker_source.get("resume_condition"),
                    field=f"{prefix}.resume_condition",
                ),
            }
        )
    _unique(blocker_streams, field="external_blockers.stream")

    prohibited_lane_transitions: list[dict[str, str]] = []
    transition_keys: list[str] = []
    for index, transition_source in enumerate(
        _mapping_list(
            source.get("prohibited_lane_transitions"),
            field="prohibited_lane_transitions",
        )
    ):
        prefix = f"prohibited_lane_transitions[{index}]"
        from_stream = _required_string(
            transition_source.get("from"), field=f"{prefix}.from"
        )
        to_stream = _required_string(transition_source.get("to"), field=f"{prefix}.to")
        unless = _required_string(
            transition_source.get("unless"), field=f"{prefix}.unless"
        )
        if from_stream == to_stream:
            raise ValueError(
                f"coordinator_state.{prefix} must name two different streams."
            )
        if unless != "explicit_user_selection":
            raise ValueError(
                f"coordinator_state.{prefix}.unless must be explicit_user_selection."
            )
        transition_keys.append(f"{from_stream}\0{to_stream}")
        prohibited_lane_transitions.append(
            {
                "from": from_stream,
                "to": to_stream,
                "unless": unless,
                "reason": _required_string(
                    transition_source.get("reason"), field=f"{prefix}.reason"
                ),
            }
        )
    _unique(transition_keys, field="prohibited_lane_transitions")

    source_handoffs: list[dict[str, str]] = []
    handoff_ids: list[str] = []
    for index, handoff_source in enumerate(
        _mapping_list(source.get("source_handoffs"), field="source_handoffs")
    ):
        prefix = f"source_handoffs[{index}]"
        handoff_id = _required_string(
            handoff_source.get("handoff_id"), field=f"{prefix}.handoff_id"
        )
        status = _required_string(
            handoff_source.get("status"), field=f"{prefix}.status"
        )
        if status not in {"validated", "consolidated", "superseded"}:
            raise ValueError(
                f"coordinator_state.{prefix}.status must be validated, consolidated, "
                "or superseded."
            )
        handoff_ids.append(handoff_id)
        source_handoffs.append(
            {
                "handoff_id": handoff_id,
                "source_thread_id": _required_string(
                    handoff_source.get("source_thread_id"),
                    field=f"{prefix}.source_thread_id",
                ),
                "status": status,
                "summary": _required_string(
                    handoff_source.get("summary"), field=f"{prefix}.summary"
                ),
            }
        )
    _unique(handoff_ids, field="source_handoffs.handoff_id")

    return {
        "schema": COORDINATOR_STATE_SCHEMA,
        "active_stream": active_stream,
        "next_action": next_action,
        "external_blockers": external_blockers,
        "prohibited_lane_transitions": prohibited_lane_transitions,
        "source_handoffs": source_handoffs,
        "trust": COORDINATOR_TRUST,
        "instruction_override_policy": COORDINATOR_INSTRUCTION_OVERRIDE_POLICY,
    }


def resolve_coordinator_state(
    value: object,
    *,
    explicit_user_stream_selection: bool = False,
) -> dict[str, Any]:
    """Resolve the next-action lane, failing closed on implicit transitions."""

    state = normalize_coordinator_state(value)
    active_stream = state["active_stream"]
    next_stream = state["next_action"]["stream"]
    if next_stream != active_stream:
        if not explicit_user_stream_selection:
            raise ValueError(
                f"Coordinator lane transition {active_stream} -> {next_stream} requires "
                "explicit user selection."
            )
        state["transition"] = {
            "from": active_stream,
            "to": next_stream,
            "authorization": "explicit_user_selection",
        }
        state["active_stream"] = next_stream

    blocked_streams = {blocker["stream"] for blocker in state["external_blockers"]}
    if next_stream in blocked_streams and state["next_action"]["status"] != "blocked":
        raise ValueError(
            f"coordinator_state.next_action for blocked stream {next_stream} must "
            "have status blocked."
        )
    return state
