"""Pure routing metrics for composition benchmark observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .composition_benchmark_manifests import validate_routing_manifests


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
    return result


def _string_ids(
    value: object, *, field: str, allow_empty: bool = False
) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of skill ids.")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        skill_id = str(item).strip()
        if not skill_id:
            raise ValueError(f"{field} must contain nonempty skill ids.")
        if skill_id in seen:
            raise ValueError(f"{field} must contain unique skill ids: {skill_id}")
        seen.add(skill_id)
        result.append(skill_id)
    if not result and not allow_empty:
        raise ValueError(f"{field} must not be empty.")
    return result


def _indexed(
    values: Sequence[Mapping[str, Any]],
    *,
    id_field: str,
    collection: str,
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for value in values:
        item_id = str(value.get(id_field) or "").strip()
        if not item_id:
            raise ValueError(f"Every {collection} item requires {id_field}.")
        if item_id in indexed:
            raise ValueError(f"Duplicate {collection} {id_field}: {item_id}")
        indexed[item_id] = value
    return indexed


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def score_routing_benchmark(
    golden_cases: Sequence[Mapping[str, Any]],
    observed_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Score expected-skill recall and selected-skill precision."""

    cases = _mapping_list(golden_cases, field="golden_cases")
    results = _mapping_list(observed_results, field="observed_results")
    case_index = _indexed(cases, id_field="case_id", collection="routing case")
    result_index = _indexed(
        results,
        id_field="case_id",
        collection="routing observation",
    )
    missing = sorted(set(case_index).difference(result_index))
    unexpected = sorted(set(result_index).difference(case_index))
    if missing or unexpected:
        raise ValueError(
            "Routing observations must match golden case ids exactly; "
            f"missing={missing}, unexpected={unexpected}."
        )

    expected_total = 0
    selected_total = 0
    matched_total = 0
    case_metrics: list[dict[str, Any]] = []
    for case_id, case in case_index.items():
        expected = _string_ids(
            case.get("expected_skill_ids"),
            field=f"{case_id}.expected_skill_ids",
        )
        observation = result_index[case_id]
        selected = _string_ids(
            observation.get("selected_skill_ids"),
            field=f"{case_id}.selected_skill_ids",
            allow_empty=True,
        )
        validate_routing_manifests(case, observation, selected)
        expected_set = set(expected)
        selected_set = set(selected)
        matched = expected_set.intersection(selected_set)
        expected_total += len(expected)
        selected_total += len(selected)
        matched_total += len(matched)
        case_metrics.append(
            {
                "case_id": case_id,
                "matched_skill_ids": sorted(matched),
                "missing_skill_ids": sorted(expected_set.difference(selected_set)),
                "unexpected_skill_ids": sorted(selected_set.difference(expected_set)),
                "expected_skill_recall": _ratio(len(matched), len(expected)),
                "selected_skill_precision": _ratio(len(matched), len(selected)),
            }
        )
    return {
        "case_count": len(cases),
        "observed_case_count": len(results),
        "missing_case_ids": [],
        "expected_skill_count": expected_total,
        "selected_skill_count": selected_total,
        "matched_skill_count": matched_total,
        "expected_skill_recall": _ratio(matched_total, expected_total),
        "selected_skill_precision": _ratio(matched_total, selected_total),
        "cases": case_metrics,
    }
