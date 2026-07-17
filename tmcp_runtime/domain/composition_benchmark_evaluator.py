"""Reviewable rubric scoring contract for composition benchmark observations."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
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


def validate_variant_dimension_scores(
    fixture_id: str,
    rubric: Mapping[str, Any],
    selected_skill_ids: list[str],
    observation: Mapping[str, Any],
    provenance: Mapping[str, Any],
    required_variants: set[str],
) -> None:
    variant_dimension_scores = provenance.get("variant_dimension_scores")
    if not isinstance(variant_dimension_scores, Mapping):
        raise ValueError(
            f"{fixture_id}.evaluation_provenance.variant_dimension_scores is required."
        )
    dimension_weights = {
        str(dimension["dimension_id"]): _finite_number(
            dimension["weight"],
            field=(
                f"{fixture_id}.quality_rubric.dimensions."
                f"{dimension['dimension_id']}.weight"
            ),
        )
        for dimension in _mapping_list(
            rubric.get("dimensions"),
            field=f"{fixture_id}.quality_rubric.dimensions",
        )
    }
    if {str(key) for key in variant_dimension_scores} != required_variants:
        raise ValueError(
            f"{fixture_id}.evaluation_provenance.variant_dimension_scores must "
            "cover every control exactly."
        )
    quality_scores = observation.get("quality_scores")
    if not isinstance(quality_scores, Mapping):
        raise ValueError(f"{fixture_id}.quality_scores must be supplied by the run.")
    singleton_scores = quality_scores.get("singletons")
    leave_one_out_scores = quality_scores.get("leave_one_out")
    if not isinstance(singleton_scores, Mapping) or not isinstance(
        leave_one_out_scores, Mapping
    ):
        raise ValueError(
            f"{fixture_id}.quality_scores requires singleton and leave-one-out maps."
        )
    expected_quality_scores = {
        "no_skill": quality_scores.get("no_skill"),
        "naive_union": quality_scores.get("naive_union"),
        "full_composition": quality_scores.get("full_composition"),
        "wrong_order": quality_scores.get("wrong_order"),
        **{
            f"singleton:{skill_id}": singleton_scores.get(skill_id)
            for skill_id in selected_skill_ids
        },
        **{
            f"leave_one_out:{skill_id}": leave_one_out_scores.get(skill_id)
            for skill_id in selected_skill_ids
        },
    }
    for variant_id, raw_scores in variant_dimension_scores.items():
        if not isinstance(raw_scores, Mapping):
            raise ValueError(
                f"{fixture_id}.evaluation_provenance.variant_dimension_scores."
                f"{variant_id} must be an object."
            )
        scores = {
            str(key): _finite_number(
                value,
                field=(
                    f"{fixture_id}.evaluation_provenance.variant_dimension_scores."
                    f"{variant_id}.{key}"
                ),
            )
            for key, value in raw_scores.items()
        }
        if set(scores) != set(dimension_weights) or any(
            score < 0.0 or score > 1.0 for score in scores.values()
        ):
            raise ValueError(
                f"{fixture_id} variant {variant_id} must score every rubric "
                "dimension from 0 to 1."
            )
        weighted_score = sum(
            scores[dimension_id] * weight
            for dimension_id, weight in dimension_weights.items()
        )
        reported_score = _finite_number(
            expected_quality_scores[variant_id],
            field=f"{fixture_id}.quality_scores.{variant_id}",
        )
        if not math.isclose(weighted_score, reported_score, abs_tol=1e-9):
            raise ValueError(
                f"{fixture_id} variant {variant_id} quality score must equal its "
                "rubric-weighted dimension score."
            )
