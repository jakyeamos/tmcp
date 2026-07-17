"""Pure acceptance metrics for observed compositional-intelligence benchmark runs."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from .composition_benchmark_contracts import (
    active_conflict_violations,
    validate_evaluation_provenance,
    validate_receipt_metrics,
    validate_run_identity_and_receipt,
)
from .composition_benchmark_context import validate_projected_execution_context
from .composition_benchmark_manifests import (
    validate_behavioral_manifests,
)
from .composition_benchmark_routing import score_routing_benchmark
from .composition_benchmark_sources import (
    graph_digest_for_observation,
    relationship_provenance_is_complete,
    validate_fixture_skill_sources,
    validate_source_slice_bindings,
)


COMPOSITION_BENCHMARK_SCHEMA = "tmcp-composition-benchmark-summary-v0.1"
DEFAULT_THRESHOLDS = {
    "expected_skill_recall": 1.0,
    "selected_skill_precision": 0.90,
    "provenance_relationship_coverage": 1.0,
    "synergy_lift": 0.10,
    "compiler_lift": 0.05,
    "order_lift": 0.05,
    "maximum_context_ratio": 0.75,
    "order_match_rate": 1.0,
}


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
    return result


def _string_ids(value: object, *, field: str, allow_empty: bool = False) -> list[str]:
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


def _quality_score(value: object, *, field: str) -> float:
    score = _finite_number(value, field=field)
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1.")
    return score


def _rounded(value: float) -> float:
    return round(value, 4)


def _ratio(numerator: int, denominator: int) -> float:
    return _rounded(numerator / denominator) if denominator else 0.0


def _relationship_target(relationship: Mapping[str, Any]) -> str:
    return str(
        relationship.get("target_id")
        or relationship.get("to")
        or relationship.get("target")
        or ""
    ).strip()


def _relationship_type(relationship: Mapping[str, Any]) -> str:
    return str(relationship.get("type") or relationship.get("relation") or "").strip()


def _relationship_key(relationship: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _relationship_source(relationship),
        _relationship_target(relationship),
        _relationship_type(relationship),
    )


def _relationship_source(relationship: Mapping[str, Any]) -> str:
    return str(
        relationship.get("source_id")
        or relationship.get("from")
        or relationship.get("source")
        or ""
    ).strip()


def _fixture_quality_metrics(
    fixture_id: str,
    selected_skill_ids: list[str],
    observation: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, float]]:
    quality_scores = observation.get("quality_scores")
    if not isinstance(quality_scores, Mapping):
        raise ValueError(f"{fixture_id}.quality_scores must be supplied by the run.")
    singleton_scores = quality_scores.get("singletons")
    if not isinstance(singleton_scores, Mapping):
        raise ValueError(f"{fixture_id}.quality_scores.singletons is required.")
    singleton_skill_ids = {str(key) for key in singleton_scores}
    if singleton_skill_ids != set(selected_skill_ids):
        raise ValueError(
            f"{fixture_id}.quality_scores.singletons must cover every selected skill."
        )
    normalized_singletons = {
        str(skill_id): _quality_score(
            value,
            field=f"{fixture_id}.quality_scores.singletons.{skill_id}",
        )
        for skill_id, value in singleton_scores.items()
    }
    leave_one_out_scores = quality_scores.get("leave_one_out")
    if not isinstance(leave_one_out_scores, Mapping):
        raise ValueError(f"{fixture_id}.quality_scores.leave_one_out is required.")
    if {str(key) for key in leave_one_out_scores} != set(selected_skill_ids):
        raise ValueError(
            f"{fixture_id}.quality_scores.leave_one_out must cover every selected skill."
        )
    normalized_leave_one_out = {
        str(skill_id): _quality_score(
            value,
            field=f"{fixture_id}.quality_scores.leave_one_out.{skill_id}",
        )
        for skill_id, value in leave_one_out_scores.items()
    }
    no_skill = _quality_score(
        quality_scores.get("no_skill"),
        field=f"{fixture_id}.quality_scores.no_skill",
    )
    full = _quality_score(
        quality_scores.get("full_composition"),
        field=f"{fixture_id}.quality_scores.full_composition",
    )
    naive = _quality_score(
        quality_scores.get("naive_union"),
        field=f"{fixture_id}.quality_scores.naive_union",
    )
    wrong_order = _quality_score(
        quality_scores.get("wrong_order"),
        field=f"{fixture_id}.quality_scores.wrong_order",
    )
    best_skill_id, best_singleton = max(
        normalized_singletons.items(),
        key=lambda item: (item[1], item[0]),
    )
    raw_lifts = {
        "synergy_lift": full - best_singleton,
        "compiler_lift": full - naive,
        "order_lift": full - wrong_order,
    }
    return {
        "best_singleton": {
            "skill_id": best_skill_id,
            "quality_score": best_singleton,
        },
        "no_skill_quality": no_skill,
        "full_composition_quality": full,
        "naive_union_quality": naive,
        "wrong_order_quality": wrong_order,
        "synergy_lift": _rounded(raw_lifts["synergy_lift"]),
        "compiler_lift": _rounded(raw_lifts["compiler_lift"]),
        "order_lift": _rounded(raw_lifts["order_lift"]),
        "leave_one_out_lifts": {
            skill_id: _rounded(full - score)
            for skill_id, score in sorted(normalized_leave_one_out.items())
        },
    }, raw_lifts


def _score_behavioral_benchmark(
    fixture_definitions: Sequence[Mapping[str, Any]],
    observed_results: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, float]]:
    fixtures = _mapping_list(fixture_definitions, field="fixture_definitions")
    observations = _mapping_list(observed_results, field="observed_results")
    fixture_index = _indexed(fixtures, id_field="fixture_id", collection="fixture")
    observation_index = _indexed(
        observations,
        id_field="fixture_id",
        collection="fixture observation",
    )
    missing = sorted(set(fixture_index).difference(observation_index))
    unexpected = sorted(set(observation_index).difference(fixture_index))
    if missing or unexpected:
        raise ValueError(
            "Behavioral observations must match fixture ids exactly; "
            f"missing={missing}, unexpected={unexpected}."
        )

    fixture_metrics: list[dict[str, Any]] = []
    all_violations: list[dict[str, Any]] = []
    missing_incoming: list[dict[str, str]] = []
    missing_expected_relationships: list[dict[str, str]] = []
    expected_relationship_count = 0
    matched_expected_relationship_count = 0
    selected_non_root_count = 0
    incoming_relationship_count = 0
    total_compiled_tokens = 0.0
    total_naive_tokens = 0.0
    synergy_lifts: list[float] = []
    compiler_lifts: list[float] = []
    order_lifts: list[float] = []
    context_ratios: list[float] = []
    qualified_context_execution_count = 0
    unqualified_context_execution_fixtures: list[str] = []

    for fixture_id, fixture in fixture_index.items():
        observation = observation_index[fixture_id]
        skill_sources = validate_fixture_skill_sources(fixture_id, fixture)
        expected = _string_ids(
            fixture.get("expected_skill_ids"),
            field=f"{fixture_id}.expected_skill_ids",
        )
        expected_order = _string_ids(
            fixture.get("expected_order"),
            field=f"{fixture_id}.expected_order",
        )
        selected = _string_ids(
            observation.get("selected_skill_ids"),
            field=f"{fixture_id}.selected_skill_ids",
        )
        (
            source_slice_bindings,
            source_slice_ids,
            source_node_by_skill,
            source_slices_by_id,
        ) = validate_source_slice_bindings(
            fixture_id,
            selected,
            observation,
            skill_sources,
        )
        source_slices = _mapping_list(
            observation.get("source_slices"),
            field=f"{fixture_id}.source_slices",
        )
        run_receipt = validate_run_identity_and_receipt(
            fixture_id,
            selected,
            source_slices,
            observation,
        )
        context_accounting = observation.get("context_accounting")
        if not isinstance(context_accounting, Mapping):
            raise ValueError(f"{fixture_id}.context_accounting is required.")
        execution_context = validate_projected_execution_context(
            run_receipt,
            context_accounting=context_accounting,
        )
        if observation.get("context_execution_mode") != execution_context[
            "execution_context_mode"
        ]:
            raise ValueError(
                f"{fixture_id}.context_execution_mode must match the run receipt."
            )
        evaluation_provenance = validate_evaluation_provenance(
            fixture_id,
            fixture,
            selected,
            observation,
        )
        ordered = _string_ids(
            observation.get("ordered_skill_ids"),
            field=f"{fixture_id}.ordered_skill_ids",
        )
        if set(ordered) != set(selected):
            raise ValueError(
                f"{fixture_id}.ordered_skill_ids must contain every selected skill once."
            )
        active_stages = _mapping_list(
            observation.get("active_stages"),
            field=f"{fixture_id}.active_stages",
        )
        active_skill_order = [
            skill_id
            for index, stage in enumerate(active_stages, start=1)
            for skill_id in _string_ids(
                stage.get("active_skill_ids"),
                field=f"{fixture_id}.active_stages[{index}]",
                allow_empty=True,
            )
        ]
        if active_skill_order != ordered:
            raise ValueError(
                f"{fixture_id}.active_stages must cover ordered skills exactly once."
            )
        relationships = _mapping_list(
            observation.get("relationships"),
            field=f"{fixture_id}.relationships",
        )
        violations = active_conflict_violations(
            fixture_id,
            fixture,
            selected,
            active_stages,
            relationships,
        )
        all_violations.extend(violations)

        incomplete_relationships = [
            relationship
            for relationship in relationships
            if not relationship_provenance_is_complete(
                fixture_id,
                relationship,
                bindings=source_slice_bindings,
                slice_ids=source_slice_ids,
            )
        ]
        if incomplete_relationships:
            raise ValueError(
                f"{fixture_id} relationship citations must cover both endpoint "
                "skills from source_slices."
            )
        expected_graph_digest = graph_digest_for_observation(
            selected,
            relationships,
            source_node_by_skill=source_node_by_skill,
            slices_by_id=source_slices_by_id,
        )
        if str(observation.get("graph_digest") or "") != expected_graph_digest:
            raise ValueError(
                f"{fixture_id}.graph_digest must match source content and relationships."
            )
        expected_relationships = _mapping_list(
            fixture.get("expected_relationships"),
            field=f"{fixture_id}.expected_relationships",
        )
        observed_relationships = {
            _relationship_key(relationship) for relationship in relationships
        }
        fixture_missing_expected = [
            relationship
            for relationship in expected_relationships
            if _relationship_key(relationship) not in observed_relationships
        ]
        expected_relationship_count += len(expected_relationships)
        matched_expected_relationship_count += len(expected_relationships) - len(
            fixture_missing_expected
        )
        missing_expected_relationships.extend(
            {
                "fixture_id": fixture_id,
                "relationship": " ".join(_relationship_key(relationship)),
            }
            for relationship in fixture_missing_expected
        )
        root_node_id = str(fixture.get("root_node_id") or "").strip()
        non_root_selected = [item for item in selected if item != root_node_id]
        incoming_targets = {
            _relationship_target(relationship)
            for relationship in relationships
            if _relationship_source(relationship)
            and _relationship_source(relationship) != _relationship_target(relationship)
        }
        fixture_missing_incoming = [
            skill_id
            for skill_id in non_root_selected
            if skill_id not in incoming_targets
        ]
        missing_incoming.extend(
            {"fixture_id": fixture_id, "skill_id": skill_id}
            for skill_id in fixture_missing_incoming
        )
        selected_non_root_count += len(non_root_selected)
        incoming_relationship_count += len(non_root_selected) - len(
            fixture_missing_incoming
        )

        compiled_tokens = _finite_number(
            observation.get("compiled_context_tokens"),
            field=f"{fixture_id}.compiled_context_tokens",
        )
        naive_tokens = _finite_number(
            observation.get("naive_context_tokens"),
            field=f"{fixture_id}.naive_context_tokens",
        )
        if compiled_tokens < 0 or naive_tokens <= 0:
            raise ValueError(
                f"{fixture_id} context tokens require compiled >= 0 and naive > 0."
            )
        expected_compiled_tokens = _finite_number(
            context_accounting.get("runtime_peak_context_tokens"),
            field=f"{fixture_id}.context_accounting.runtime_peak_context_tokens",
        )
        expected_naive_tokens = _finite_number(
            context_accounting.get("naive_union_context_tokens"),
            field=f"{fixture_id}.context_accounting.naive_union_context_tokens",
        )
        if (
            not math.isclose(
                compiled_tokens,
                expected_compiled_tokens,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or not math.isclose(
                naive_tokens,
                expected_naive_tokens,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError(
                f"{fixture_id} context aliases must match compiler phase accounting."
            )
        raw_context_ratio = compiled_tokens / naive_tokens
        context_ratio = _rounded(raw_context_ratio)
        total_compiled_tokens += compiled_tokens
        total_naive_tokens += naive_tokens
        context_ratios.append(raw_context_ratio)
        if execution_context["qualified"]:
            qualified_context_execution_count += 1
        else:
            unqualified_context_execution_fixtures.append(fixture_id)

        quality, raw_lifts = _fixture_quality_metrics(fixture_id, selected, observation)
        validate_behavioral_manifests(fixture, observation, selected)
        validate_receipt_metrics(
            fixture_id,
            run_receipt,
            quality,
            compiled_tokens=compiled_tokens,
            context_ratio=context_ratio,
        )
        synergy_lifts.append(raw_lifts["synergy_lift"])
        compiler_lifts.append(raw_lifts["compiler_lift"])
        order_lifts.append(raw_lifts["order_lift"])
        expected_set = set(expected)
        selected_set = set(selected)
        matched = expected_set.intersection(selected_set)
        fixture_metrics.append(
            {
                "fixture_id": fixture_id,
                "expected_skill_recall": _ratio(len(matched), len(expected)),
                "selected_skill_precision": _ratio(len(matched), len(selected)),
                "order_matches_expected": ordered == expected_order,
                "active_conflict_violation_count": len(violations),
                "missing_incoming_relationship_skill_ids": fixture_missing_incoming,
                "missing_expected_relationships": [
                    " ".join(_relationship_key(relationship))
                    for relationship in fixture_missing_expected
                ],
                "provenance_relationship_coverage": _ratio(
                    len(non_root_selected) - len(fixture_missing_incoming),
                    len(non_root_selected),
                ),
                "context_ratio": context_ratio,
                "context_execution_mode": execution_context[
                    "execution_context_mode"
                ],
                "quality_metrics": quality,
                "evaluation_provenance": evaluation_provenance,
                "preflight_id": str(observation["preflight_id"]),
                "composition_plan_id": str(observation["composition_plan_id"]),
                "graph_digest": str(observation["graph_digest"]),
            }
        )

    raw_acceptance = {
        "context_ratio": total_compiled_tokens / total_naive_tokens,
        "maximum_fixture_context_ratio": max(context_ratios),
        "synergy_lift": median(synergy_lifts),
        "compiler_lift": median(compiler_lifts),
        "order_lift": median(order_lifts),
        "context_execution_mode": not unqualified_context_execution_fixtures,
    }
    return {
        "fixture_count": len(fixtures),
        "active_conflict_violation_count": len(all_violations),
        "active_conflict_violations": all_violations,
        "selected_non_root_skill_count": selected_non_root_count,
        "incoming_provenance_relationship_count": incoming_relationship_count,
        "missing_incoming_relationships": missing_incoming,
        "expected_relationship_count": expected_relationship_count,
        "matched_expected_relationship_count": matched_expected_relationship_count,
        "missing_expected_relationships": missing_expected_relationships,
        "expected_relationship_coverage": _ratio(
            matched_expected_relationship_count,
            expected_relationship_count,
        ),
        "provenance_relationship_coverage": _ratio(
            incoming_relationship_count,
            selected_non_root_count,
        ),
        "context_ratio": _rounded(total_compiled_tokens / total_naive_tokens),
        "maximum_fixture_context_ratio": _rounded(max(context_ratios)),
        "qualified_context_execution_count": qualified_context_execution_count,
        "unqualified_context_execution_fixtures": unqualified_context_execution_fixtures,
        "quality_metrics": {
            "synergy_lift": _rounded(median(synergy_lifts)),
            "compiler_lift": _rounded(median(compiler_lifts)),
            "order_lift": _rounded(median(order_lifts)),
        },
        "order_match_rate": _ratio(
            sum(1 for item in fixture_metrics if item["order_matches_expected"]),
            len(fixture_metrics),
        ),
        "fixtures": fixture_metrics,
    }, raw_acceptance


def score_behavioral_benchmark(
    fixture_definitions: Sequence[Mapping[str, Any]],
    observed_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    metrics, _ = _score_behavioral_benchmark(fixture_definitions, observed_results)
    return metrics


def score_composition_benchmark(
    *,
    golden_cases: Sequence[Mapping[str, Any]],
    fixture_definitions: Sequence[Mapping[str, Any]],
    routing_results: Sequence[Mapping[str, Any]],
    behavioral_results: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Score one complete observed benchmark run against the 0.6 acceptance gates."""

    resolved_thresholds = dict(DEFAULT_THRESHOLDS)
    for key, value in (thresholds or {}).items():
        if key not in resolved_thresholds:
            raise ValueError(f"Unknown composition benchmark threshold: {key}")
        resolved_thresholds[key] = _finite_number(value, field=f"thresholds.{key}")
    routing = score_routing_benchmark(golden_cases, routing_results)
    behavioral, raw_behavioral = _score_behavioral_benchmark(
        fixture_definitions,
        behavioral_results,
    )
    checks = {
        "expected_skill_recall": (
            routing["expected_skill_recall"]
            >= resolved_thresholds["expected_skill_recall"]
        ),
        "selected_skill_precision": (
            routing["selected_skill_precision"]
            >= resolved_thresholds["selected_skill_precision"]
        ),
        "active_conflict_violations": (
            behavioral["active_conflict_violation_count"] == 0
        ),
        "incoming_provenance_relationships": (
            behavioral["provenance_relationship_coverage"]
            >= resolved_thresholds["provenance_relationship_coverage"]
            and behavioral["expected_relationship_coverage"]
            >= resolved_thresholds["provenance_relationship_coverage"]
        ),
        "expected_order": (
            behavioral["order_match_rate"] >= resolved_thresholds["order_match_rate"]
        ),
        "context_ratio": (
            raw_behavioral["context_ratio"]
            <= resolved_thresholds["maximum_context_ratio"]
            and raw_behavioral["maximum_fixture_context_ratio"]
            <= resolved_thresholds["maximum_context_ratio"]
        ),
        "context_execution_mode": raw_behavioral["context_execution_mode"],
        "synergy_lift": (
            raw_behavioral["synergy_lift"] >= resolved_thresholds["synergy_lift"]
        ),
        "compiler_lift": (
            raw_behavioral["compiler_lift"] >= resolved_thresholds["compiler_lift"]
        ),
        "order_lift": (
            raw_behavioral["order_lift"] >= resolved_thresholds["order_lift"]
        ),
    }
    return {
        "schema": COMPOSITION_BENCHMARK_SCHEMA,
        "eligible": all(checks.values()),
        "failed_checks": [check for check, passed in checks.items() if not passed],
        "acceptance_checks": checks,
        "thresholds": resolved_thresholds,
        "routing_metrics": routing,
        "behavioral_metrics": behavioral,
    }
