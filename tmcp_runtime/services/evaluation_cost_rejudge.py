"""Validation and promotion coverage for condition-blind cost sidecars."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


COST_REJUDGMENT_SCHEMA = "tmcp-skill-eval-cost-rejudgment-v0.1"


def trace_source_digest(trace: Mapping[str, Any]) -> str:
    """Return the stable digest that binds a cost rejudgment to one trace."""

    encoded = json.dumps(trace, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_cost_rejudgments(
    traces: Sequence[Mapping[str, Any]], payload: Mapping[str, Any] | None
) -> dict[str, bool] | None:
    """Validate complete, blind cost adjudications without touching raw verdicts."""

    if payload is None:
        return None
    if payload.get("schema") != COST_REJUDGMENT_SCHEMA:
        raise ValueError(f"cost_rejudgments_json must use {COST_REJUDGMENT_SCHEMA}.")
    entries = payload.get("rejudgments")
    if not isinstance(entries, list):
        raise ValueError("cost_rejudgments_json.rejudgments must be a list.")
    trace_by_id = {
        str(trace.get("trace_id") or ""): trace
        for trace in traces
        if str(trace.get("trace_id") or "")
    }
    if len(trace_by_id) != len(traces):
        raise ValueError(
            "cost rejudgment requires a non-empty trace_id for every trace."
        )
    if len(entries) != len(trace_by_id):
        raise ValueError(
            "cost rejudgment coverage must include every supplied trace exactly once."
        )
    verdicts: dict[str, bool] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("cost rejudgments must be objects.")
        trace_id = str(entry.get("trace_id") or "")
        if not trace_id or trace_id not in trace_by_id or trace_id in verdicts:
            raise ValueError(
                "cost rejudgments must use unique supplied trace_id values."
            )
        if entry.get("source_trace_digest") != trace_source_digest(
            trace_by_id[trace_id]
        ):
            raise ValueError(
                "cost rejudgment source_trace_digest does not match supplied trace."
            )
        cost_regression = entry.get("cost_regression")
        if not isinstance(cost_regression, bool):
            raise ValueError("cost rejudgment cost_regression must be boolean.")
        rationale = entry.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("cost rejudgment rationale must be non-empty.")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("cost rejudgment evidence must be a non-empty list.")
        c1_statuses: set[str] = set()
        for item in evidence:
            if not isinstance(item, Mapping):
                raise ValueError("cost rejudgment evidence entries must be objects.")
            if not str(item.get("citation") or "").strip():
                raise ValueError("cost rejudgment evidence requires a citation.")
            criterion = str(item.get("criterion") or "")
            if criterion == "C1" or criterion.startswith("C1:"):
                status = str(item.get("status") or "")
                if status in {"necessary", "materially_unnecessary"}:
                    c1_statuses.add(status)
        expected_status = "materially_unnecessary" if cost_regression else "necessary"
        if c1_statuses != {expected_status}:
            raise ValueError(
                "cost rejudgment C1 status must agree with cost_regression."
            )
        provenance = entry.get("provenance")
        if not isinstance(provenance, Mapping) or not all(
            provenance.get(field) is True
            for field in (
                "judge_blinded",
                "isolated_session",
                "fresh_session",
                "condition_hidden",
                "source_artifact_only",
            )
        ):
            raise ValueError(
                "cost rejudgment provenance must prove fresh blinded review."
            )
        verdicts[trace_id] = cost_regression
    return verdicts


def cost_rejudge_requirement(
    plan: Mapping[str, Any],
    traces: Sequence[Mapping[str, Any]],
    cost_rejudgments: Mapping[str, bool] | None,
) -> dict[str, Any]:
    """Report whether a plan-preregistered cost sidecar covers its source traces."""

    experiment = plan.get("experiment")
    policy = (
        experiment.get("cost_rejudge_policy")
        if isinstance(experiment, Mapping)
        else None
    )
    if (
        not isinstance(policy, Mapping)
        or policy.get("complete_before_promotion") is not True
    ):
        return {"required": False, "status": "not_required"}

    expected_trace_count = policy.get("expected_trace_count")
    if not isinstance(expected_trace_count, int) or expected_trace_count < 1:
        return {
            "required": True,
            "status": "invalid_policy",
            "expected_trace_count": expected_trace_count,
        }
    trace_ids = [str(trace.get("trace_id") or "") for trace in traces]
    adjudicated_trace_count = (
        len(cost_rejudgments) if cost_rejudgments is not None else 0
    )
    result: dict[str, Any] = {
        "required": True,
        "expected_trace_count": expected_trace_count,
        "source_trace_count": len(trace_ids),
        "adjudicated_trace_count": adjudicated_trace_count,
    }
    if (
        len(trace_ids) != expected_trace_count
        or len(set(trace_ids)) != expected_trace_count
        or "" in trace_ids
    ):
        return {**result, "status": "incomplete_source_traces"}
    if cost_rejudgments is None:
        return {**result, "status": "missing"}
    if set(cost_rejudgments) != set(trace_ids):
        return {**result, "status": "incomplete"}
    return {**result, "status": "complete"}
