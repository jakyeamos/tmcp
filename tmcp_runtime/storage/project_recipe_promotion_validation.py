"""Promotion-evidence validation for persisted project composition recipes."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from tmcp_runtime.services.composition_evaluation import (
    DEFAULT_MAXIMUM_CONTEXT_RATIO,
    DEFAULT_MINIMUM_COMPILER_LIFT,
    DEFAULT_MINIMUM_FIXTURES,
    DEFAULT_MINIMUM_ORDER_LIFT,
    DEFAULT_MINIMUM_RECEIPTS,
    DEFAULT_MINIMUM_SYNERGY_LIFT,
    PROJECT_RECIPE_PROMOTION_SCHEMA,
)


PHASE_CAPSULE_BOUND = "verified"
PHASE_CAPSULE_LEGACY_UNBOUND = "legacy_unbound"
_PHASE_CAPSULE_EVIDENCE_FIELDS = frozenset(
    {
        "isolated_phase_capsule_receipt_count",
        "structurally_valid_phase_capsule_evidence_receipt_count",
        "bound_phase_capsule_evidence_receipt_count",
        "structurally_valid_benchmark_receipt_provenance_receipt_count",
        "bound_benchmark_receipt_provenance_receipt_count",
        "unqualified_context_execution_receipts",
        "invalid_phase_capsule_evidence_receipts",
        "unmatched_phase_capsule_provenance_receipts",
        "missing_benchmark_receipt_provenance_receipts",
        "invalid_benchmark_receipt_provenance_receipts",
        "unmatched_benchmark_receipt_provenance_receipts",
    }
)
_PHASE_CAPSULE_REJECTED_COUNT_FIELDS = frozenset(
    {
        "unqualified_context_execution",
        "invalid_phase_capsule_evidence",
        "unmatched_phase_capsule_provenance",
        "missing_benchmark_receipt_provenance",
        "invalid_benchmark_receipt_provenance",
        "unmatched_benchmark_receipt_provenance",
    }
)


def _integer(value: object, *, minimum: int) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= minimum


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def promotion_is_valid(
    value: object,
    *,
    recipe_id: str,
    graph_digest: str,
    phase_capsule_binding: Mapping[str, Any],
) -> bool:
    """Check reviewed promotion evidence without relaxing phase provenance."""

    if not isinstance(value, Mapping):
        return False
    if (
        value.get("schema") != PROJECT_RECIPE_PROMOTION_SCHEMA
        or value.get("recipe_id") != recipe_id
        or value.get("graph_digest") != graph_digest
        or value.get("phase_capsule_binding_digest")
        != phase_capsule_binding["binding_digest"]
        or value.get("cache_policy") != "project"
        or value.get("explicit_promotion_required") is not True
        or value.get("auto_promote") is not False
        or value.get("eligible") is not True
        or value.get("blocking_reasons") != []
    ):
        return False
    thresholds = value.get("thresholds")
    evidence = value.get("evidence")
    metrics = value.get("aggregate_metrics")
    if (
        not isinstance(thresholds, Mapping)
        or not isinstance(evidence, Mapping)
        or not isinstance(metrics, Mapping)
    ):
        return False

    minimum_receipts = thresholds.get("minimum_receipts")
    minimum_fixtures = thresholds.get("minimum_fixtures")
    minimum_receipts_value = (
        minimum_receipts
        if isinstance(minimum_receipts, int) and not isinstance(minimum_receipts, bool)
        else None
    )
    minimum_fixtures_value = (
        minimum_fixtures
        if isinstance(minimum_fixtures, int) and not isinstance(minimum_fixtures, bool)
        else None
    )
    threshold_values = {
        "minimum_synergy_lift": _number(thresholds.get("minimum_synergy_lift")),
        "minimum_compiler_lift": _number(thresholds.get("minimum_compiler_lift")),
        "minimum_order_lift": _number(thresholds.get("minimum_order_lift")),
        "maximum_context_ratio": _number(thresholds.get("maximum_context_ratio")),
    }
    if (
        minimum_receipts_value is None
        or minimum_receipts_value < DEFAULT_MINIMUM_RECEIPTS
        or minimum_fixtures_value is None
        or minimum_fixtures_value < DEFAULT_MINIMUM_FIXTURES
        or threshold_values["minimum_synergy_lift"] is None
        or threshold_values["minimum_synergy_lift"] < DEFAULT_MINIMUM_SYNERGY_LIFT
        or threshold_values["minimum_compiler_lift"] is None
        or threshold_values["minimum_compiler_lift"] < DEFAULT_MINIMUM_COMPILER_LIFT
        or threshold_values["minimum_order_lift"] is None
        or threshold_values["minimum_order_lift"] < DEFAULT_MINIMUM_ORDER_LIFT
        or threshold_values["maximum_context_ratio"] is None
        or threshold_values["maximum_context_ratio"] < 0
        or threshold_values["maximum_context_ratio"] > DEFAULT_MAXIMUM_CONTEXT_RATIO
    ):
        return False

    verified_receipts = evidence.get("verified_receipt_count")
    isolated_phase_capsule_receipts = evidence.get(
        "isolated_phase_capsule_receipt_count"
    )
    structurally_valid_phase_capsule_evidence_receipts = evidence.get(
        "structurally_valid_phase_capsule_evidence_receipt_count"
    )
    bound_phase_capsule_evidence_receipts = evidence.get(
        "bound_phase_capsule_evidence_receipt_count"
    )
    structurally_valid_benchmark_receipt_provenance_receipts = evidence.get(
        "structurally_valid_benchmark_receipt_provenance_receipt_count"
    )
    bound_benchmark_receipt_provenance_receipts = evidence.get(
        "bound_benchmark_receipt_provenance_receipt_count"
    )
    fixture_count = evidence.get("fixture_count")
    rejected_counts = evidence.get("rejected_receipt_counts")
    required_rejected_counts = (
        "different_recipe",
        "different_graph_digest",
        "unverified",
        "missing_safety_gate_evidence",
        "failing_safety_gate_evidence",
        "missing_fixture_id",
        "missing_metrics",
        "unqualified_context_execution",
        "invalid_phase_capsule_evidence",
        "unmatched_phase_capsule_provenance",
        "missing_benchmark_receipt_provenance",
        "invalid_benchmark_receipt_provenance",
        "unmatched_benchmark_receipt_provenance",
    )
    if not _integer(verified_receipts, minimum=minimum_receipts_value):
        return False
    verified_receipts_value = int(verified_receipts)
    if (
        not _integer(
            isolated_phase_capsule_receipts, minimum=minimum_receipts_value
        )
        or isolated_phase_capsule_receipts != verified_receipts_value
        or not _integer(
            structurally_valid_phase_capsule_evidence_receipts,
            minimum=verified_receipts_value,
        )
        or not _integer(
            bound_phase_capsule_evidence_receipts,
            minimum=verified_receipts_value,
        )
        or bound_phase_capsule_evidence_receipts != verified_receipts_value
        or not _integer(
            structurally_valid_benchmark_receipt_provenance_receipts,
            minimum=verified_receipts_value,
        )
        or not _integer(
            bound_benchmark_receipt_provenance_receipts,
            minimum=verified_receipts_value,
        )
        or bound_benchmark_receipt_provenance_receipts != verified_receipts_value
        or not _integer(fixture_count, minimum=minimum_fixtures_value)
        or evidence.get("safety_failure_receipts") != []
        or evidence.get("missing_safety_gate_receipts") != []
        or evidence.get("override_receipts") != []
        or evidence.get("unqualified_context_execution_receipts") != []
        or evidence.get("invalid_phase_capsule_evidence_receipts") != []
        or evidence.get("unmatched_phase_capsule_provenance_receipts") != []
        or evidence.get("missing_benchmark_receipt_provenance_receipts") != []
        or evidence.get("invalid_benchmark_receipt_provenance_receipts") != []
        or evidence.get("unmatched_benchmark_receipt_provenance_receipts") != []
        or not isinstance(rejected_counts, Mapping)
        or any(
            not _integer(rejected_counts.get(key), minimum=0)
            for key in required_rejected_counts
        )
        or rejected_counts.get("invalid_phase_capsule_evidence") != 0
        or rejected_counts.get("unmatched_phase_capsule_provenance") != 0
        or rejected_counts.get("missing_benchmark_receipt_provenance") != 0
        or rejected_counts.get("invalid_benchmark_receipt_provenance") != 0
        or rejected_counts.get("unmatched_benchmark_receipt_provenance") != 0
    ):
        return False

    aggregate_values = {
        "synergy_lift": _number(metrics.get("synergy_lift")),
        "compiler_lift": _number(metrics.get("compiler_lift")),
        "order_lift": _number(metrics.get("order_lift")),
        "context_ratio": _number(metrics.get("context_ratio")),
    }
    return (
        aggregate_values["synergy_lift"] is not None
        and aggregate_values["synergy_lift"] >= threshold_values["minimum_synergy_lift"]
        and aggregate_values["compiler_lift"] is not None
        and aggregate_values["compiler_lift"]
        >= threshold_values["minimum_compiler_lift"]
        and aggregate_values["order_lift"] is not None
        and aggregate_values["order_lift"] >= threshold_values["minimum_order_lift"]
        and aggregate_values["context_ratio"] is not None
        and aggregate_values["context_ratio"]
        <= threshold_values["maximum_context_ratio"]
    )


def phase_capsule_binding_status(
    projection: Mapping[str, Any],
    promotion: object,
) -> str | None:
    """Classify only a complete legacy omission as compatibility-readable."""

    has_binding = "phase_capsule_binding" in projection
    has_promotion_digest = isinstance(promotion, Mapping) and (
        "phase_capsule_binding_digest" in promotion
    )
    evidence = promotion.get("evidence") if isinstance(promotion, Mapping) else None
    has_phase_evidence = isinstance(evidence, Mapping) and any(
        field in evidence for field in _PHASE_CAPSULE_EVIDENCE_FIELDS
    )
    rejected_counts = (
        evidence.get("rejected_receipt_counts") if isinstance(evidence, Mapping) else None
    )
    has_phase_rejected_counts = isinstance(rejected_counts, Mapping) and any(
        field in rejected_counts for field in _PHASE_CAPSULE_REJECTED_COUNT_FIELDS
    )
    if has_binding:
        return PHASE_CAPSULE_BOUND
    if (
        not has_promotion_digest
        and not has_phase_evidence
        and not has_phase_rejected_counts
    ):
        return PHASE_CAPSULE_LEGACY_UNBOUND
    return None


def legacy_promotion_is_readable(
    value: object,
    *,
    recipe_id: str,
    graph_digest: str,
) -> bool:
    """Check the former v0.1 shape without treating it as promotion evidence."""

    if not isinstance(value, Mapping):
        return False
    if (
        value.get("schema") != PROJECT_RECIPE_PROMOTION_SCHEMA
        or value.get("recipe_id") != recipe_id
        or value.get("graph_digest") != graph_digest
        or value.get("cache_policy") != "project"
        or value.get("explicit_promotion_required") is not True
        or value.get("auto_promote") is not False
        or value.get("eligible") is not True
        or value.get("blocking_reasons") != []
        or "phase_capsule_binding_digest" in value
    ):
        return False
    thresholds = value.get("thresholds")
    evidence = value.get("evidence")
    metrics = value.get("aggregate_metrics")
    rejected_counts = (
        evidence.get("rejected_receipt_counts") if isinstance(evidence, Mapping) else None
    )
    return (
        isinstance(thresholds, Mapping)
        and isinstance(evidence, Mapping)
        and isinstance(metrics, Mapping)
        and all(
            field in evidence
            for field in (
                "verified_receipt_count",
                "fixture_count",
                "safety_failure_receipts",
                "missing_safety_gate_receipts",
                "override_receipts",
            )
        )
        and not any(field in evidence for field in _PHASE_CAPSULE_EVIDENCE_FIELDS)
        and (
            not isinstance(rejected_counts, Mapping)
            or not any(
                field in rejected_counts
                for field in _PHASE_CAPSULE_REJECTED_COUNT_FIELDS
            )
        )
    )
