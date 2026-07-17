"""Pure evaluation and project-recipe promotion policy for skill compositions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any


COMPOSITION_EVALUATION_SCHEMA = "tmcp-composition-evaluation-summary-v0.1"
PROJECT_RECIPE_PROMOTION_SCHEMA = "tmcp-project-recipe-promotion-eligibility-v0.1"

DEFAULT_MINIMUM_RECEIPTS = 3
DEFAULT_MINIMUM_FIXTURES = 2
DEFAULT_MINIMUM_SYNERGY_LIFT = 0.10
DEFAULT_MINIMUM_COMPILER_LIFT = 0.05
DEFAULT_MINIMUM_ORDER_LIFT = 0.05
DEFAULT_MAXIMUM_CONTEXT_RATIO = 0.75

_PASS_STATUSES = {"ok", "pass", "passed", "success", "succeeded", "verified"}
_FAIL_STATUSES = {"block", "blocked", "error", "fail", "failed", "failure"}
_SINGLE_VARIANT_KINDS = {
    "baseline": "no_skill",
    "no_skill": "no_skill",
    "naive_union": "naive_union",
    "full_composition": "full_composition",
    "wrong_order": "wrong_order",
}


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


def _finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric.")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite.")
    return result


def _optional_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _quality_score(result: Mapping[str, Any], *, variant_id: str) -> float:
    value = result.get("quality_score")
    if value is None:
        quality_metrics = _optional_mapping(result.get("quality_metrics"))
        for key in ("normalized_quality_score", "quality_score", "score"):
            if quality_metrics.get(key) is not None:
                value = quality_metrics[key]
                break
    score = _finite_number(value, field=f"{variant_id}.quality_score")
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"{variant_id}.quality_score must be between 0 and 1.")
    return score


def _context_tokens(result: Mapping[str, Any], *, variant_id: str) -> float:
    value = result.get("context_tokens")
    if value is None:
        value = _optional_mapping(result.get("cost_metrics")).get("context_tokens")
    tokens = _finite_number(value, field=f"{variant_id}.context_tokens")
    if tokens < 0:
        raise ValueError(f"{variant_id}.context_tokens cannot be negative.")
    return tokens


def _variant_kind(result: Mapping[str, Any], variant_id: str) -> str:
    explicit = str(result.get("variant_kind") or "").strip()
    if explicit == "baseline":
        return "no_skill"
    if explicit:
        return explicit
    if variant_id.startswith("singleton:"):
        return "singleton"
    if variant_id.startswith("leave_one_out:"):
        return "leave_one_out"
    return _SINGLE_VARIANT_KINDS.get(variant_id, "")


def _variant_skill_id(result: Mapping[str, Any], variant_id: str) -> str:
    explicit = str(result.get("skill_id") or "").strip()
    if explicit:
        return explicit
    return variant_id.split(":", 1)[1].strip() if ":" in variant_id else ""


def _mapping_list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _gate_id(gate: Mapping[str, Any], index: int) -> str:
    for key in ("gate_id", "id", "name"):
        value = str(gate.get(key) or "").strip()
        if value:
            return value
    return f"gate-{index}"


def _status(value: object) -> str:
    return str(value or "").strip().lower()


def _gate_failed(gate: Mapping[str, Any]) -> bool:
    if gate.get("passed") is False:
        return True
    return any(
        _status(gate.get(key)) in _FAIL_STATUSES
        for key in ("status", "outcome", "result")
    )


def _gate_passed(gate: Mapping[str, Any]) -> bool:
    if gate.get("passed") is True:
        return True
    return any(
        _status(gate.get(key)) in _PASS_STATUSES
        for key in ("status", "outcome", "result")
    )


def _is_safety_gate(gate: Mapping[str, Any]) -> bool:
    if gate.get("safety") is True:
        return True
    labels = " ".join(
        str(gate.get(key) or "")
        for key in ("gate_id", "id", "name", "kind", "category", "type")
    ).lower()
    return "safety" in labels or "security" in labels or "privacy" in labels


def _safety_failures(result: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if result.get("safety_passed") is False:
        failures.append("safety_passed=false")
    safety = _optional_mapping(result.get("safety"))
    if safety.get("passed") is False:
        failures.append("safety.passed=false")
    raw_failures = safety.get("failures")
    if isinstance(raw_failures, list):
        failures.extend(str(item) for item in raw_failures if str(item).strip())
    for index, gate in enumerate(_mapping_list(result.get("gate_results")), start=1):
        if _is_safety_gate(gate) and _gate_failed(gate):
            failures.append(_gate_id(gate, index))
    return list(dict.fromkeys(failures))


def _safety_gate_evidence_status(result: Mapping[str, Any]) -> str:
    safety_gates = [
        gate
        for gate in _mapping_list(result.get("gate_results"))
        if _is_safety_gate(gate)
    ]
    if not safety_gates:
        return "missing"
    if any(_gate_failed(gate) for gate in safety_gates):
        return "failed"
    if all(_gate_passed(gate) for gate in safety_gates):
        return "passed"
    return "missing"


def _single_result(
    grouped: Mapping[str, list[dict[str, Any]]], variant_kind: str
) -> dict[str, Any]:
    matches = grouped.get(variant_kind, [])
    if len(matches) != 1:
        raise ValueError(
            f"Composition results require exactly one {variant_kind} variant."
        )
    return matches[0]


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
    leave_one_out_ids = {item["skill_id"] for item in leave_one_out if item["skill_id"]}
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _verification_passed(receipt: Mapping[str, Any]) -> bool:
    if _status(receipt.get("outcome")) not in _PASS_STATUSES:
        return False
    verification_results = [
        item.lower() for item in _string_list(receipt.get("verification_results"))
    ]
    if any(
        any(failure in item for failure in _FAIL_STATUSES)
        for item in verification_results
    ):
        return False
    gate_results = _mapping_list(receipt.get("gate_results"))
    if gate_results:
        return all(
            _gate_passed(gate) and not _gate_failed(gate) for gate in gate_results
        )
    return any(
        any(passed in item for passed in _PASS_STATUSES)
        for item in verification_results
    )


def _has_override(receipt: Mapping[str, Any]) -> bool:
    return bool(
        _string_list(receipt.get("user_overrides"))
        or _string_list(receipt.get("overrides"))
    )


def _receipt_metrics(receipt: Mapping[str, Any]) -> dict[str, float] | None:
    quality = _optional_mapping(receipt.get("quality_metrics"))
    cost = _optional_mapping(receipt.get("cost_metrics"))
    try:
        return {
            "synergy_lift": _finite_number(
                quality.get("synergy_lift"), field="quality_metrics.synergy_lift"
            ),
            "compiler_lift": _finite_number(
                quality.get("compiler_lift"), field="quality_metrics.compiler_lift"
            ),
            "order_lift": _finite_number(
                quality.get("order_lift"), field="quality_metrics.order_lift"
            ),
            "context_ratio": _finite_number(
                cost.get("context_ratio"), field="cost_metrics.context_ratio"
            ),
        }
    except ValueError:
        return None


def _threshold(value: object, *, name: str, minimum: float | None = None) -> float:
    result = _finite_number(value, field=name)
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return result


def assess_project_recipe_promotion(
    receipts: Sequence[Mapping[str, Any]],
    *,
    recipe_id: str,
    graph_digest: str,
    minimum_receipts: int = DEFAULT_MINIMUM_RECEIPTS,
    minimum_fixtures: int = DEFAULT_MINIMUM_FIXTURES,
    minimum_synergy_lift: float = DEFAULT_MINIMUM_SYNERGY_LIFT,
    minimum_compiler_lift: float = DEFAULT_MINIMUM_COMPILER_LIFT,
    minimum_order_lift: float = DEFAULT_MINIMUM_ORDER_LIFT,
    maximum_context_ratio: float = DEFAULT_MAXIMUM_CONTEXT_RATIO,
) -> dict[str, Any]:
    """Assess explicit project-local recipe promotion from supplied receipts."""

    clean_recipe_id = recipe_id.strip()
    clean_graph_digest = graph_digest.strip()
    if not clean_recipe_id or not clean_graph_digest:
        raise ValueError("Recipe promotion requires recipe_id and graph_digest.")
    if isinstance(receipts, (str, bytes)):
        raise ValueError("Recipe promotion receipts must be a sequence of objects.")
    if minimum_receipts < 1 or minimum_fixtures < 1:
        raise ValueError(
            "Recipe promotion receipt and fixture minimums must be positive."
        )
    thresholds = {
        "minimum_receipts": minimum_receipts,
        "minimum_fixtures": minimum_fixtures,
        "minimum_synergy_lift": _threshold(
            minimum_synergy_lift, name="minimum_synergy_lift"
        ),
        "minimum_compiler_lift": _threshold(
            minimum_compiler_lift, name="minimum_compiler_lift"
        ),
        "minimum_order_lift": _threshold(minimum_order_lift, name="minimum_order_lift"),
        "maximum_context_ratio": _threshold(
            maximum_context_ratio,
            name="maximum_context_ratio",
            minimum=0.0,
        ),
    }

    qualifying: list[tuple[Mapping[str, Any], dict[str, float]]] = []
    fixture_ids: set[str] = set()
    safety_failures: list[str] = []
    missing_safety_gate_receipts: list[str] = []
    override_receipts: list[str] = []
    rejected_counts = {
        "different_recipe": 0,
        "different_graph_digest": 0,
        "unverified": 0,
        "missing_safety_gate_evidence": 0,
        "failing_safety_gate_evidence": 0,
        "missing_fixture_id": 0,
        "missing_metrics": 0,
    }
    matching_digest_count = 0
    for index, receipt in enumerate(receipts, start=1):
        if not isinstance(receipt, Mapping):
            raise ValueError("Each recipe promotion receipt must be an object.")
        if str(receipt.get("recipe_id") or "").strip() != clean_recipe_id:
            rejected_counts["different_recipe"] += 1
            continue
        if str(receipt.get("graph_digest") or "").strip() != clean_graph_digest:
            rejected_counts["different_graph_digest"] += 1
            continue
        matching_digest_count += 1
        receipt_label = str(receipt.get("packet_id") or f"receipt-{index}")
        failures = _safety_failures(receipt)
        safety_gate_status = _safety_gate_evidence_status(receipt)
        if failures:
            safety_failures.append(receipt_label)
        if safety_gate_status == "missing":
            missing_safety_gate_receipts.append(receipt_label)
        if _has_override(receipt):
            override_receipts.append(receipt_label)
        if failures or safety_gate_status == "failed":
            rejected_counts["failing_safety_gate_evidence"] += 1
            continue
        if safety_gate_status == "missing":
            rejected_counts["missing_safety_gate_evidence"] += 1
            continue
        if not _verification_passed(receipt):
            rejected_counts["unverified"] += 1
            continue
        fixture_id = str(receipt.get("composition_fixture_id") or "").strip()
        if not fixture_id:
            rejected_counts["missing_fixture_id"] += 1
            continue
        metrics = _receipt_metrics(receipt)
        if metrics is None:
            rejected_counts["missing_metrics"] += 1
            continue
        qualifying.append((receipt, metrics))
        fixture_ids.add(fixture_id)

    aggregate_metrics: dict[str, float] = {}
    if qualifying:
        for metric in (
            "synergy_lift",
            "compiler_lift",
            "order_lift",
            "context_ratio",
        ):
            aggregate_metrics[metric] = round(
                median(item[1][metric] for item in qualifying), 6
            )

    blocking_reasons: list[str] = []
    if len(qualifying) < minimum_receipts:
        blocking_reasons.append("minimum_verified_receipts_not_met")
    if len(fixture_ids) < minimum_fixtures:
        blocking_reasons.append("minimum_fixture_count_not_met")
    if safety_failures:
        blocking_reasons.append("safety_failure_present")
    if missing_safety_gate_receipts:
        blocking_reasons.append("missing_safety_gate_evidence")
    if override_receipts:
        blocking_reasons.append("override_present")
    metric_thresholds = (
        ("synergy_lift", "minimum_synergy_lift", False),
        ("compiler_lift", "minimum_compiler_lift", False),
        ("order_lift", "minimum_order_lift", False),
        ("context_ratio", "maximum_context_ratio", True),
    )
    for metric, threshold_name, maximum in metric_thresholds:
        if metric not in aggregate_metrics:
            blocking_reasons.append(f"{metric}_unavailable")
            continue
        metric_failed = (
            aggregate_metrics[metric] > float(thresholds[threshold_name])
            if maximum
            else aggregate_metrics[metric] < float(thresholds[threshold_name])
        )
        if metric_failed:
            suffix = "above_threshold" if maximum else "below_threshold"
            blocking_reasons.append(f"{metric}_{suffix}")

    return {
        "schema": PROJECT_RECIPE_PROMOTION_SCHEMA,
        "recipe_id": clean_recipe_id,
        "graph_digest": clean_graph_digest,
        "cache_policy": "project",
        "explicit_promotion_required": True,
        "auto_promote": False,
        "eligible": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "thresholds": thresholds,
        "evidence": {
            "supplied_receipt_count": len(receipts),
            "matching_digest_receipt_count": matching_digest_count,
            "verified_receipt_count": len(qualifying),
            "fixture_count": len(fixture_ids),
            "fixture_ids": sorted(fixture_ids),
            "receipt_packet_ids": [
                str(receipt.get("packet_id") or "")
                for receipt, _metrics in qualifying
                if str(receipt.get("packet_id") or "")
            ],
            "safety_failure_receipts": safety_failures,
            "missing_safety_gate_receipts": missing_safety_gate_receipts,
            "override_receipts": override_receipts,
            "rejected_receipt_counts": rejected_counts,
        },
        "aggregate_metrics": aggregate_metrics,
    }
