"""Pure provenance and evidence contracts for composition benchmarks."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .composition_benchmark_evaluator import validate_variant_dimension_scores
from .composition_preflight import stable_digest


PASS_STATUSES = {"ok", "pass", "passed", "success", "succeeded", "verified"}
ACCEPTABLE_PHASE_STATUSES = PASS_STATUSES | {"active", "advanced", "unchanged"}
FAIL_STATUSES = {"blocked", "error", "fail", "failed", "failure", "reverted"}


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
    return result


def _string_ids(
    value: object,
    *,
    field: str,
    allow_empty: bool = False,
) -> list[str]:
    if (
        allow_empty
        and isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and not value
    ):
        return []
    return _nonempty_strings(value, field=field)


def _nonempty_strings(value: object, *, field: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of strings.")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain nonempty strings.")
        normalized = item.strip()
        if normalized in seen:
            raise ValueError(f"{field} must contain unique values: {normalized}")
        seen.add(normalized)
        result.append(normalized)
    if not result:
        raise ValueError(f"{field} must not be empty.")
    return result


def _finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric.")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite.")
    return number


def _relationship_source(relationship: Mapping[str, Any]) -> str:
    return str(
        relationship.get("source_id")
        or relationship.get("from")
        or relationship.get("source")
        or ""
    ).strip()


def _relationship_target(relationship: Mapping[str, Any]) -> str:
    return str(
        relationship.get("target_id")
        or relationship.get("to")
        or relationship.get("target")
        or ""
    ).strip()


def active_conflict_violations(
    fixture_id: str,
    fixture: Mapping[str, Any],
    selected_skill_ids: list[str],
    active_stages: list[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    selected = set(selected_skill_ids)
    conflicts = _mapping_list(
        fixture.get("incompatible_skill_pairs", []),
        field=f"{fixture_id}.incompatible_skill_pairs",
    )
    for index, conflict in enumerate(conflicts, start=1):
        pair = _string_ids(
            conflict.get("skill_ids"),
            field=f"{fixture_id}.incompatible_skill_pairs[{index}].skill_ids",
        )
        if len(pair) != 2:
            raise ValueError(f"{fixture_id} conflict pairs require exactly two skills.")
        conflict_id = str(conflict.get("conflict_id") or f"conflict-{index}")
        if conflict.get("same_stage_only", True):
            for stage_index, stage in enumerate(active_stages, start=1):
                active = set(
                    _string_ids(
                        stage.get("active_skill_ids"),
                        field=f"{fixture_id}.active_stages[{stage_index}]",
                        allow_empty=True,
                    )
                )
                if set(pair).issubset(active):
                    violations.append(
                        {
                            "fixture_id": fixture_id,
                            "conflict_id": conflict_id,
                            "stage_id": str(stage.get("stage_id") or stage_index),
                            "skill_ids": pair,
                        }
                    )
        elif set(pair).issubset(selected):
            violations.append(
                {
                    "fixture_id": fixture_id,
                    "conflict_id": conflict_id,
                    "stage_id": None,
                    "skill_ids": pair,
                }
            )
    for index, relationship in enumerate(relationships, start=1):
        relation = str(
            relationship.get("relation") or relationship.get("type") or ""
        ).strip()
        source_id = _relationship_source(relationship)
        target_id = _relationship_target(relationship)
        if (
            relation == "conflicts_with"
            and source_id in selected
            and target_id in selected
        ):
            violations.append(
                {
                    "fixture_id": fixture_id,
                    "conflict_id": f"observed-conflict-{index}",
                    "stage_id": None,
                    "skill_ids": [source_id, target_id],
                }
            )
    return violations


def _quality_rubric(fixture_id: str, fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    rubric = fixture.get("quality_rubric")
    if not isinstance(rubric, Mapping):
        raise ValueError(f"{fixture_id}.quality_rubric is required.")
    for key in ("rubric_id", "version", "aggregation"):
        if not str(rubric.get(key) or "").strip():
            raise ValueError(f"{fixture_id}.quality_rubric.{key} is required.")
    dimensions = _mapping_list(
        rubric.get("dimensions"),
        field=f"{fixture_id}.quality_rubric.dimensions",
    )
    if not dimensions:
        raise ValueError(f"{fixture_id}.quality_rubric.dimensions must not be empty.")
    dimension_ids: set[str] = set()
    total_weight = 0.0
    for index, dimension in enumerate(dimensions, start=1):
        field = f"{fixture_id}.quality_rubric.dimensions[{index}]"
        dimension_id = str(dimension.get("dimension_id") or "").strip()
        criterion = str(dimension.get("criterion") or "").strip()
        if not dimension_id or not criterion:
            raise ValueError(f"{field} requires dimension_id and criterion.")
        if dimension_id in dimension_ids:
            raise ValueError(
                f"{fixture_id} has duplicate rubric dimension {dimension_id}."
            )
        dimension_ids.add(dimension_id)
        total_weight += _finite_number(dimension.get("weight"), field=f"{field}.weight")
        _nonempty_strings(
            dimension.get("evidence_required"),
            field=f"{field}.evidence_required",
        )
    if not math.isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(
            f"{fixture_id}.quality_rubric dimension weights must sum to 1."
        )
    return rubric


def validate_evaluation_provenance(
    fixture_id: str,
    fixture: Mapping[str, Any],
    selected_skill_ids: list[str],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    provenance = observation.get("evaluation_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError(f"{fixture_id}.evaluation_provenance is required.")
    for key in (
        "evaluator_id",
        "evaluator_version",
        "evaluation_run_id",
        "evaluated_at",
        "method",
    ):
        if not str(provenance.get(key) or "").strip():
            raise ValueError(f"{fixture_id}.evaluation_provenance.{key} is required.")
    rubric = _quality_rubric(fixture_id, fixture)
    expected_rubric = {
        "rubric_id": str(rubric["rubric_id"]),
        "rubric_version": str(rubric["version"]),
        "rubric_digest": stable_digest(dict(rubric)),
    }
    for key, expected in expected_rubric.items():
        if str(provenance.get(key) or "").strip() != expected:
            raise ValueError(
                f"{fixture_id}.evaluation_provenance.{key} must match the fixture rubric."
            )
    variant_evidence = provenance.get("variant_evidence")
    if not isinstance(variant_evidence, Mapping):
        raise ValueError(
            f"{fixture_id}.evaluation_provenance.variant_evidence is required."
        )
    required_variants = {
        "no_skill",
        "naive_union",
        "full_composition",
        "wrong_order",
        *(f"singleton:{skill_id}" for skill_id in selected_skill_ids),
        *(f"leave_one_out:{skill_id}" for skill_id in selected_skill_ids),
    }
    observed_variants = {str(key) for key in variant_evidence}
    if observed_variants != required_variants:
        raise ValueError(
            f"{fixture_id}.evaluation_provenance.variant_evidence must cover every "
            f"control exactly; missing={sorted(required_variants - observed_variants)}, "
            f"unexpected={sorted(observed_variants - required_variants)}."
        )
    for variant_id, evidence_refs in variant_evidence.items():
        _nonempty_strings(
            evidence_refs,
            field=(f"{fixture_id}.evaluation_provenance.variant_evidence.{variant_id}"),
        )
    validate_variant_dimension_scores(
        fixture_id,
        rubric,
        selected_skill_ids,
        observation,
        provenance,
        required_variants,
    )
    return {
        **expected_rubric,
        "evaluator_id": str(provenance["evaluator_id"]),
        "evaluator_version": str(provenance["evaluator_version"]),
        "evaluation_run_id": str(provenance["evaluation_run_id"]),
        "evaluated_at": str(provenance["evaluated_at"]),
        "method": str(provenance["method"]),
    }


def validate_run_identity_and_receipt(
    fixture_id: str,
    selected_skill_ids: list[str],
    source_slices: Sequence[Mapping[str, Any]],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    preflight_id = str(observation.get("preflight_id") or "").strip()
    composition_plan_id = str(observation.get("composition_plan_id") or "").strip()
    graph_digest = str(observation.get("graph_digest") or "").strip()
    if re.fullmatch(r"preflight-[a-f0-9]{20}", preflight_id) is None:
        raise ValueError(f"{fixture_id}.preflight_id is invalid.")
    if re.fullmatch(r"composition-[a-f0-9]{20}", composition_plan_id) is None:
        raise ValueError(f"{fixture_id}.composition_plan_id is invalid.")
    if re.fullmatch(r"[a-f0-9]{32}", graph_digest) is None:
        raise ValueError(f"{fixture_id}.graph_digest is invalid.")
    task_identity = observation.get("task_identity")
    if (
        not isinstance(task_identity, Mapping)
        or not str(task_identity.get("primary") or "").strip()
    ):
        raise ValueError(f"{fixture_id}.task_identity with primary is required.")
    receipt = observation.get("run_receipt")
    if not isinstance(receipt, Mapping):
        raise ValueError(f"{fixture_id}.run_receipt is required.")
    if receipt.get("schema") != "tmcp-run-receipt-v0.1":
        raise ValueError(f"{fixture_id}.run_receipt.schema is invalid.")
    if str(receipt.get("recipe_id") or "").strip() != composition_plan_id:
        raise ValueError(
            f"{fixture_id}.run_receipt.recipe_id must match composition_plan_id."
        )
    if receipt.get("task_identity") != task_identity:
        raise ValueError(
            f"{fixture_id}.run_receipt.task_identity must match the observation."
        )
    if str(receipt.get("graph_digest") or "").strip() != graph_digest:
        raise ValueError(
            f"{fixture_id}.run_receipt.graph_digest must match the observation."
        )
    receipt_skill_ids = _string_ids(
        receipt.get("selected_skill_ids"),
        field=f"{fixture_id}.run_receipt.selected_skill_ids",
    )
    source_node_by_skill = {
        str(source_slice.get("skill_id") or "").strip(): str(
            source_slice.get("source_node_id") or ""
        ).strip()
        for source_slice in source_slices
    }
    expected_source_node_ids = [
        source_node_by_skill[skill_id] for skill_id in selected_skill_ids
    ]
    if receipt_skill_ids != expected_source_node_ids:
        raise ValueError(
            f"{fixture_id}.run_receipt.selected_skill_ids must match bound "
            "source_node_id values."
        )
    source_content_digests = sorted(
        {
            str(source_slice.get("content_digest") or "").strip()
            for source_slice in source_slices
        }
    )
    receipt_content_digests = sorted(
        _nonempty_strings(
            receipt.get("content_digests"),
            field=f"{fixture_id}.run_receipt.content_digests",
        )
    )
    if receipt_content_digests != source_content_digests:
        raise ValueError(
            f"{fixture_id}.run_receipt.content_digests must match source_slices."
        )
    phase_trace = _mapping_list(
        receipt.get("phase_trace"),
        field=f"{fixture_id}.run_receipt.phase_trace",
    )
    if not phase_trace or any(
        not (
            str(item.get("phase") or "").strip()
            or str(item.get("from_phase") or "").strip()
            or str(item.get("to_phase") or "").strip()
        )
        or str(item.get("status") or "").strip().lower()
        not in ACCEPTABLE_PHASE_STATUSES
        for item in phase_trace
    ):
        raise ValueError(
            f"{fixture_id}.run_receipt.phase_trace requires passing phase results."
        )
    gate_results = _mapping_list(
        receipt.get("gate_results"),
        field=f"{fixture_id}.run_receipt.gate_results",
    )
    if not gate_results or any(
        not str(item.get("gate_id") or item.get("id") or "").strip()
        or (
            item.get("passed") is not True
            and str(item.get("status") or "").strip().lower() not in PASS_STATUSES
        )
        or item.get("passed") is False
        or str(item.get("status") or "").strip().lower() in FAIL_STATUSES
        for item in gate_results
    ):
        raise ValueError(
            f"{fixture_id}.run_receipt.gate_results requires explicit passing gates."
        )
    overrides = receipt.get("user_overrides")
    if not isinstance(overrides, list) or overrides:
        raise ValueError(
            f"{fixture_id}.run_receipt.user_overrides must be an empty array."
        )
    if str(receipt.get("outcome") or "").strip().lower() not in PASS_STATUSES:
        raise ValueError(f"{fixture_id}.run_receipt.outcome must be passing.")
    return dict(receipt)


def validate_receipt_metrics(
    fixture_id: str,
    receipt: Mapping[str, Any],
    quality: Mapping[str, Any],
    *,
    compiled_tokens: float,
    context_ratio: float,
) -> None:
    quality_metrics = receipt.get("quality_metrics")
    if not isinstance(quality_metrics, Mapping):
        raise ValueError(f"{fixture_id}.run_receipt.quality_metrics is required.")
    for key in ("synergy_lift", "compiler_lift", "order_lift"):
        observed = _finite_number(
            quality_metrics.get(key),
            field=f"{fixture_id}.run_receipt.quality_metrics.{key}",
        )
        if not math.isclose(observed, float(quality[key]), abs_tol=1e-9):
            raise ValueError(
                f"{fixture_id}.run_receipt.quality_metrics.{key} must match "
                "the observed variant scores."
            )
    cost_metrics = receipt.get("cost_metrics")
    if not isinstance(cost_metrics, Mapping):
        raise ValueError(f"{fixture_id}.run_receipt.cost_metrics is required.")
    receipt_tokens = _finite_number(
        cost_metrics.get("context_tokens"),
        field=f"{fixture_id}.run_receipt.cost_metrics.context_tokens",
    )
    receipt_ratio = _finite_number(
        cost_metrics.get("context_ratio"),
        field=f"{fixture_id}.run_receipt.cost_metrics.context_ratio",
    )
    if not math.isclose(
        receipt_tokens, compiled_tokens, abs_tol=1e-9
    ) or not math.isclose(
        receipt_ratio,
        context_ratio,
        abs_tol=1e-9,
    ):
        raise ValueError(
            f"{fixture_id}.run_receipt.cost_metrics must match observed context cost."
        )
