"""Evidence-strength analysis and guidebook claim policy for skill evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.services.evaluation_catalog import EVIDENCE_RANK
from tmcp_runtime.services.evaluation_cost_rejudge import (
    cost_rejudge_requirement as cost_rejudge_coverage_requirement,
)
from tmcp_runtime.services.evaluation_statistics import (
    DEFAULT_THRESHOLDS as DEFAULT_THRESHOLDS,
    clustered_analysis_policy_for_plan,
    evaluation_summary,
    meets_threshold,
    promotion_gaps,
    thresholds_for_plan,
)
from tmcp_runtime.services.evaluation_trace_evidence import (
    records_for_plan,
    validated_case_verdict,
)


def scorecard_claim_boundary() -> dict[str, Any]:
    """Describe which report surface may support guidebook promotion."""

    return {
        "promotion_source": "pattern_claims",
        "diagnostic_only_dimensions": [
            "activation",
            "packet_inclusion",
            "adherence",
            "cost",
            "safety",
        ],
        "notes": (
            "Only validated, behaviorally judged pattern_claims can change guidebook "
            "evidence status. Other scorecard dimensions are heuristic diagnostics "
            "and must not be read as causal effects."
        ),
    }


def _baseline_reliability_policy(plan: Mapping[str, Any]) -> Mapping[str, Any] | None:
    experiment = plan.get("experiment")
    policy = (
        experiment.get("campaign_policy") if isinstance(experiment, Mapping) else None
    )
    if (
        not isinstance(policy, Mapping)
        or policy.get("design") != "baseline_reliability"
    ):
        return None
    baseline = policy.get("baseline_reliability")
    return baseline if isinstance(baseline, Mapping) else None


def is_baseline_reliability_plan(plan: Mapping[str, Any]) -> bool:
    """Return whether a plan is an original-only reliability study."""

    return _baseline_reliability_policy(plan) is not None


def baseline_reliability_summary(
    plan: Mapping[str, Any],
    traces: Sequence[Mapping[str, Any]],
    *,
    cost_rejudgments: Mapping[str, bool] | None = None,
) -> dict[str, Any] | None:
    """Summarize intact-skill reliability without inventing a causal contrast."""

    baseline_policy = _baseline_reliability_policy(plan)
    if baseline_policy is None:
        return None

    control_variant = str(baseline_policy.get("control_variant") or "original")
    planned_rows = [
        dict(row)
        for row in plan.get("task_matrix", [])
        if isinstance(row, Mapping) and row.get("variant_id") == control_variant
    ]
    fixture_rows: dict[str, dict[str, Any]] = {}
    for row in planned_rows:
        fixture_digest = str(row.get("fixture_digest") or "")
        if fixture_digest:
            fixture_rows.setdefault(fixture_digest, row)

    records = [
        record
        for record in records_for_plan(plan, traces)
        if str(record["row"].get("variant_id") or "") == control_variant
    ]
    by_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        row = record["row"]
        fixture_digest = str(row.get("fixture_digest") or "")
        if fixture_digest:
            by_fixture[fixture_digest].append(record)
        runner_model = str(record.get("runner_model") or "unspecified")
        by_model[runner_model].append(record)

    def _counts(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        total = len(items)
        passed = sum(1 for item in items if item.get("passed") is True)
        return {
            "passed": passed,
            "total": total,
            "pass_rate": round(passed / total, 3) if total else None,
        }

    per_fixture = [
        {
            "fixture_digest": fixture_digest,
            "task_id": row.get("task_id"),
            "fixture_family": row.get("fixture_family"),
            **_counts(by_fixture.get(fixture_digest, [])),
        }
        for fixture_digest, row in sorted(fixture_rows.items())
    ]
    per_fixture_rates = [
        float(item["pass_rate"])
        for item in per_fixture
        if isinstance(item.get("pass_rate"), (int, float))
    ]

    experiment = plan.get("experiment")
    policy = (
        experiment.get("campaign_policy") if isinstance(experiment, Mapping) else None
    )
    configurations = (
        policy.get("runner_configurations") if isinstance(policy, Mapping) else None
    )
    expected_models = {
        str(configuration.get("model") or "")
        for configuration in configurations or []
        if isinstance(configuration, Mapping) and str(configuration.get("model") or "")
    }
    runner_models = sorted(expected_models | set(by_model))
    per_runner_model = []
    for model in runner_models:
        model_records = by_model.get(model, [])
        model_by_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in model_records:
            digest = str(record["row"].get("fixture_digest") or "")
            if digest:
                model_by_fixture[digest].append(record)
        counts = _counts(model_records)
        per_runner_model.append(
            {
                "model": model,
                **counts,
                "fixture_count": len(model_by_fixture),
                "minimum_repetitions_per_fixture": min(
                    (len(model_by_fixture.get(digest, [])) for digest in fixture_rows),
                    default=0,
                ),
            }
        )

    totals = _counts(records)
    valid_case_verdicts = sum(1 for record in records if not record.get("verdict_gaps"))
    provenance_complete = all(record.get("controlled") is True for record in records)
    raw_safety_regressions = sum(
        1
        for record in records
        if isinstance(record["trace"].get("case_verdict"), Mapping)
        and record["trace"]["case_verdict"].get("safety_regression") is True
    )
    raw_cost_regressions = sum(
        1
        for record in records
        if isinstance(record["trace"].get("case_verdict"), Mapping)
        and record["trace"]["case_verdict"].get("cost_regression") is True
    )
    trace_ids = [str(record["trace"].get("trace_id") or "") for record in records]
    adjudicated_cost_regressions = (
        sum(1 for trace_id in trace_ids if cost_rejudgments.get(trace_id) is True)
        if cost_rejudgments is not None
        else None
    )
    adjudicated_cost_complete = cost_rejudgments is not None and all(
        trace_id in cost_rejudgments for trace_id in trace_ids
    )
    overall_floor = float(baseline_policy["minimum_control_pass_rate"])
    per_fixture_floor = float(baseline_policy["minimum_per_fixture_control_pass_rate"])
    floors_met = (
        totals["pass_rate"] is not None
        and valid_case_verdicts == totals["total"]
        and provenance_complete
        and len(per_fixture) == len(fixture_rows)
        and len(per_fixture_rates) == len(per_fixture)
        and float(totals["pass_rate"]) >= overall_floor
        and all(rate >= per_fixture_floor for rate in per_fixture_rates)
    )
    return {
        "design": "baseline_reliability",
        "causal_contrast_applicable": False,
        "control_variant": control_variant,
        **totals,
        "valid_case_verdicts": valid_case_verdicts,
        "provenance_complete": provenance_complete,
        "minimum_per_fixture_pass_rate": (
            round(min(per_fixture_rates), 3) if per_fixture_rates else None
        ),
        "per_fixture": per_fixture,
        "per_runner_model": per_runner_model,
        "raw_safety_regressions": raw_safety_regressions,
        "raw_cost_regressions": raw_cost_regressions,
        "cost_rejudgment_applied": cost_rejudgments is not None,
        "cost_rejudgment_complete": adjudicated_cost_complete,
        "adjudicated_cost_regressions": adjudicated_cost_regressions,
        "predeclared_thresholds": {
            "minimum_control_pass_rate": overall_floor,
            "minimum_per_fixture_control_pass_rate": per_fixture_floor,
        },
        "meets_predeclared_floors": floors_met,
    }


def _cross_model_confirmation(
    plan: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    intervention_variant: str,
    control_variant: str,
    direction: str,
) -> dict[str, Any]:
    """Assess only a policy-declared independent-model replication requirement."""

    experiment = plan.get("experiment")
    policy = (
        experiment.get("campaign_policy") if isinstance(experiment, Mapping) else None
    )
    confirmation = (
        policy.get("cross_model_confirmation") if isinstance(policy, Mapping) else None
    )
    if (
        not isinstance(confirmation, Mapping)
        or confirmation.get("required") is not True
    ):
        return {"required": False, "passed": True, "gaps": [], "model_effects": []}
    required_models = int(confirmation.get("minimum_distinct_runner_models") or 2)
    required_fixtures = int(confirmation.get("minimum_fixture_count_per_model") or 1)
    required_repetitions = int(confirmation.get("minimum_repetitions_per_cell") or 1)
    directional = confirmation.get("require_directional_replication") is True
    eligible = [
        record
        for record in records
        if record.get("controlled") is True
        and record.get("runner_model")
        and str(record["row"].get("variant_id") or "")
        in {intervention_variant, control_variant}
    ]
    model_records: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in eligible:
        model_records[str(record["runner_model"])].append(record)
    gaps: list[str] = []
    if len(model_records) < required_models:
        gaps.append(
            f"runner model count {len(model_records)} is below required {required_models}"
        )
    configuration_models: dict[str, set[str]] = defaultdict(set)
    for record in eligible:
        configuration_models[str(record["configuration_id"])].add(
            str(record["runner_model"])
        )
    ambiguous = sorted(
        configuration
        for configuration, models in configuration_models.items()
        if len(models) > 1
    )
    if ambiguous:
        gaps.append(
            "configuration IDs span multiple runner models: " + ", ".join(ambiguous)
        )
    model_effects: list[dict[str, Any]] = []
    for model, items in sorted(model_records.items()):
        summary = evaluation_summary(
            items,
            intervention_variant=intervention_variant,
            control_variant=control_variant,
            controlled_only=True,
        )
        effect = summary.get("absolute_lift")
        aligned_effect = (
            -float(effect)
            if direction == "negative" and isinstance(effect, (int, float))
            else effect
        )
        model_effects.append(
            {
                "model": model,
                "fixture_count": summary["fixture_count"],
                "minimum_repetitions_per_cell": summary["minimum_repetitions_per_cell"],
                "configuration_count": summary["agent_configuration_count"],
                "absolute_lift": effect,
            }
        )
        if int(summary["fixture_count"]) < required_fixtures:
            gaps.append(
                f"runner model {model} fixture count {summary['fixture_count']} is below required {required_fixtures}"
            )
        if int(summary["minimum_repetitions_per_cell"]) < required_repetitions:
            gaps.append(
                f"runner model {model} repetitions are below required {required_repetitions}"
            )
        if directional and (
            not isinstance(aligned_effect, (int, float)) or float(aligned_effect) <= 0
        ):
            gaps.append(
                f"runner model {model} does not replicate the expected direction"
            )
    configured_judge = (
        policy.get("judge_configuration") if isinstance(policy, Mapping) else None
    )
    judge_model = (
        str(configured_judge.get("model") or "")
        if isinstance(configured_judge, Mapping)
        else ""
    )
    if not judge_model or judge_model in model_records:
        gaps.append("judge model is not independent from runner models")
    return {
        "required": True,
        "passed": not gaps,
        "gaps": gaps,
        "model_effects": model_effects,
    }


def case_scores(
    plan: Mapping[str, Any], traces: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Expose fixture-specific judge verdicts without replacing them with heuristics."""

    result: list[dict[str, Any]] = []
    for record in records_for_plan(plan, traces):
        row = record["row"]
        result.append(
            {
                "trace_id": record["trace"].get("trace_id"),
                "matrix_row_id": row.get("matrix_row_id"),
                "task_id": row.get("task_id"),
                "variant_id": row.get("variant_id"),
                "expected_observables": list(row.get("expected_observables") or []),
                "failure_smells": list(row.get("failure_smells") or []),
                "passed": record["passed"],
                "judge_evidence_valid": not record["verdict_gaps"],
                "controlled_provenance_valid": record["controlled"],
                "evidence_gaps": list(record["controlled_gaps"]),
            }
        )
    return result


def analyze_pattern_evidence(
    plan: Mapping[str, Any],
    traces: Sequence[Mapping[str, Any]],
    *,
    cost_rejudgments: Mapping[str, bool] | None = None,
) -> list[dict[str, Any]]:
    """Compute paired effects and evidence levels for explicitly tagged patterns."""

    if is_baseline_reliability_plan(plan):
        return []

    records = records_for_plan(plan, traces)
    cost_rejudge_requirement = cost_rejudge_coverage_requirement(
        plan, traces, cost_rejudgments
    )
    thresholds = thresholds_for_plan(plan)
    clustered_policy = clustered_analysis_policy_for_plan(plan)
    rows_by_pattern: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in plan.get("task_matrix", []):
        if not isinstance(row, Mapping):
            continue
        pattern_id = str(row.get("pattern_id") or "")
        if pattern_id:
            rows_by_pattern[pattern_id].append(dict(row))

    claims: list[dict[str, Any]] = []
    plan_contract_trusted = (
        str(plan.get("schema") or "") != "tmcp-skill-evaluation-plan-v0.1"
    )
    for pattern_id, rows in sorted(rows_by_pattern.items()):
        interventions = {str(row.get("intervention_variant") or "") for row in rows}
        controls = {str(row.get("control_variant") or "") for row in rows}
        directions = {
            str(row.get("expected_effect_direction") or "positive") for row in rows
        }
        targets = {str(row.get("intervention_target") or "") for row in rows}
        tested_atoms = {str(row.get("tested_atom") or "") for row in rows}
        intervention_contracts = {
            (
                str(contract.get("tested_atom") or ""),
                tuple(
                    sorted(str(item) for item in contract.get("allowed_targets") or [])
                ),
                tuple(
                    sorted(str(item) for item in contract.get("allowed_kinds") or [])
                ),
                str(contract.get("claim_granularity") or ""),
                str(contract.get("expected_support_direction") or ""),
            )
            for row in rows
            for contract in [row.get("pattern_intervention_contract")]
            if isinstance(contract, Mapping)
        }
        design_consistent = (
            len(interventions) == 1
            and len(controls) == 1
            and len(directions) == 1
            and len(targets) == 1
            and "" not in targets
            and len(tested_atoms) == 1
            and "" not in tested_atoms
            and len(intervention_contracts) == 1
        )
        intervention_variant = next(iter(interventions), "")
        control_variant = next(iter(controls), "")
        direction = next(iter(directions), "positive")
        intervention_target = next(iter(targets), "")
        tested_atom = next(iter(tested_atoms), "")
        (
            contract_atom,
            allowed_targets,
            allowed_kinds,
            claim_granularity,
            contract_direction,
        ) = next(iter(intervention_contracts), ("", (), (), "", ""))
        intervention_rows = [
            row
            for row in rows
            if str(row.get("variant_id")) == intervention_variant
            and (
                intervention_variant != "ablated"
                or str(row.get("ablation_section") or "")
                == str(row.get("intervention_target") or "")
            )
        ]
        control_rows = [
            row for row in rows if str(row.get("variant_id")) == control_variant
        ]
        contrast_ids = {
            str(row.get("contrast_id") or "")
            for row in (*intervention_rows, *control_rows)
        }
        paired_contrasts = (
            bool(contrast_ids)
            and "" not in contrast_ids
            and all(
                any(
                    str(row.get("contrast_id")) == contrast_id
                    for row in intervention_rows
                )
                and any(
                    str(row.get("contrast_id")) == contrast_id for row in control_rows
                )
                for contrast_id in contrast_ids
            )
        )
        all_interventions_causal = bool(intervention_rows) and all(
            isinstance(row.get("intervention"), Mapping)
            and row["intervention"].get("causal_attribution") is True
            and row["intervention"].get("kind") != "control"
            and str(row["intervention"].get("target") or "") == intervention_target
            and str(row["intervention"].get("kind") or "") in allowed_kinds
            for row in intervention_rows
        )
        matched_control_valid = bool(intervention_rows) and all(
            (
                row["intervention"].get("kind") == "single_section_ablation"
                and control_variant == "original"
            )
            or (
                row["intervention"].get("kind") == "source_bundle_inclusion"
                and control_variant == "packet_only"
            )
            for row in intervention_rows
            if isinstance(row.get("intervention"), Mapping)
        )
        has_fixture_digests = all(str(row.get("fixture_digest") or "") for row in rows)
        causal_contrast_valid = (
            plan_contract_trusted
            and design_consistent
            and intervention_variant != control_variant
            and all_interventions_causal
            and matched_control_valid
            and paired_contrasts
            and has_fixture_digests
            and tested_atom == contract_atom
            and intervention_target in allowed_targets
            and bool(claim_granularity)
            and direction == contract_direction
        )
        pattern_records = [
            record
            for record in records
            if str(record["row"].get("pattern_id") or "") == pattern_id
            and (
                str(record["row"].get("variant_id")) != intervention_variant
                or intervention_variant != "ablated"
                or str(record["row"].get("ablation_section") or "")
                == str(record["row"].get("intervention_target") or "")
            )
        ]
        observed = evaluation_summary(
            pattern_records,
            intervention_variant=intervention_variant,
            control_variant=control_variant,
            controlled_only=False,
            clustered_analysis_policy=clustered_policy,
            cost_rejudgments=cost_rejudgments,
        )
        controlled = evaluation_summary(
            pattern_records,
            intervention_variant=intervention_variant,
            control_variant=control_variant,
            controlled_only=True,
            clustered_analysis_policy=clustered_policy,
            cost_rejudgments=cost_rejudgments,
        )
        cross_model_confirmation = _cross_model_confirmation(
            plan,
            pattern_records,
            intervention_variant=intervention_variant,
            control_variant=control_variant,
            direction=direction,
        )
        evidence_level = "hypothesis"
        if causal_contrast_valid and meets_threshold(observed, thresholds["dogfooded"]):
            evidence_level = "dogfooded"
        if causal_contrast_valid and meets_threshold(
            controlled, thresholds["controlled_single_agent_eval"]
        ):
            evidence_level = "controlled_single_agent_eval"
        if causal_contrast_valid and meets_threshold(
            controlled, thresholds["controlled_multi_agent_eval"]
        ):
            evidence_level = "controlled_multi_agent_eval"
        exclusion_reasons = Counter(
            gap for record in pattern_records for gap in record["controlled_gaps"]
        )
        claim: dict[str, Any] = {
            "pattern_id": pattern_id,
            "intervention_variant": intervention_variant,
            "control_variant": control_variant,
            "expected_effect_direction": direction,
            "intervention_target": intervention_target,
            "tested_atom": tested_atom,
            "claim_granularity": claim_granularity,
            "causal_contrast_valid": causal_contrast_valid,
            "plan_contract_trusted": plan_contract_trusted,
            "analysis_policy_predeclared": bool(clustered_policy["predeclared"]),
            "analysis_policy": clustered_policy,
            "cost_rejudge_requirement": cost_rejudge_requirement,
            "evidence_level": evidence_level,
            "observed_summary": observed,
            "controlled_summary": controlled,
            "cross_model_confirmation": cross_model_confirmation,
            "excluded_controlled_trace_count": sum(
                1 for record in pattern_records if not record["controlled"]
            ),
            "controlled_exclusion_reasons": [
                {"reason": reason, "count": count}
                for reason, count in sorted(exclusion_reasons.items())
            ],
        }
        gaps = promotion_gaps(claim, thresholds)
        claim["promotion_eligible"] = not gaps and (
            EVIDENCE_RANK[evidence_level]
            >= EVIDENCE_RANK["controlled_multi_agent_eval"]
        )
        claim["promotion_decision"] = (
            "eligible_for_manual_review" if claim["promotion_eligible"] else "hold"
        )
        claim["promotion_gaps"] = gaps
        claims.append(claim)
    return claims


def aggregate_lift(claims: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate actual paired lift; never substitute mean task outcome."""

    effects = [
        (
            -float(summary["absolute_lift"])
            if str(claim.get("expected_effect_direction") or "positive") == "negative"
            else float(summary["absolute_lift"])
        )
        for claim in claims
        for summary in [claim.get("controlled_summary")]
        if isinstance(summary, Mapping) and summary.get("absolute_lift") is not None
    ]
    if not effects:
        effects = [
            (
                -float(summary["absolute_lift"])
                if str(claim.get("expected_effect_direction") or "positive")
                == "negative"
                else float(summary["absolute_lift"])
            )
            for claim in claims
            for summary in [claim.get("observed_summary")]
            if isinstance(summary, Mapping) and summary.get("absolute_lift") is not None
        ]
    if not effects:
        return {
            "score": 0.0,
            "confidence": "low",
            "notes": "No paired intervention/control verdicts were available.",
        }
    highest = max(
        (EVIDENCE_RANK.get(str(claim.get("evidence_level")), 0) for claim in claims),
        default=0,
    )
    confidence = "high" if highest >= 4 else "medium" if highest >= 3 else "low"
    return {
        "score": round(sum(effects) / len(effects), 3),
        "confidence": confidence,
        "paired_pattern_count": len(effects),
    }
