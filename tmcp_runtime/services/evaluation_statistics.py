"""Paired evaluation summaries and conservative promotion statistics."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "dogfooded": {"minimum_traces": 3, "minimum_fixtures": 2},
    "controlled_single_agent_eval": {
        "minimum_repetitions_per_cell": 2,
        "minimum_fixtures": 2,
        "minimum_agent_configurations": 1,
    },
    "controlled_multi_agent_eval": {
        "minimum_repetitions_per_cell": 2,
        "minimum_fixtures": 6,
        "minimum_fixture_families": 3,
        "minimum_agent_configurations": 3,
        "minimum_absolute_lift": 0.1,
    },
}


def thresholds_for_plan(plan: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    result = {level: dict(values) for level, values in DEFAULT_THRESHOLDS.items()}
    experiment = plan.get("experiment")
    supplied = (
        experiment.get("promotion_thresholds")
        if isinstance(experiment, Mapping)
        else None
    )
    if not isinstance(supplied, Mapping):
        return result
    for level, defaults in result.items():
        candidate = supplied.get(level)
        if not isinstance(candidate, Mapping):
            continue
        for key in defaults:
            value = candidate.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                defaults[key] = max(defaults[key], float(value))
    return result


def _wilson_interval(passed: int, total: int) -> tuple[float, float] | None:
    if total <= 0:
        return None
    z = 1.96
    proportion = passed / total
    denominator = 1 + (z * z / total)
    center = (proportion + (z * z / (2 * total))) / denominator
    margin = (
        z
        * math.sqrt(
            (proportion * (1 - proportion) / total) + (z * z / (4 * total * total))
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _difference_interval(
    intervention: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any] | None:
    intervention_interval = _wilson_interval(
        int(intervention.get("passed") or 0), int(intervention.get("total") or 0)
    )
    control_interval = _wilson_interval(
        int(control.get("passed") or 0), int(control.get("total") or 0)
    )
    if intervention_interval is None or control_interval is None:
        return None
    return {
        "lower": round(intervention_interval[0] - control_interval[1], 3),
        "upper": round(intervention_interval[1] - control_interval[0], 3),
        "confidence": 0.95,
        "method": "newcombe_wilson_difference",
    }


def evaluation_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    intervention_variant: str,
    control_variant: str,
    controlled_only: bool,
) -> dict[str, Any]:
    eligible = [
        record
        for record in records
        if record.get("passed") is not None
        and not record.get("verdict_gaps")
        and str(record["row"].get("fixture_digest") or "")
        and str(record["row"].get("variant_id"))
        in {intervention_variant, control_variant}
        and (not controlled_only or record.get("controlled") is True)
    ]
    pair_groups: dict[tuple[str, str, str, str], dict[str, list[Mapping[str, Any]]]] = (
        defaultdict(lambda: defaultdict(list))
    )
    for record in eligible:
        row = record["row"]
        key = (
            str(row.get("fixture_digest") or ""),
            str(row.get("skill_digest") or row.get("skill_path") or ""),
            str(row.get("contrast_id") or ""),
            str(record.get("configuration_id") or ""),
        )
        pair_groups[key][str(row.get("variant_id"))].append(record)
    complete_keys = {
        key
        for key, conditions in pair_groups.items()
        if conditions.get(intervention_variant) and conditions.get(control_variant)
    }
    paired = [
        record
        for key in complete_keys
        for variant in (intervention_variant, control_variant)
        for record in pair_groups[key][variant]
    ]
    condition_records = {
        variant: [
            record
            for record in paired
            if str(record["row"].get("variant_id")) == variant
        ]
        for variant in (intervention_variant, control_variant)
    }

    def condition(variant: str) -> dict[str, Any]:
        items = condition_records[variant]
        passed = sum(1 for item in items if item.get("passed") is True)
        total = len(items)
        return {
            "passed": passed,
            "total": total,
            "pass_rate": round(passed / total, 3) if total else None,
        }

    intervention = condition(intervention_variant)
    control = condition(control_variant)
    lift = (
        round(float(intervention["pass_rate"]) - float(control["pass_rate"]), 3)
        if intervention["pass_rate"] is not None and control["pass_rate"] is not None
        else None
    )
    repetitions = [
        len(pair_groups[key][variant])
        for key in complete_keys
        for variant in (intervention_variant, control_variant)
    ]
    fixtures = {str(record["row"].get("fixture_digest")) for record in paired}
    families = {
        str(record["row"].get("fixture_family") or "unspecified") for record in paired
    }
    configurations = {str(record.get("configuration_id") or "") for record in paired}
    configuration_effects: list[dict[str, Any]] = []
    for configuration_id in sorted(configurations):
        condition_summaries: dict[str, dict[str, int]] = {}
        for variant in (intervention_variant, control_variant):
            items = [
                record
                for record in paired
                if str(record.get("configuration_id") or "") == configuration_id
                and str(record["row"].get("variant_id")) == variant
            ]
            condition_summaries[variant] = {
                "passed": sum(1 for record in items if record.get("passed") is True),
                "total": len(items),
            }
        intervention_total = condition_summaries[intervention_variant]["total"]
        control_total = condition_summaries[control_variant]["total"]
        intervention_rate = (
            condition_summaries[intervention_variant]["passed"] / intervention_total
            if intervention_total
            else None
        )
        control_rate = (
            condition_summaries[control_variant]["passed"] / control_total
            if control_total
            else None
        )
        configuration_effects.append(
            {
                "configuration_id": configuration_id,
                "absolute_lift": (
                    round(intervention_rate - control_rate, 3)
                    if intervention_rate is not None and control_rate is not None
                    else None
                ),
                "intervention_total": intervention_total,
                "control_total": control_total,
            }
        )
    regression_missing = 0
    safety_regression = False
    cost_regression = False
    for record in paired:
        verdict = record["trace"].get("case_verdict")
        if not isinstance(verdict, Mapping):
            regression_missing += 1
            continue
        safety = verdict.get("safety_regression")
        cost = verdict.get("cost_regression")
        if not isinstance(safety, bool) or not isinstance(cost, bool):
            regression_missing += 1
            continue
        safety_regression = safety_regression or safety
        cost_regression = cost_regression or cost
    return {
        "trace_count": len(paired),
        "paired_cells": len(complete_keys),
        "fixture_count": len(fixtures),
        "fixture_family_count": len(families),
        "agent_configuration_count": len(configurations),
        "minimum_repetitions_per_cell": min(repetitions, default=0),
        "intervention": intervention,
        "control": control,
        "absolute_lift": lift,
        "absolute_lift_interval": _difference_interval(intervention, control),
        "configuration_effects": configuration_effects,
        "regression_fields_missing": regression_missing,
        "safety_regression": safety_regression,
        "cost_regression": cost_regression,
        "regression_free": bool(paired)
        and regression_missing == 0
        and not safety_regression
        and not cost_regression,
    }


def meets_threshold(summary: Mapping[str, Any], threshold: Mapping[str, float]) -> bool:
    checks = {
        "minimum_traces": summary.get("trace_count", 0),
        "minimum_fixtures": summary.get("fixture_count", 0),
        "minimum_fixture_families": summary.get("fixture_family_count", 0),
        "minimum_agent_configurations": summary.get("agent_configuration_count", 0),
        "minimum_repetitions_per_cell": summary.get("minimum_repetitions_per_cell", 0),
    }
    return all(
        float(checks[key]) >= value for key, value in threshold.items() if key in checks
    )


def promotion_gaps(
    claim: Mapping[str, Any], thresholds: Mapping[str, Mapping[str, float]]
) -> list[str]:
    gaps: list[str] = []
    if not claim.get("causal_contrast_valid"):
        gaps.append("intervention is not a one-factor causal contrast")
    summary = claim["controlled_summary"]
    multi = thresholds["controlled_multi_agent_eval"]
    for threshold_key, metric_key in (
        ("minimum_fixtures", "fixture_count"),
        ("minimum_fixture_families", "fixture_family_count"),
        ("minimum_agent_configurations", "agent_configuration_count"),
        ("minimum_repetitions_per_cell", "minimum_repetitions_per_cell"),
    ):
        required = int(multi[threshold_key])
        actual = int(summary.get(metric_key) or 0)
        if actual < required:
            gaps.append(f"{metric_key} {actual} is below required {required}")
    lift = summary.get("absolute_lift")
    direction = str(claim.get("expected_effect_direction") or "positive")
    aligned_lift = (
        -float(lift) if direction == "negative" and lift is not None else lift
    )
    minimum_lift = float(multi["minimum_absolute_lift"])
    if aligned_lift is None or float(aligned_lift) < minimum_lift:
        rendered = "missing" if aligned_lift is None else f"{float(aligned_lift):.3f}"
        gaps.append(
            f"aligned absolute lift {rendered} is below required {minimum_lift:.3f}"
        )
    interval = summary.get("absolute_lift_interval")
    aligned_interval_lower: float | None = None
    if isinstance(interval, Mapping):
        raw_lower = interval.get("lower")
        raw_upper = interval.get("upper")
        if isinstance(raw_lower, (int, float)) and isinstance(raw_upper, (int, float)):
            aligned_interval_lower = (
                -float(raw_upper) if direction == "negative" else float(raw_lower)
            )
    if aligned_interval_lower is None or aligned_interval_lower <= 0:
        rendered = (
            "missing"
            if aligned_interval_lower is None
            else f"{aligned_interval_lower:.3f}"
        )
        gaps.append(
            f"aligned 95% lift interval lower bound {rendered} does not clear zero"
        )
    reversals = [
        str(effect.get("configuration_id") or "unspecified")
        for effect in summary.get("configuration_effects") or []
        if isinstance(effect, Mapping)
        and isinstance(effect.get("absolute_lift"), (int, float))
        and (
            -float(effect["absolute_lift"])
            if direction == "negative"
            else float(effect["absolute_lift"])
        )
        < 0
    ]
    if reversals:
        gaps.append(
            "agent-configuration effect reversal detected: " + ", ".join(reversals)
        )
    if int(summary.get("regression_fields_missing") or 0):
        gaps.append("safety/cost regression verdicts are incomplete")
    if summary.get("safety_regression"):
        gaps.append("safety regression detected")
    if summary.get("cost_regression"):
        gaps.append("cost regression detected")
    return gaps
