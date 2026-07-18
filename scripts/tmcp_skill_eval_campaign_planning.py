"""Matrix construction and preregistration readiness for skill-eval campaigns."""

from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CampaignCell:
    order: int
    cell_id: str
    matrix_row_id: str
    task_id: str
    variant_id: str
    fixture_family: str
    fixture_digest: str
    replicate_id: str
    runner_model: str
    runner_effort: str
    configuration_id: str


def _stable_id(*parts: str, prefix: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def selected_rows(
    plan: dict[str, Any],
    *,
    pattern_id: str,
    intervention_target: str,
    design: str = "causal_contrast",
) -> list[dict[str, Any]]:
    if design not in {"baseline_reliability", "causal_contrast"}:
        raise ValueError(
            "Campaign design must be baseline_reliability or causal_contrast."
        )
    rows = []
    for row in plan.get("task_matrix", []):
        if (
            not isinstance(row, dict)
            or row.get("pattern_id") != pattern_id
            or row.get("intervention_target") != intervention_target
        ):
            continue
        variant_id = str(row.get("variant_id") or "")
        control_variant = str(row.get("control_variant") or "original")
        intervention_variant = str(row.get("intervention_variant") or "ablated")
        if design == "baseline_reliability":
            if variant_id == control_variant:
                rows.append(row)
            continue
        if variant_id == control_variant:
            rows.append(row)
        elif variant_id == intervention_variant and (
            intervention_variant != "ablated"
            or row.get("ablation_section") == intervention_target
        ):
            rows.append(row)
    if not rows:
        raise ValueError("No matched pattern rows found in the evaluation plan.")
    return rows


def build_cells(
    plan: dict[str, Any],
    *,
    pattern_id: str,
    intervention_target: str,
    model: str,
    runner_efforts: list[str],
    runner_configurations: list[tuple[str, str]] | None = None,
    design: str = "causal_contrast",
    repetitions: int,
    expected_fixtures: int,
    seed: int,
    codex_version: str,
) -> list[CampaignCell]:
    rows = selected_rows(
        plan,
        pattern_id=pattern_id,
        intervention_target=intervention_target,
        design=design,
    )
    rows_by_task: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_task.setdefault(str(row["task_id"]), []).append(row)
    if len(rows_by_task) != expected_fixtures:
        raise ValueError(
            f"Expected {expected_fixtures} fixtures, found {len(rows_by_task)}."
        )
    for task_id, task_rows in rows_by_task.items():
        variants = [str(row["variant_id"]) for row in task_rows]
        control_variants = {
            str(row.get("control_variant") or "original") for row in task_rows
        }
        intervention_variants = {
            str(row.get("intervention_variant") or "ablated") for row in task_rows
        }
        if len(control_variants) != 1 or len(intervention_variants) != 1:
            raise ValueError(f"Fixture {task_id} does not declare one matched contrast.")
        control_variant = next(iter(control_variants))
        intervention_variant = next(iter(intervention_variants))
        expected_variants = (
            [control_variant]
            if design == "baseline_reliability"
            else sorted({control_variant, intervention_variant})
        )
        if sorted(variants) != expected_variants:
            raise ValueError(
                f"Fixture {task_id} does not match {design} variant requirements."
            )
        fixture_digests = {str(row.get("fixture_digest") or "") for row in task_rows}
        if len(fixture_digests) != 1 or "" in fixture_digests:
            raise ValueError(f"Fixture {task_id} must have one stable fixture digest.")
        for row in task_rows:
            observables = row.get("expected_observables")
            if (
                not isinstance(observables, list)
                or not observables
                or not all(
                    isinstance(item, str) and item.strip() for item in observables
                )
            ):
                raise ValueError(
                    f"Fixture {task_id} must have non-empty expected observables."
                )
            for field in ("prompt", "skill_attachment", "fixture_family"):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError(f"Fixture {task_id} has an empty {field}.")
    fixture_digests = {
        str(task_rows[0]["fixture_digest"]) for task_rows in rows_by_task.values()
    }
    if len(fixture_digests) != expected_fixtures:
        raise ValueError("Every fixture must have a unique fixture digest.")
    fixture_families = {
        str(task_rows[0]["fixture_family"]) for task_rows in rows_by_task.values()
    }
    if len(fixture_families) < 3:
        raise ValueError("Campaign requires at least three fixture families.")
    configurations = (
        list(runner_configurations)
        if runner_configurations is not None
        else [(model, effort) for effort in runner_efforts]
    )
    if not configurations or any(
        not runner_model.strip() or not effort.strip()
        for runner_model, effort in configurations
    ):
        raise ValueError(
            "runner configurations must contain non-empty model and effort."
        )
    if len(set(configurations)) != len(configurations):
        raise ValueError("runner configurations must be distinct.")
    cells: list[CampaignCell] = []
    for row in rows:
        for runner_model, effort in configurations:
            configuration_id = (
                f"{runner_model}-reasoning-{effort}-{codex_version.replace(' ', '-')}"
            )
            for replicate in range(1, repetitions + 1):
                cell_id = _stable_id(
                    str(plan["experiment"]["experiment_id"]),
                    str(row["matrix_row_id"]),
                    configuration_id,
                    str(replicate),
                    prefix="campaign-cell",
                )
                cells.append(
                    CampaignCell(
                        order=0,
                        cell_id=cell_id,
                        matrix_row_id=str(row["matrix_row_id"]),
                        task_id=str(row["task_id"]),
                        variant_id=str(row["variant_id"]),
                        fixture_family=str(row["fixture_family"]),
                        fixture_digest=str(row["fixture_digest"]),
                        replicate_id=f"replicate-{replicate}",
                        runner_model=runner_model,
                        runner_effort=effort,
                        configuration_id=configuration_id,
                    )
                )
    random.Random(seed).shuffle(cells)
    return [
        CampaignCell(**{**asdict(cell), "order": index})
        for index, cell in enumerate(cells, start=1)
    ]


def campaign_readiness_report(
    plan: dict[str, Any],
    *,
    cells: list[CampaignCell],
    design: str,
    judge_model: str,
    judge_effort: str,
) -> dict[str, Any]:
    """Return launch readiness without starting a runner or judge session."""

    gaps: list[str] = []
    experiment = plan.get("experiment")
    policy = experiment.get("campaign_policy") if isinstance(experiment, dict) else None
    if not isinstance(policy, dict):
        gaps.append("missing_campaign_policy")
        policy = {}
    if policy.get("schema") != "tmcp-skill-eval-campaign-policy-v0.1":
        gaps.append("invalid_campaign_policy_schema")
    if policy.get("design") != design:
        gaps.append("campaign_design_not_preregistered")
    analysis_policy = (
        experiment.get("analysis_policy") if isinstance(experiment, dict) else None
    )
    clustered_interval = (
        analysis_policy.get("clustered_interval")
        if isinstance(analysis_policy, dict)
        else None
    )
    if not isinstance(clustered_interval, dict) or not {
        "method",
        "confidence",
        "cluster_unit",
        "resamples",
        "seed",
    }.issubset(clustered_interval):
        gaps.append("clustered_interval_not_preregistered")
    thresholds = (
        experiment.get("promotion_thresholds", {}).get("controlled_multi_agent_eval")
        if isinstance(experiment, dict)
        and isinstance(experiment.get("promotion_thresholds"), dict)
        else None
    )
    if not isinstance(thresholds, dict) or any(
        not isinstance(thresholds.get(key), (int, float))
        or float(thresholds[key]) < 0.5
        for key in (
            "minimum_control_pass_rate",
            "minimum_per_fixture_control_pass_rate",
        )
    ):
        gaps.append("control_reliability_floors_not_preregistered")
    configured = policy.get("runner_configurations")
    observed_configurations = [
        {"model": model, "reasoning_effort": effort}
        for model, effort in sorted(
            {(cell.runner_model, cell.runner_effort) for cell in cells}
        )
    ]
    configured_normalized = (
        sorted(
            (
                {
                    "model": str(item.get("model") or ""),
                    "reasoning_effort": str(item.get("reasoning_effort") or ""),
                }
                for item in configured
                if isinstance(item, dict)
            ),
            key=lambda item: (item["model"], item["reasoning_effort"]),
        )
        if isinstance(configured, list)
        else []
    )
    if (
        not isinstance(configured, list)
        or len(configured_normalized) != len(configured)
        or configured_normalized != observed_configurations
    ):
        gaps.append("runner_configuration_matrix_not_preregistered")
    configured_judge = policy.get("judge_configuration")
    if (
        not isinstance(configured_judge, dict)
        or configured_judge.get("model") != judge_model
        or configured_judge.get("reasoning_effort") != judge_effort
    ):
        gaps.append("judge_configuration_not_preregistered")
    runner_models = sorted({cell.runner_model for cell in cells})
    confirmation = policy.get("cross_model_confirmation")
    if not isinstance(confirmation, dict):
        gaps.append("cross_model_confirmation_not_preregistered")
    elif confirmation.get("required") is True:
        minimum_models = int(confirmation.get("minimum_distinct_runner_models") or 2)
        minimum_fixtures = int(confirmation.get("minimum_fixture_count_per_model") or 1)
        minimum_repetitions = int(confirmation.get("minimum_repetitions_per_cell") or 1)
        if len(runner_models) < minimum_models:
            gaps.append("insufficient_distinct_runner_models")
        for model in runner_models:
            model_cells = [cell for cell in cells if cell.runner_model == model]
            if len({cell.fixture_digest for cell in model_cells}) < minimum_fixtures:
                gaps.append(f"insufficient_fixture_coverage_for_{model}")
            repetitions_by_cell: dict[tuple[str, str], int] = {}
            for cell in model_cells:
                key = (cell.matrix_row_id, cell.configuration_id)
                repetitions_by_cell[key] = repetitions_by_cell.get(key, 0) + 1
            if min(repetitions_by_cell.values(), default=0) < minimum_repetitions:
                gaps.append(f"insufficient_repetitions_for_{model}")
        if judge_model in runner_models:
            gaps.append("judge_model_not_independent")
    if design == "baseline_reliability" and {cell.variant_id for cell in cells} != {
        "original"
    }:
        gaps.append("baseline_contains_non_original_variant")
    baseline = policy.get("baseline_reliability")
    if design == "baseline_reliability" and (
        not isinstance(baseline, dict)
        or baseline.get("control_variant") != "original"
        or not isinstance(baseline.get("minimum_control_pass_rate"), (int, float))
        or not isinstance(
            baseline.get("minimum_per_fixture_control_pass_rate"), (int, float)
        )
    ):
        gaps.append("baseline_reliability_not_preregistered")
    fixture_review = policy.get("fixture_review")
    if not isinstance(fixture_review, dict) or any(
        fixture_review.get(field) is not True
        for field in (
            "independent_reviewer",
            "prompt_event_directness",
            "bar_skill_expressibility",
        )
    ):
        gaps.append("fixture_review_not_preregistered")
    return {
        "schema": "tmcp-skill-eval-campaign-readiness-v0.1",
        "ready": not gaps,
        "design": design,
        "runner_models": runner_models,
        "judge_model": judge_model,
        "cell_count": len(cells),
        "gaps": gaps,
    }
