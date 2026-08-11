#!/usr/bin/env python3
"""Extract provider-native turn metrics from an explicit Codex rollout JSONL.

This adapter intentionally ignores prompts, messages, reasoning, tool arguments,
and tool outputs. It retains only authoritative tool-call IDs and names, and
emits a scorer-ready v0.7 provider_metrics object only when the Codex host also
supplies the context-assembly counters that rollout JSONL does not contain. The
terminal finalization seam rejects a completed rollout without that companion
instead of treating missing attribution as zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tmcp_runtime.api.registry import PUBLIC_TOOL_NAMES  # noqa: E402


TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
# These are the public MCP tool names from the canonical TMCP contract registry.
# Exact set membership is intentional: CLI aliases, filenames, prose, and
# arbitrary names containing "tmcp" are not TMCP tool calls.
TMCP_TOOL_NAMES = frozenset(PUBLIC_TOOL_NAMES)
TOOL_CALL_TYPES = frozenset({"function_call", "custom_tool_call"})
TOOL_OUTPUT_TYPES = frozenset({"function_call_output", "custom_tool_call_output"})
TOOL_ITEM_TYPES = TOOL_CALL_TYPES | TOOL_OUTPUT_TYPES
EXPECTED_OUTPUT_TYPES = {
    "function_call": "function_call_output",
    "custom_tool_call": "custom_tool_call_output",
}
HOST_COUNTER_FIELDS = (
    "skill_read_calls",
    "skill_read_input_tokens",
)
TMCP_ROUND_TRIP_FIELD = "tmcp_model_visible_round_trips"
HOST_OBSERVATION_COUNTER_FIELDS = frozenset(
    (*HOST_COUNTER_FIELDS, TMCP_ROUND_TRIP_FIELD)
)
HOST_OBSERVATION_SCHEMA = "codex-tmcp-host-observation-v0.1"
UNAVAILABLE_ATTRIBUTION_DISPOSITION = "unavailable-attribution"
ATTRIBUTION_AVAILABILITY_SCHEMA = (
    "tmcp-invocation-admission-attribution-availability-v0.11"
)
COMPLETE_ZERO = "complete-zero"
COMPLETE_EXACT = "complete-exact"
UNAVAILABLE = "unavailable"


class HostObservationUnavailableError(ValueError):
    """Reject a terminal turn whose host-owned attribution companion is absent."""

    disposition = UNAVAILABLE_ATTRIBUTION_DISPOSITION

    def __init__(self) -> None:
        super().__init__(
            "terminal rollout is rejected: "
            f"{HOST_OBSERVATION_SCHEMA} is missing after task_complete "
            f"(disposition={self.disposition}); exact provider attribution for "
            "surviving skills is unavailable; missing companion evidence is not zero"
        )


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty RFC3339 timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC3339 timestamp") from exc


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _token_usage(value: object, field: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return {
        token_field: _non_negative_int(value.get(token_field), f"{field}.{token_field}")
        for token_field in TOKEN_FIELDS
    }


def _read_rollout(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Retain telemetry records only; discard all model and tool content."""
    records: dict[str, list[dict[str, Any]]] = {
        "session_meta": [],
        "turn_context": [],
        "task_events": [],
        "token_events": [],
        "tool_items": [],
    }
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        row_type = row.get("type")
        payload = row.get("payload")
        if row_type in {
            "session_meta",
            "turn_context",
            "event_msg",
            "response_item",
        } and not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number} payload must be an object")
        if not isinstance(payload, dict):
            continue
        if row_type == "session_meta":
            records["session_meta"].append(
                {
                    "session_id": payload.get("session_id") or payload.get("id"),
                    "model_provider": payload.get("model_provider"),
                    "originator": payload.get("originator"),
                    "source": payload.get("source"),
                    "cli_version": payload.get("cli_version"),
                }
            )
        elif row_type == "turn_context":
            records["turn_context"].append(
                {"turn_id": payload.get("turn_id"), "model": payload.get("model")}
            )
        elif row_type == "event_msg" and payload.get("type") in {
            "task_started",
            "task_complete",
        }:
            records["task_events"].append(
                {
                    "timestamp": row.get("timestamp"),
                    "event_type": payload.get("type"),
                    "turn_id": payload.get("turn_id"),
                    "duration_ms": payload.get("duration_ms"),
                }
            )
        elif row_type == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info")
            if isinstance(info, dict):
                records["token_events"].append(
                    {
                        "timestamp": row.get("timestamp"),
                        "last": info.get("last_token_usage"),
                        "total": info.get("total_token_usage"),
                    }
                )
        elif row_type == "response_item" and payload.get("type") in {
            "function_call",
            "custom_tool_call",
            "function_call_output",
            "custom_tool_call_output",
        }:
            records["tool_items"].append(
                {
                    "timestamp": row.get("timestamp"),
                    "item_type": payload.get("type"),
                    "call_id": payload.get("call_id"),
                    "name": payload.get("name")
                    if payload.get("type") in TOOL_CALL_TYPES
                    else None,
                }
            )
    return records


def _one_value(values: list[object], field: str) -> str:
    normalized = {_non_empty_string(value, field) for value in values}
    if len(normalized) != 1:
        raise ValueError(f"rollout must contain exactly one consistent {field}")
    return normalized.pop()


def _sum_token_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    totals = {field: 0 for field in TOKEN_FIELDS}
    for index, event in enumerate(events):
        usage = _token_usage(event.get("last"), f"token_events[{index}].last")
        for field in TOKEN_FIELDS:
            totals[field] += usage[field]
    return totals


def _validate_cumulative_delta(
    events: list[dict[str, Any]],
    prior_event: dict[str, Any] | None,
    summed: dict[str, int],
) -> None:
    final = _token_usage(events[-1].get("total"), "final total_token_usage")
    baseline = (
        _token_usage(prior_event.get("total"), "prior total_token_usage")
        if prior_event is not None
        else {field: 0 for field in TOKEN_FIELDS}
    )
    for field in TOKEN_FIELDS:
        delta = final[field] - baseline[field]
        if delta < 0:
            raise ValueError(f"cumulative {field} decreased across the selected turn")
        if delta != summed[field]:
            raise ValueError(
                f"provider token evidence is inconsistent for {field}: "
                f"cumulative delta {delta} != last-call sum {summed[field]}"
            )


def extract_turn(path: Path, turn_id: str) -> dict[str, Any]:
    turn_id = _non_empty_string(turn_id, "turn_id")
    records = _read_rollout(path)
    session_id = _one_value(
        [row.get("session_id") for row in records["session_meta"]], "session_id"
    )
    provider = _one_value(
        [row.get("model_provider") for row in records["session_meta"]],
        "model_provider",
    )
    originator = _one_value(
        [row.get("originator") for row in records["session_meta"]], "originator"
    )
    source = _one_value(
        [row.get("source") for row in records["session_meta"]], "source"
    )
    cli_version = _one_value(
        [row.get("cli_version") for row in records["session_meta"]], "cli_version"
    )
    model = _one_value(
        [
            row.get("model")
            for row in records["turn_context"]
            if row.get("turn_id") == turn_id
        ],
        f"model for turn {turn_id}",
    )

    starts = [
        row
        for row in records["task_events"]
        if row.get("turn_id") == turn_id and row.get("event_type") == "task_started"
    ]
    completes = [
        row
        for row in records["task_events"]
        if row.get("turn_id") == turn_id and row.get("event_type") == "task_complete"
    ]
    if len(starts) != 1 or len(completes) != 1:
        raise ValueError(
            f"turn {turn_id} requires exactly one start and completion event"
        )
    start_at = _timestamp(starts[0].get("timestamp"), "task_started.timestamp")
    complete_at = _timestamp(completes[0].get("timestamp"), "task_complete.timestamp")
    if complete_at < start_at:
        raise ValueError(f"turn {turn_id} completed before it started")
    duration_ms = _non_negative_int(
        completes[0].get("duration_ms"), "task_complete.duration_ms"
    )
    if duration_ms <= 0:
        raise ValueError("task_complete.duration_ms must be positive")

    token_events: list[dict[str, Any]] = []
    prior_token_event: dict[str, Any] | None = None
    for event in records["token_events"]:
        event_at = _timestamp(event.get("timestamp"), "token_count.timestamp")
        if event_at < start_at:
            if (
                prior_token_event is None
                or _timestamp(
                    prior_token_event.get("timestamp"), "prior token_count.timestamp"
                )
                < event_at
            ):
                prior_token_event = event
        elif event_at <= complete_at:
            token_events.append(event)
    if not token_events:
        raise ValueError(f"turn {turn_id} contains no provider token_count events")
    token_events.sort(
        key=lambda event: _timestamp(event["timestamp"], "token_count.timestamp")
    )
    summed = _sum_token_usage(token_events)
    _validate_cumulative_delta(token_events, prior_token_event, summed)

    calls: dict[str, dict[str, str]] = {}
    outputs: dict[str, str] = {}
    for item in records["tool_items"]:
        item_at = _timestamp(item.get("timestamp"), "response_item.timestamp")
        if not (start_at <= item_at <= complete_at):
            continue
        call_id = item.get("call_id")
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("selected tool event has no call_id")
        item_type = str(item.get("item_type") or "")
        if item_type not in TOOL_ITEM_TYPES:
            raise ValueError(f"selected tool event has unsupported type {item_type}")
        if item_type in TOOL_CALL_TYPES:
            name = _non_empty_string(item.get("name"), f"{item_type}.name")
            if name != name.strip():
                raise ValueError(
                    f"{item_type}.name must not contain surrounding whitespace"
                )
            candidate = {"item_type": item_type, "name": name}
            existing = calls.get(call_id)
            if existing is not None:
                if existing != candidate:
                    raise ValueError(
                        f"conflicting duplicate {item_type} for call_id {call_id}"
                    )
                continue
            calls[call_id] = candidate
            continue

        existing_output_type = outputs.get(call_id)
        if existing_output_type is not None:
            if existing_output_type != item_type:
                raise ValueError(f"conflicting duplicate output for call_id {call_id}")
            # Identical cached/repeated outputs are one response for this call ID.
            continue
        outputs[call_id] = item_type
    missing_outputs = sorted(set(calls) - set(outputs))
    orphan_outputs = sorted(set(outputs) - set(calls))
    if missing_outputs or orphan_outputs:
        raise ValueError(
            "tool-call evidence is incomplete: "
            f"missing_outputs={missing_outputs}, orphan_outputs={orphan_outputs}"
        )
    mismatched_outputs = sorted(
        call_id
        for call_id, call in calls.items()
        if outputs[call_id] != EXPECTED_OUTPUT_TYPES[call["item_type"]]
    )
    if mismatched_outputs:
        raise ValueError(
            "tool-call output types do not match their calls: "
            + ", ".join(mismatched_outputs)
        )

    rollout_tool_calls = [
        {"call_id": call_id, "name": calls[call_id]["name"]}
        for call_id in sorted(calls)
    ]
    tmcp_round_trips = sum(
        1
        for call_id, call in calls.items()
        if call_id in outputs and call["name"] in TMCP_TOOL_NAMES
    )

    return {
        "schema": "codex-rollout-turn-metrics-v0.1",
        "status": "incomplete",
        "trace_source": "codex-host",
        "session_id": session_id,
        "turn_id": turn_id,
        "provider": provider,
        "model": model,
        "host_runtime": {
            "originator": originator,
            "source": source,
            "cli_version": cli_version,
        },
        "provider_metrics_available": {
            "wall_time_ms": duration_ms,
            "input_tokens": summed["input_tokens"],
            "output_tokens": summed["output_tokens"],
            "model_round_trips": len(token_events),
            "tool_round_trips": len(calls),
            TMCP_ROUND_TRIP_FIELD: tmcp_round_trips,
        },
        "rollout_tool_calls": rollout_tool_calls,
        "provider_token_detail": {
            field: summed[field]
            for field in (
                "cached_input_tokens",
                "cache_write_input_tokens",
                "reasoning_output_tokens",
                "total_tokens",
            )
        },
        "missing_host_metrics": list(HOST_COUNTER_FIELDS),
        "scorer_ready": False,
    }


def _read_host_observation(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if value.get("schema") != HOST_OBSERVATION_SCHEMA:
        raise ValueError(f"host observation must use schema {HOST_OBSERVATION_SCHEMA}")
    return value


def merge_host_observation(
    extracted: dict[str, Any], observation: dict[str, Any]
) -> dict[str, Any]:
    for field in ("session_id", "turn_id"):
        if observation.get(field) != extracted[field]:
            raise ValueError(
                f"host observation {field} does not match rollout evidence"
            )
    counters = observation.get("host_metrics")
    if not isinstance(counters, dict) or set(counters) not in (
        set(HOST_COUNTER_FIELDS),
        set(HOST_OBSERVATION_COUNTER_FIELDS),
    ):
        raise ValueError("host observation host_metrics are incomplete or unexpected")
    validated = {
        field: _non_negative_int(counters.get(field), f"host_metrics.{field}")
        for field in HOST_COUNTER_FIELDS
    }
    extracted_metrics = extracted.get("provider_metrics_available")
    if not isinstance(extracted_metrics, dict):
        raise ValueError("rollout provider metrics are missing")
    derived_tmcp_round_trips = _non_negative_int(
        extracted_metrics.get(TMCP_ROUND_TRIP_FIELD),
        f"rollout provider metrics.{TMCP_ROUND_TRIP_FIELD}",
    )
    if TMCP_ROUND_TRIP_FIELD in counters:
        observed_tmcp_round_trips = _non_negative_int(
            counters.get(TMCP_ROUND_TRIP_FIELD),
            f"host_metrics.{TMCP_ROUND_TRIP_FIELD}",
        )
        if observed_tmcp_round_trips != derived_tmcp_round_trips:
            raise ValueError(
                "host observation tmcp_model_visible_round_trips does not match "
                "the rollout-derived value"
            )
    trace = observation.get("trace")
    if not isinstance(trace, dict):
        raise ValueError("host observation trace must be an object")
    forbidden = {"trace_source", "provider", "model", "provider_metrics"} & set(trace)
    if forbidden:
        raise ValueError(
            "host observation cannot override rollout-owned fields: "
            + ", ".join(sorted(forbidden))
        )
    required_trace_fields = {
        "run_id",
        "task_id",
        "fresh_context",
        "stratum",
        "human_expected_action",
        "human_label_blinded",
        "review_or_audit_task",
        "admission",
        "routing",
    }
    missing_trace_fields = sorted(required_trace_fields - set(trace))
    if missing_trace_fields:
        raise ValueError(
            "host observation trace is missing fields: "
            + ", ".join(missing_trace_fields)
        )
    for field in ("run_id", "task_id", "stratum", "human_expected_action"):
        _non_empty_string(trace.get(field), f"trace.{field}")
    for field in ("fresh_context", "human_label_blinded", "review_or_audit_task"):
        if not isinstance(trace.get(field), bool):
            raise ValueError(f"trace.{field} must be a boolean")
    admission = trace["admission"]
    arm = trace.get("arm")
    baseline_arm = arm == "normal-codex-routing"
    if admission is None and not baseline_arm:
        raise ValueError(
            "host observation trace.admission may be null only for the "
            "normal-codex-routing arm"
        )
    if baseline_arm and admission is not None:
        raise ValueError(
            "normal-codex-routing host observation trace.admission must be null"
        )
    if admission is not None and not isinstance(admission, dict):
        raise ValueError("host observation trace.admission must be an object")
    if isinstance(admission, dict):
        for field in ("mode", "action", "recommended_action", "policy_version"):
            _non_empty_string(admission.get(field), f"trace.admission.{field}")
    routing = trace["routing"]
    if not isinstance(routing, dict):
        raise ValueError("host observation trace.routing must be an object")
    routing_mode = _non_empty_string(routing.get("mode"), "trace.routing.mode")
    expected_packet_injected = {
        "normal": False,
        "shadow": False,
        "bypass": False,
        "normal_after_bypass": False,
        "substitution": True,
    }.get(routing_mode)
    if expected_packet_injected is None:
        raise ValueError(
            f"host observation trace.routing.mode is unsupported: {routing_mode}"
        )
    if routing.get("packet_injected") is not expected_packet_injected:
        raise ValueError(
            "host observation trace.routing.packet_injected is inconsistent with "
            f"routing mode {routing_mode}"
        )
    for field in (
        "selected_source_count",
        "review_source_count",
        "normal_full_skill_load_count",
        "supplemental_full_skill_load_count",
    ):
        _non_negative_int(routing.get(field), f"trace.routing.{field}")
    if routing["supplemental_full_skill_load_count"] != 0:
        raise ValueError(
            "host observation cannot include supplemental full-skill loads"
        )
    if baseline_arm and routing_mode != "normal":
        raise ValueError(
            "normal-codex-routing host observation must use routing mode normal"
        )
    if routing_mode == "substitution" and routing["normal_full_skill_load_count"] != 0:
        raise ValueError("substitution routing cannot include normal full-skill loads")
    provider_metrics = {**extracted["provider_metrics_available"], **validated}
    return {
        "schema": "codex-rollout-turn-metrics-v0.1",
        "status": "complete",
        "scorer_ready": True,
        "session_id": extracted["session_id"],
        "turn_id": extracted["turn_id"],
        "host_runtime": extracted["host_runtime"],
        "provider_token_detail": extracted["provider_token_detail"],
        "trace": {
            **trace,
            "trace_source": "codex-host",
            "provider": extracted["provider"],
            "model": extracted["model"],
            "provider_metrics": provider_metrics,
        },
    }


def finalize_terminal_turn(
    extracted: dict[str, Any], observation: dict[str, Any] | None
) -> dict[str, Any]:
    """Require the native host companion before accepting a terminal rollout."""

    if observation is None:
        raise HostObservationUnavailableError()
    return merge_host_observation(extracted, observation)


def build_attribution_availability_receipt(
    extracted: dict[str, Any], finalized: dict[str, Any] | None
) -> dict[str, Any]:
    """Build a redacted, non-promoting terminal attribution receipt."""

    common = {
        "schema": ATTRIBUTION_AVAILABILITY_SCHEMA,
        "session_id": _non_empty_string(extracted.get("session_id"), "session_id"),
        "turn_id": _non_empty_string(extracted.get("turn_id"), "turn_id"),
        "promotion_authorized": False,
        "canary_authorized": False,
    }
    if finalized is None:
        return {
            **common,
            "attribution_status": UNAVAILABLE,
            "scorer_ready": False,
            "disposition": UNAVAILABLE_ATTRIBUTION_DISPOSITION,
            "missing_host_metrics": list(HOST_COUNTER_FIELDS),
        }

    if (
        finalized.get("status") != "complete"
        or finalized.get("scorer_ready") is not True
        or finalized.get("session_id") != common["session_id"]
        or finalized.get("turn_id") != common["turn_id"]
    ):
        raise ValueError("finalized attribution result is incomplete or mismatched")
    trace = finalized.get("trace")
    metrics = trace.get("provider_metrics") if isinstance(trace, dict) else None
    if not isinstance(metrics, dict):
        raise ValueError("finalized attribution result is missing provider metrics")
    skill_read_calls = _non_negative_int(
        metrics.get("skill_read_calls"), "provider_metrics.skill_read_calls"
    )
    skill_read_input_tokens = _non_negative_int(
        metrics.get("skill_read_input_tokens"),
        "provider_metrics.skill_read_input_tokens",
    )
    if skill_read_calls == 0 and skill_read_input_tokens != 0:
        raise ValueError("zero skill-read calls cannot have skill-read input tokens")
    attribution_status = (
        COMPLETE_ZERO
        if skill_read_calls == 0 and skill_read_input_tokens == 0
        else COMPLETE_EXACT
    )
    return {
        **common,
        "attribution_status": attribution_status,
        "scorer_ready": True,
    }


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"output already exists: {path}")
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--turn-id", required=True)
    parser.add_argument("--host-observation", type=Path)
    parser.add_argument("--availability-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if (
        args.availability_receipt
        and args.output
        and args.availability_receipt.resolve() == args.output.resolve()
    ):
        raise ValueError(
            "availability receipt and metrics output must use different paths"
        )

    result = extract_turn(args.rollout, args.turn_id)
    observation = (
        _read_host_observation(args.host_observation) if args.host_observation else None
    )
    try:
        finalized = finalize_terminal_turn(result, observation)
    except HostObservationUnavailableError:
        if args.availability_receipt:
            _write_new_json(
                args.availability_receipt,
                build_attribution_availability_receipt(result, None),
            )
        raise
    if args.availability_receipt:
        _write_new_json(
            args.availability_receipt,
            build_attribution_availability_receipt(result, finalized),
        )
    result = finalized
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
