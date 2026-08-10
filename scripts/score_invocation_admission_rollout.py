#!/usr/bin/env python3
"""Score provider-native shadow and substitution-canary TMCP rollout traces.

The scorer deliberately does not launch models or estimate provider measures.
It accepts only complete host traces, rejects additive TMCP routing, and keeps
shadow admission as a hard prerequisite for canary promotion.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "examples" / "workflows" / "invocation-admission-rollout-v0.7.json"
)
ARMS = frozenset({"normal-codex-routing", "tmcp-admitted-substitution"})
STRATA = frozenset({"positive", "negative", "ambiguous"})
ATTRIBUTION_AVAILABILITY_SCHEMA = (
    "tmcp-invocation-admission-attribution-availability-v0.11"
)
ATTRIBUTION_READINESS_SCHEMA = "tmcp-invocation-admission-attribution-readiness-v0.11"
ATTRIBUTION_STATUSES = frozenset({"complete-zero", "complete-exact", "unavailable"})
HOST_COUNTER_FIELDS = frozenset({"skill_read_calls", "skill_read_input_tokens"})
UNAVAILABLE_ATTRIBUTION_DISPOSITION = "unavailable-attribution"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    if not rows:
        raise ValueError(f"{path} contains no observations")
    return rows


def _mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot calculate a median from no values")
    return float(statistics.median(values))


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise ValueError("rate denominator must be positive")
    return numerator / denominator


def _non_negative_number(value: object, field: str, *, positive: bool = False) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if number < 0 or (positive and number <= 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{field} must be {qualifier}")
    return number


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != "tmcp-invocation-admission-rollout-v0.7":
        raise ValueError("rollout manifest must use schema v0.7")
    required_metrics = set(manifest.get("required_provider_metrics") or [])
    expected_metrics = {
        "wall_time_ms",
        "input_tokens",
        "output_tokens",
        "model_round_trips",
        "tool_round_trips",
        "skill_read_calls",
        "skill_read_input_tokens",
        "tmcp_model_visible_round_trips",
    }
    if required_metrics != expected_metrics:
        raise ValueError("required provider metrics do not match the v0.7 contract")
    if not manifest.get("preregistration", {}).get("atom_variant_excluded"):
        raise ValueError("atom variants must remain excluded from this rollout")


def _validate_stratum(row: dict[str, Any], run_id: str) -> str:
    if not str(row.get("task_id") or ""):
        raise ValueError(f"{run_id}: task_id is required")
    if not isinstance(row.get("review_or_audit_task"), bool):
        raise ValueError(f"{run_id}: review_or_audit_task must be boolean")
    stratum = str(row.get("stratum") or "")
    if stratum not in STRATA:
        raise ValueError(f"{run_id}: invalid task stratum")
    expected = str(row.get("human_expected_action") or "")
    if expected not in {"compose", "bypass"}:
        raise ValueError(f"{run_id}: invalid human_expected_action")
    if row.get("human_label_blinded") is not True:
        raise ValueError(f"{run_id}: human action label was not blinded")
    if stratum == "positive" and expected != "compose":
        raise ValueError(f"{run_id}: positive tasks must be labeled compose")
    if stratum == "negative" and expected != "bypass":
        raise ValueError(f"{run_id}: negative tasks must be labeled bypass")
    return stratum


def _validate_host_trace(row: dict[str, Any], run_id: str) -> None:
    if row.get("trace_source") != "codex-host":
        raise ValueError(f"{run_id}: trace_source must be codex-host")
    if not str(row.get("provider") or "") or not str(row.get("model") or ""):
        raise ValueError(f"{run_id}: provider and model are required")
    if row.get("fresh_context") is not True:
        raise ValueError(f"{run_id}: run did not use a fresh context")


def _validate_admission(
    admission: object, run_id: str, *, shadow: bool
) -> dict[str, Any]:
    if not isinstance(admission, dict):
        raise ValueError(f"{run_id}: admission must be an object")
    if shadow:
        if admission.get("mode") != "shadow" or admission.get("action") != "shadow":
            raise ValueError(f"{run_id}: shadow admission mode/action mismatch")
    else:
        if admission.get("mode") != "automatic":
            raise ValueError(f"{run_id}: canary admission must be automatic")
        if admission.get("action") not in {"compose", "bypass"}:
            raise ValueError(f"{run_id}: invalid automatic admission action")
    if admission.get("recommended_action") not in {"compose", "bypass"}:
        raise ValueError(f"{run_id}: invalid recommended admission action")
    if not str(admission.get("policy_version") or ""):
        raise ValueError(f"{run_id}: missing admission policy version")
    return admission


def _validate_routing(routing: object, run_id: str) -> dict[str, Any]:
    if not isinstance(routing, dict):
        raise ValueError(f"{run_id}: routing must be an object")
    for field in (
        "selected_source_count",
        "review_source_count",
        "normal_full_skill_load_count",
        "supplemental_full_skill_load_count",
    ):
        _non_negative_int(routing.get(field), f"{run_id}: routing.{field}")
    if not isinstance(routing.get("packet_injected"), bool):
        raise ValueError(f"{run_id}: routing.packet_injected must be boolean")
    return routing


def _validate_provider_metrics(
    metrics: object, run_id: str, required: set[str]
) -> dict[str, Any]:
    if not isinstance(metrics, dict) or set(metrics) != required:
        raise ValueError(f"{run_id}: provider metrics are incomplete or unexpected")
    _non_negative_number(
        metrics["wall_time_ms"], f"{run_id}: wall_time_ms", positive=True
    )
    for field in ("input_tokens", "output_tokens", "skill_read_input_tokens"):
        _non_negative_int(metrics[field], f"{run_id}: {field}")
    for field in (
        "model_round_trips",
        "tool_round_trips",
        "skill_read_calls",
        "tmcp_model_visible_round_trips",
    ):
        _non_negative_int(metrics[field], f"{run_id}: {field}")
    if metrics["model_round_trips"] < 1:
        raise ValueError(f"{run_id}: model_round_trips must be positive")
    return metrics


def _gate(passed: bool, **details: Any) -> dict[str, Any]:
    return {"status": "passed" if passed else "failed", "passed": passed, **details}


def score_attribution_readiness(
    manifest: dict[str, Any], receipts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Aggregate redacted availability only; never score or authorize a rollout."""

    _validate_manifest(manifest)
    if not receipts:
        raise ValueError("attribution readiness requires at least one receipt")
    common_fields = {
        "schema",
        "session_id",
        "turn_id",
        "attribution_status",
        "scorer_ready",
        "promotion_authorized",
        "canary_authorized",
    }
    seen: set[tuple[str, str]] = set()
    counts = Counter({status: 0 for status in ATTRIBUTION_STATUSES})
    for receipt in receipts:
        if receipt.get("schema") != ATTRIBUTION_AVAILABILITY_SCHEMA:
            raise ValueError("attribution receipt must use the v0.11 schema")
        session_id = _non_empty_string(receipt.get("session_id"), "session_id")
        turn_id = _non_empty_string(receipt.get("turn_id"), "turn_id")
        identity = (session_id, turn_id)
        if identity in seen:
            raise ValueError("attribution receipts contain a duplicate session/turn")
        seen.add(identity)
        status = receipt.get("attribution_status")
        if status not in ATTRIBUTION_STATUSES:
            raise ValueError("attribution receipt has an unsupported status")
        expected_fields = set(common_fields)
        if status == "unavailable":
            expected_fields.update({"disposition", "missing_host_metrics"})
            if receipt.get("scorer_ready") is not False:
                raise ValueError("unavailable attribution cannot be scorer-ready")
            if receipt.get("disposition") != UNAVAILABLE_ATTRIBUTION_DISPOSITION:
                raise ValueError("unavailable attribution has an invalid disposition")
            missing = receipt.get("missing_host_metrics")
            if (
                not isinstance(missing, list)
                or len(missing) != len(HOST_COUNTER_FIELDS)
                or set(missing) != HOST_COUNTER_FIELDS
            ):
                raise ValueError("unavailable attribution has invalid missing metrics")
        elif receipt.get("scorer_ready") is not True:
            raise ValueError("complete attribution must be scorer-ready")
        if set(receipt) != expected_fields:
            raise ValueError("attribution receipt fields are incomplete or unexpected")
        if receipt.get("promotion_authorized") is not False:
            raise ValueError("attribution receipt cannot authorize promotion")
        if receipt.get("canary_authorized") is not False:
            raise ValueError("attribution receipt cannot authorize a canary")
        counts[str(status)] += 1

    total = len(receipts)
    complete = counts["complete-zero"] + counts["complete-exact"]
    coverage = complete / total
    eligible = complete == total
    gates = {
        "complete_attribution_coverage": _gate(
            eligible,
            complete_turns=complete,
            unavailable_turns=counts["unavailable"],
            total_turns=total,
            observed_ratio=coverage,
            required_ratio=1.0,
        )
    }
    return {
        "schema": ATTRIBUTION_READINESS_SCHEMA,
        "status": "ready" if eligible else "blocked",
        "shadow_score_eligible": eligible,
        "promotion_authorized": False,
        "canary_authorized": False,
        "turns_observed": total,
        "attribution_counts": dict(sorted(counts.items())),
        "attribution_coverage_ratio": coverage,
        "acceptance_gates": gates,
        "evidence_boundary": (
            "This report establishes attribution availability only. It does not "
            "score routing, quality, economics, shadow acceptance, or canary readiness."
        ),
    }


def score_shadow(
    manifest: dict[str, Any], traces: list[dict[str, Any]]
) -> dict[str, Any]:
    _validate_manifest(manifest)
    config = manifest["shadow"]
    acceptance = config["acceptance"]
    required = set(manifest["required_provider_metrics"])
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in traces:
        run_id = str(row.get("run_id") or "")
        if not run_id or run_id in seen:
            raise ValueError("shadow traces require unique non-empty run_id values")
        seen.add(run_id)
        _validate_host_trace(row, run_id)
        stratum = _validate_stratum(row, run_id)
        admission = _validate_admission(row.get("admission"), run_id, shadow=True)
        routing = _validate_routing(row.get("routing"), run_id)
        metrics = _validate_provider_metrics(
            row.get("provider_metrics"), run_id, required
        )
        if routing["packet_injected"]:
            raise ValueError(f"{run_id}: shadow mode injected a packet")
        normalized.append(
            {
                **row,
                "stratum": stratum,
                "admission": admission,
                "routing": routing,
                "provider_metrics": metrics,
            }
        )

    counts = Counter(row["stratum"] for row in normalized)
    positive = [row for row in normalized if row["stratum"] == "positive"]
    negative = [row for row in normalized if row["stratum"] == "negative"]
    false_negatives = sum(
        row["admission"]["recommended_action"] == "bypass" for row in positive
    )
    false_positives = sum(
        row["admission"]["recommended_action"] == "compose" for row in negative
    )
    false_negative_rate = _rate(false_negatives, len(positive))
    false_positive_rate = _rate(false_positives, len(negative))
    non_review = [row for row in normalized if row.get("review_or_audit_task") is False]
    selected = sum(row["routing"]["selected_source_count"] for row in non_review)
    review = sum(row["routing"]["review_source_count"] for row in non_review)
    review_rate = review / selected if selected else 0.0
    model_visible = max(
        row["provider_metrics"]["tmcp_model_visible_round_trips"] for row in normalized
    )
    enough_strata = all(
        counts[stratum] >= int(config["minimum_tasks_per_stratum"])
        for stratum in STRATA
    )
    gates = {
        "sample_complete": _gate(
            len(normalized) >= int(config["minimum_tasks_total"]) and enough_strata,
            tasks=len(normalized),
            tasks_by_stratum=dict(counts),
        ),
        "false_positive_rate": _gate(
            false_positive_rate <= acceptance["maximum_false_positive_rate"],
            observed=false_positive_rate,
            maximum=acceptance["maximum_false_positive_rate"],
        ),
        "false_negative_rate": _gate(
            false_negative_rate <= acceptance["maximum_false_negative_rate"],
            observed=false_negative_rate,
            maximum=acceptance["maximum_false_negative_rate"],
        ),
        "review_source_rate_for_non_review_tasks": _gate(
            review_rate
            <= acceptance["maximum_review_source_rate_for_non_review_tasks"],
            observed=review_rate,
            maximum=acceptance["maximum_review_source_rate_for_non_review_tasks"],
        ),
        "host_side_only": _gate(
            model_visible <= acceptance["maximum_model_visible_tmcp_round_trips"],
            observed_maximum=model_visible,
            maximum=acceptance["maximum_model_visible_tmcp_round_trips"],
        ),
    }
    return {
        "schema": "tmcp-invocation-admission-shadow-score-v0.7",
        "status": "complete",
        "promotion_authorized": all(gate["passed"] for gate in gates.values()),
        "tasks_scored": len(normalized),
        "acceptance_gates": gates,
        "evidence_boundary": manifest["evidence_boundary"],
    }


def _validate_judgments(
    traces: list[dict[str, Any]], judgments: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    by_run: dict[str, dict[str, Any]] = {}
    required = {
        "run_id",
        "judge_blinded",
        "pass",
        "weighted_score",
        "verification_quality_score",
        "irrelevant_constraint_count",
        "unsafe_or_unjustified_action_count",
    }
    for row in judgments:
        if set(row) != required:
            raise ValueError("judge result fields do not match the v0.7 schema")
        run_id = str(row["run_id"])
        if not run_id or run_id in by_run:
            raise ValueError("judge results require unique non-empty run_id values")
        if row["judge_blinded"] is not True or not isinstance(row["pass"], bool):
            raise ValueError(f"{run_id}: judgment was not blinded or pass is invalid")
        for field in ("weighted_score", "verification_quality_score"):
            value = _non_negative_number(row[field], f"{run_id}: {field}")
            if value > 1:
                raise ValueError(f"{run_id}: {field} must be within 0..1")
        for field in (
            "irrelevant_constraint_count",
            "unsafe_or_unjustified_action_count",
        ):
            _non_negative_int(row[field], f"{run_id}: {field}")
        by_run[run_id] = row
    trace_ids = {str(row["run_id"]) for row in traces}
    if set(by_run) != trace_ids:
        raise ValueError("judge corpus does not exactly match canary traces")
    return by_run


def score_canary(
    manifest: dict[str, Any],
    traces: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
    shadow_report: dict[str, Any],
) -> dict[str, Any]:
    _validate_manifest(manifest)
    if manifest["canary"].get("requires_passed_shadow") and (
        shadow_report.get("schema") != "tmcp-invocation-admission-shadow-score-v0.7"
        or shadow_report.get("status") != "complete"
        or not shadow_report.get("promotion_authorized")
    ):
        raise ValueError("canary scoring requires a complete passed v0.7 shadow report")
    config = manifest["canary"]
    acceptance = config["acceptance"]
    required = set(manifest["required_provider_metrics"])
    seen: set[str] = set()
    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    normalized: list[dict[str, Any]] = []
    for row in traces:
        run_id = str(row.get("run_id") or "")
        pair_id = str(row.get("pair_id") or "")
        arm = str(row.get("arm") or "")
        if not run_id or run_id in seen or not pair_id or arm not in ARMS:
            raise ValueError(
                "canary traces require unique runs, pair ids, and valid arms"
            )
        seen.add(run_id)
        _validate_host_trace(row, run_id)
        pair_order = row.get("pair_order")
        if pair_order not in {1, 2}:
            raise ValueError(f"{run_id}: pair_order must be 1 or 2")
        stratum = _validate_stratum(row, run_id)
        routing = _validate_routing(row.get("routing"), run_id)
        metrics = _validate_provider_metrics(
            row.get("provider_metrics"), run_id, required
        )
        normalized_row = {
            **row,
            "stratum": stratum,
            "routing": routing,
            "provider_metrics": metrics,
        }
        if arm == "normal-codex-routing":
            if (
                row.get("admission") is not None
                or routing["packet_injected"]
                or routing.get("mode") != "normal"
            ):
                raise ValueError(f"{run_id}: baseline arm contains TMCP intervention")
        else:
            admission = _validate_admission(row.get("admission"), run_id, shadow=False)
            normalized_row["admission"] = admission
            action = admission["action"]
            if action == "compose":
                if (
                    routing.get("mode") != "substitution"
                    or not routing["packet_injected"]
                ):
                    raise ValueError(
                        f"{run_id}: admitted packet did not use substitution"
                    )
                if routing["normal_full_skill_load_count"] != 0:
                    raise ValueError(
                        f"{run_id}: admitted run retained normal full-skill loads"
                    )
                if routing["supplemental_full_skill_load_count"] != 0:
                    raise ValueError(
                        f"{run_id}: admitted run supplemented normal routing"
                    )
            elif (
                routing["packet_injected"]
                or routing.get("mode") != "normal_after_bypass"
            ):
                raise ValueError(
                    f"{run_id}: bypass did not fall through to normal routing"
                )
        bucket = pairs.setdefault(pair_id, {})
        if arm in bucket:
            raise ValueError(f"{pair_id}: duplicate canary arm")
        bucket[arm] = normalized_row
        normalized.append(normalized_row)

    for pair_id, arms in pairs.items():
        if set(arms) != ARMS:
            raise ValueError(f"{pair_id}: incomplete canary pair")
        baseline = arms["normal-codex-routing"]
        tmcp = arms["tmcp-admitted-substitution"]
        identity = (
            baseline.get("task_id"),
            baseline["stratum"],
            baseline["human_expected_action"],
        )
        compared = (tmcp.get("task_id"), tmcp["stratum"], tmcp["human_expected_action"])
        if identity != compared:
            raise ValueError(f"{pair_id}: paired task identity mismatch")
        if (
            baseline["provider"] != tmcp["provider"]
            or baseline["model"] != tmcp["model"]
        ):
            raise ValueError(f"{pair_id}: provider or model mismatch")
        if {baseline["pair_order"], tmcp["pair_order"]} != {1, 2}:
            raise ValueError(f"{pair_id}: pair order is incomplete")

    judgment_by_run = _validate_judgments(normalized, judgments)
    pair_rows = list(pairs.values())
    counts = Counter(
        arms["tmcp-admitted-substitution"]["stratum"] for arms in pair_rows
    )
    enough_strata = all(
        counts[stratum] >= int(config["minimum_pairs_per_stratum"])
        for stratum in STRATA
    )
    tmcp_rows = [arms["tmcp-admitted-substitution"] for arms in pair_rows]
    positive = [row for row in tmcp_rows if row["stratum"] == "positive"]
    negative = [row for row in tmcp_rows if row["stratum"] == "negative"]
    false_negative_rate = _rate(
        sum(row["admission"]["action"] == "bypass" for row in positive), len(positive)
    )
    false_positive_rate = _rate(
        sum(row["admission"]["action"] == "compose" for row in negative), len(negative)
    )
    non_review_composed = [
        row
        for row in tmcp_rows
        if row.get("review_or_audit_task") is False
        and row["admission"]["action"] == "compose"
    ]
    selected = sum(
        row["routing"]["selected_source_count"] for row in non_review_composed
    )
    review = sum(row["routing"]["review_source_count"] for row in non_review_composed)
    review_rate = review / selected if selected else 0.0

    baseline_scores = [
        float(judgment_by_run[arms["normal-codex-routing"]["run_id"]]["weighted_score"])
        for arms in pair_rows
    ]
    tmcp_scores = [
        float(
            judgment_by_run[arms["tmcp-admitted-substitution"]["run_id"]][
                "weighted_score"
            ]
        )
        for arms in pair_rows
    ]
    baseline_irrelevant = _mean(
        [
            judgment_by_run[arms["normal-codex-routing"]["run_id"]][
                "irrelevant_constraint_count"
            ]
            for arms in pair_rows
        ]
    )
    tmcp_irrelevant = _mean(
        [
            judgment_by_run[arms["tmcp-admitted-substitution"]["run_id"]][
                "irrelevant_constraint_count"
            ]
            for arms in pair_rows
        ]
    )
    baseline_unsafe = sum(
        judgment_by_run[arms["normal-codex-routing"]["run_id"]][
            "unsafe_or_unjustified_action_count"
        ]
        for arms in pair_rows
    )
    tmcp_unsafe = sum(
        judgment_by_run[arms["tmcp-admitted-substitution"]["run_id"]][
            "unsafe_or_unjustified_action_count"
        ]
        for arms in pair_rows
    )

    wall_ratios: list[float] = []
    token_ratios: list[float] = []
    tool_deltas: list[float] = []
    skill_read_deltas: list[float] = []
    skill_read_token_deltas: list[float] = []
    model_deltas: list[float] = []
    for arms in pair_rows:
        baseline = arms["normal-codex-routing"]["provider_metrics"]
        tmcp = arms["tmcp-admitted-substitution"]["provider_metrics"]
        wall_ratios.append(tmcp["wall_time_ms"] / baseline["wall_time_ms"])
        baseline_tokens = baseline["input_tokens"] + baseline["output_tokens"]
        tmcp_tokens = tmcp["input_tokens"] + tmcp["output_tokens"]
        if baseline_tokens <= 0:
            raise ValueError("baseline total token count must be positive")
        token_ratios.append(tmcp_tokens / baseline_tokens)
        model_deltas.append(tmcp["model_round_trips"] - baseline["model_round_trips"])
        tool_deltas.append(tmcp["tool_round_trips"] - baseline["tool_round_trips"])
        skill_read_deltas.append(
            tmcp["skill_read_calls"] - baseline["skill_read_calls"]
        )
        skill_read_token_deltas.append(
            tmcp["skill_read_input_tokens"] - baseline["skill_read_input_tokens"]
        )

    median_wall_ratio = _median(wall_ratios)
    median_token_ratio = _median(token_ratios)
    median_tool_delta = _median(tool_deltas)
    median_skill_read_delta = _median(skill_read_deltas)
    median_skill_read_token_delta = _median(skill_read_token_deltas)
    median_model_delta = _median(model_deltas)
    baseline_first = sum(
        arms["normal-codex-routing"]["pair_order"] == 1 for arms in pair_rows
    )
    tmcp_first = len(pair_rows) - baseline_first
    model_visible = max(
        row["provider_metrics"]["tmcp_model_visible_round_trips"] for row in tmcp_rows
    )
    quality_floor = _mean(baseline_scores) - acceptance["quality_noninferiority_margin"]
    gates = {
        "shadow_prerequisite": _gate(True, schema=shadow_report.get("schema")),
        "sample_complete": _gate(
            len(pair_rows) >= int(config["minimum_pairs_total"]) and enough_strata,
            pairs=len(pair_rows),
            pairs_by_stratum=dict(counts),
        ),
        "pair_order_counterbalanced": _gate(
            abs(baseline_first - tmcp_first) <= 1,
            baseline_first=baseline_first,
            tmcp_first=tmcp_first,
        ),
        "quality_noninferiority": _gate(
            _mean(tmcp_scores) >= quality_floor,
            tmcp_mean=_mean(tmcp_scores),
            baseline_mean=_mean(baseline_scores),
            margin=acceptance["quality_noninferiority_margin"],
        ),
        "false_positive_rate": _gate(
            false_positive_rate <= acceptance["maximum_false_positive_rate"],
            observed=false_positive_rate,
            maximum=acceptance["maximum_false_positive_rate"],
        ),
        "false_negative_rate": _gate(
            false_negative_rate <= acceptance["maximum_false_negative_rate"],
            observed=false_negative_rate,
            maximum=acceptance["maximum_false_negative_rate"],
        ),
        "review_source_rate_for_non_review_tasks": _gate(
            review_rate
            <= acceptance["maximum_review_source_rate_for_non_review_tasks"],
            observed=review_rate,
            maximum=acceptance["maximum_review_source_rate_for_non_review_tasks"],
        ),
        "irrelevant_constraints": _gate(
            tmcp_irrelevant - baseline_irrelevant
            <= acceptance["maximum_irrelevant_constraint_mean_increase"],
            observed_mean_increase=tmcp_irrelevant - baseline_irrelevant,
            maximum=acceptance["maximum_irrelevant_constraint_mean_increase"],
        ),
        "no_safety_regression": _gate(
            tmcp_unsafe - baseline_unsafe
            <= acceptance["maximum_unsafe_action_increase"],
            observed_increase=tmcp_unsafe - baseline_unsafe,
            maximum=acceptance["maximum_unsafe_action_increase"],
        ),
        "provider_wall_time": _gate(
            median_wall_ratio <= acceptance["maximum_median_paired_wall_time_ratio"],
            observed_median_ratio=median_wall_ratio,
            maximum=acceptance["maximum_median_paired_wall_time_ratio"],
        ),
        "provider_tokens": _gate(
            median_token_ratio <= acceptance["maximum_median_paired_total_token_ratio"],
            observed_median_ratio=median_token_ratio,
            maximum=acceptance["maximum_median_paired_total_token_ratio"],
        ),
        "model_round_trips": _gate(
            median_model_delta
            <= acceptance["maximum_median_paired_model_round_trip_delta"],
            observed_median_delta=median_model_delta,
            maximum=acceptance["maximum_median_paired_model_round_trip_delta"],
        ),
        "tool_round_trips": _gate(
            median_tool_delta
            <= acceptance["maximum_median_paired_tool_round_trip_delta"],
            observed_median_delta=median_tool_delta,
            maximum=acceptance["maximum_median_paired_tool_round_trip_delta"],
        ),
        "skill_read_calls": _gate(
            median_skill_read_delta
            <= acceptance["maximum_median_paired_skill_read_call_delta"],
            observed_median_delta=median_skill_read_delta,
            maximum=acceptance["maximum_median_paired_skill_read_call_delta"],
        ),
        "skill_read_tokens": _gate(
            median_skill_read_token_delta
            <= acceptance["maximum_median_paired_skill_read_token_delta"],
            observed_median_delta=median_skill_read_token_delta,
            maximum=acceptance["maximum_median_paired_skill_read_token_delta"],
        ),
        "host_side_only": _gate(
            model_visible <= acceptance["maximum_model_visible_tmcp_round_trips"],
            observed_maximum=model_visible,
            maximum=acceptance["maximum_model_visible_tmcp_round_trips"],
        ),
        "substitution_integrity": _gate(
            all(
                row["admission"]["action"] != "compose"
                or (
                    row["routing"]["mode"] == "substitution"
                    and row["routing"]["normal_full_skill_load_count"] == 0
                    and row["routing"]["supplemental_full_skill_load_count"] == 0
                )
                for row in tmcp_rows
            )
        ),
    }
    return {
        "schema": "tmcp-invocation-admission-canary-score-v0.7",
        "status": "complete",
        "promotion_authorized": all(gate["passed"] for gate in gates.values()),
        "pairs_scored": len(pair_rows),
        "acceptance_gates": gates,
        "evidence_boundary": manifest["evidence_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("readiness", "shadow", "canary"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--shadow-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        manifest = _read_object(args.manifest.resolve())
        traces = _read_jsonl(args.traces.resolve())
        if args.phase == "readiness":
            report = score_attribution_readiness(manifest, traces)
        elif args.phase == "shadow":
            report = score_shadow(manifest, traces)
        else:
            if args.judgments is None or args.shadow_report is None:
                raise ValueError(
                    "canary scoring requires --judgments and --shadow-report"
                )
            report = score_canary(
                manifest,
                traces,
                _read_jsonl(args.judgments.resolve()),
                _read_object(args.shadow_report.resolve()),
            )
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            if args.output.exists():
                raise ValueError(f"output already exists: {args.output}")
            args.output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
