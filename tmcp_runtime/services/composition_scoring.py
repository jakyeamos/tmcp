"""Deterministic ablation-matrix construction and scoring for compositions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.services.composition_evaluation import (
    COMPOSITION_EVALUATION_SCHEMA,
    _SINGLE_VARIANT_KINDS,
    _context_tokens,
    _quality_score,
    _safety_failures,
    _single_result,
    _variant_kind,
    _variant_skill_id,
)


def _skill_ids(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError("Composition skill ids must be a sequence of strings.")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Composition skill ids must be nonempty strings.")
        skill_id = value.strip()
        if skill_id in seen:
            raise ValueError(f"Composition skill ids must be unique: {skill_id}")
        seen.add(skill_id)
        result.append(skill_id)
    if len(result) < 2:
        raise ValueError("Composition evaluation requires at least two skills.")
    return result


def _variant(
    variant_id: str,
    variant_kind: str,
    skill_ids: Sequence[str],
    *,
    composition_enabled: bool,
    omitted_skill_ids: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "variant_id": variant_id,
        "variant_kind": variant_kind,
        "selected_skill_ids": list(skill_ids),
        "ordered_skill_ids": list(skill_ids),
        "omitted_skill_ids": list(omitted_skill_ids),
        "composition_enabled": composition_enabled,
    }


def build_composition_evaluation_variants(
    selected_skill_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Build the complete deterministic ablation matrix for one composition."""

    skill_ids = _skill_ids(selected_skill_ids)
    variants = [
        _variant("baseline", "no_skill", [], composition_enabled=False),
        _variant(
            "naive_union",
            "naive_union",
            skill_ids,
            composition_enabled=False,
        ),
    ]
    variants.extend(
        _variant(
            f"singleton:{skill_id}",
            "singleton",
            [skill_id],
            composition_enabled=False,
            omitted_skill_ids=[item for item in skill_ids if item != skill_id],
        )
        for skill_id in skill_ids
    )
    variants.append(
        _variant(
            "full_composition",
            "full_composition",
            skill_ids,
            composition_enabled=True,
        )
    )
    variants.extend(
        _variant(
            f"leave_one_out:{skill_id}",
            "leave_one_out",
            [item for item in skill_ids if item != skill_id],
            composition_enabled=True,
            omitted_skill_ids=[skill_id],
        )
        for skill_id in skill_ids
    )
    variants.append(
        _variant(
            "wrong_order",
            "wrong_order",
            list(reversed(skill_ids)),
            composition_enabled=True,
        )
    )
    return variants


def score_composition_results(
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute normalized composition lift and context metrics from run results."""

    if isinstance(results, (str, bytes)) or not results:
        raise ValueError("Composition results must be a nonempty sequence.")
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw_result in results:
        if not isinstance(raw_result, Mapping):
            raise ValueError("Each composition result must be an object.")
        variant_id = str(raw_result.get("variant_id") or "").strip()
        if not variant_id:
            raise ValueError("Each composition result requires variant_id.")
        if variant_id in seen_ids:
            raise ValueError(
                f"Composition result variant_id must be unique: {variant_id}"
            )
        seen_ids.add(variant_id)
        variant_kind = _variant_kind(raw_result, variant_id)
        if variant_kind not in {
            "no_skill",
            "naive_union",
            "singleton",
            "full_composition",
            "leave_one_out",
            "wrong_order",
        }:
            raise ValueError(f"Unsupported composition variant: {variant_id}")
        result = {
            "variant_id": variant_id,
            "variant_kind": variant_kind,
            "skill_id": _variant_skill_id(raw_result, variant_id),
            "quality_score": _quality_score(raw_result, variant_id=variant_id),
            "safety_failures": _safety_failures(raw_result),
            "raw": raw_result,
        }
        normalized.append(result)
        grouped.setdefault(variant_kind, []).append(result)

    baseline = _single_result(grouped, "no_skill")
    naive_union = _single_result(grouped, "naive_union")
    full = _single_result(grouped, "full_composition")
    wrong_order = _single_result(grouped, "wrong_order")
    singletons = grouped.get("singleton", [])
    leave_one_out = grouped.get("leave_one_out", [])
    if not singletons:
        raise ValueError("Composition results require every singleton variant.")
    if not leave_one_out:
        raise ValueError("Composition results require every leave-one-out variant.")
    singleton_ids = {item["skill_id"] for item in singletons if item["skill_id"]}
    leave_one_out_ids = {
        item["skill_id"] for item in leave_one_out if item["skill_id"]
    }
    if (
        len(singleton_ids) != len(singletons)
        or len(leave_one_out_ids) != len(leave_one_out)
        or singleton_ids != leave_one_out_ids
    ):
        raise ValueError(
            "Singleton and leave-one-out results must cover the same unique skill ids."
        )

    best_singleton = sorted(
        singletons,
        key=lambda item: (-float(item["quality_score"]), str(item["variant_id"])),
    )[0]
    naive_context = _context_tokens(
        naive_union["raw"], variant_id=naive_union["variant_id"]
    )
    full_context = _context_tokens(full["raw"], variant_id=full["variant_id"])
    if naive_context == 0:
        raise ValueError("naive_union.context_tokens must be greater than zero.")

    quality_metrics = {
        "baseline_quality": baseline["quality_score"],
        "naive_union_quality": naive_union["quality_score"],
        "best_singleton_quality": best_singleton["quality_score"],
        "full_composition_quality": full["quality_score"],
        "wrong_order_quality": wrong_order["quality_score"],
        "synergy_lift": round(
            float(full["quality_score"]) - float(best_singleton["quality_score"]),
            6,
        ),
        "compiler_lift": round(
            float(full["quality_score"]) - float(naive_union["quality_score"]),
            6,
        ),
        "order_lift": round(
            float(full["quality_score"]) - float(wrong_order["quality_score"]),
            6,
        ),
        "leave_one_out_lifts": {
            str(item["skill_id"]): round(
                float(full["quality_score"]) - float(item["quality_score"]), 6
            )
            for item in sorted(leave_one_out, key=lambda value: value["skill_id"])
        },
    }
    failed_variants = [
        {
            "variant_id": item["variant_id"],
            "failures": item["safety_failures"],
        }
        for item in normalized
        if item["safety_failures"]
    ]
    ineligibility_reasons = ["safety_failure_present"] if failed_variants else []
    return {
        "schema": COMPOSITION_EVALUATION_SCHEMA,
        "variant_count": len(normalized),
        "quality_metrics": quality_metrics,
        "cost_metrics": {
            "naive_union_context_tokens": naive_context,
            "full_composition_context_tokens": full_context,
            "context_ratio": round(full_context / naive_context, 6),
        },
        "best_singleton": {
            "variant_id": best_singleton["variant_id"],
            "skill_id": best_singleton["skill_id"],
            "quality_score": best_singleton["quality_score"],
        },
        "safety": {
            "passed": not failed_variants,
            "failed_variants": failed_variants,
        },
        "eligible": not ineligibility_reasons,
        "ineligibility_reasons": ineligibility_reasons,
    }
