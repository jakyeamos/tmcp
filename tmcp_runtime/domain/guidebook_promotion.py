"""Pure independent-rejudge and guidebook-promotion policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .composition_lift_campaign_results import (
    validate_campaign_evaluator_artifacts,
)
from .composition_lift_campaign_scoring import score_composition_lift_campaign
from .composition_preflight import stable_digest


REJUDGE_ENVELOPE_SCHEMA = "tmcp-composition-lift-rejudge-envelope-v0.1"
PROMOTION_CANDIDATE_SCHEMA = "tmcp-guidebook-promotion-candidate-v0.1"
AGREEMENT_TOLERANCE = 0.1


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object.")
    return value


def _text(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required.")
    return result


def validate_independent_rejudge(
    campaign: Mapping[str, Any],
    host_cells: Mapping[str, Mapping[str, Any]],
    primary_evaluator: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a second blind judgment without accepting it as promotion."""

    if envelope.get("schema") != REJUDGE_ENVELOPE_SCHEMA:
        raise ValueError("rejudge envelope schema is invalid.")
    if envelope.get("campaign_id") != campaign.get("campaign_id"):
        raise ValueError("rejudge envelope campaign_id is not campaign-bound.")
    if envelope.get("campaign_digest") != campaign.get("campaign_digest"):
        raise ValueError("rejudge envelope campaign_digest is not campaign-bound.")
    if envelope.get("primary_evaluator_digest") != stable_digest(
        dict(primary_evaluator)
    ):
        raise ValueError("rejudge envelope primary evaluator digest is invalid.")

    independence = _mapping(envelope.get("independence"), field="rejudge.independence")
    if independence.get("mode") != "independent_rejudge":
        raise ValueError("rejudge.independence.mode must be independent_rejudge.")
    for key in ("executor_id", "execution_id", "primary_execution_id", "method"):
        _text(independence.get(key), field=f"rejudge.independence.{key}")
    primary_execution = _mapping(
        primary_evaluator.get("evaluator_execution"),
        field="primary_evaluator.evaluator_execution",
    )
    if independence["primary_execution_id"] != primary_execution.get("execution_id"):
        raise ValueError("rejudge independence does not name the primary execution.")
    if independence["execution_id"] == primary_execution.get("execution_id"):
        raise ValueError("rejudge execution_id must differ from the primary execution.")
    if independence["executor_id"] == primary_execution.get("executor_id"):
        raise ValueError("rejudge executor_id must differ from the primary evaluator.")

    artifacts = _mapping(envelope.get("artifacts"), field="rejudge.artifacts")
    execution = _mapping(
        artifacts.get("evaluator_execution"),
        field="rejudge.artifacts.evaluator_execution",
    )
    if execution.get("execution_class") != "trusted_evaluator_execution":
        raise ValueError("rejudge artifacts require trusted evaluator execution.")
    if execution.get("execution_id") != independence.get("execution_id"):
        raise ValueError("rejudge artifact execution_id is not envelope-bound.")
    rejudge_cells = validate_campaign_evaluator_artifacts(
        campaign, artifacts, host_cells
    )
    primary_cells = validate_campaign_evaluator_artifacts(
        campaign, primary_evaluator, host_cells
    )
    if stable_digest(dict(artifacts)) == stable_digest(dict(primary_evaluator)):
        raise ValueError(
            "rejudge artifacts must differ from the primary evaluator artifacts."
        )

    max_delta = 0.0
    dimension_count = 0
    for cell_id, primary_cell in primary_cells.items():
        rejudge_cell = rejudge_cells.get(cell_id)
        if rejudge_cell is None:
            raise ValueError("rejudge artifacts must cover every primary cell.")
        primary_scores = _mapping(
            primary_cell.get("dimension_scores"),
            field=f"primary.{cell_id}.dimension_scores",
        )
        rejudge_scores = _mapping(
            rejudge_cell.get("dimension_scores"),
            field=f"rejudge.{cell_id}.dimension_scores",
        )
        if set(primary_scores) != set(rejudge_scores):
            raise ValueError(
                f"rejudge.{cell_id} dimensions do not match primary judgment."
            )
        dimension_count += len(primary_scores)
        for dimension in primary_scores:
            delta = abs(
                float(primary_scores[dimension]) - float(rejudge_scores[dimension])
            )
            max_delta = max(max_delta, delta)
    if max_delta > AGREEMENT_TOLERANCE:
        raise ValueError(
            f"independent rejudge disagreement {max_delta:.4f} exceeds {AGREEMENT_TOLERANCE:.4f}."
        )
    return {
        "rejudge_cells": rejudge_cells,
        "agreement": {
            "cell_count": len(rejudge_cells),
            "dimension_count": dimension_count,
            "max_absolute_score_delta": round(max_delta, 4),
        },
    }


def build_guidebook_promotion_candidate(
    *,
    campaign: Mapping[str, Any],
    summary: Mapping[str, Any],
    rejudge_summary: Mapping[str, Any],
    primary_evaluator: Mapping[str, Any],
    rejudge_envelope: Mapping[str, Any],
    pattern_ids: Sequence[str],
    catalog: Mapping[str, Any],
    agreement: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a manual-review candidate; never mutate the guidebook or catalog."""

    if summary.get("eligible") is not True:
        raise ValueError("primary composition summary is not eligible.")
    if rejudge_summary.get("eligible") is not True:
        raise ValueError("independent rejudge composition summary is not eligible.")
    if summary.get("evidence_class") != "host_executed":
        raise ValueError("primary composition evidence is not host-executed.")
    if summary.get("evaluator_execution_class") != "trusted_evaluator_execution":
        raise ValueError("primary evaluator execution is not trusted.")
    if (
        rejudge_summary.get("evaluator_execution_class")
        != "trusted_evaluator_execution"
    ):
        raise ValueError("independent rejudge execution is not trusted.")
    if int(agreement.get("cell_count") or 0) != 540:
        raise ValueError("independent rejudge must cover all 540 cells.")

    primary_metrics = _mapping(
        summary.get("quality_metrics"), field="summary.quality_metrics"
    )
    rejudge_metrics = _mapping(
        rejudge_summary.get("quality_metrics"), field="rejudge_summary.quality_metrics"
    )
    metric_deltas = {
        key: round(abs(float(primary_metrics[key]) - float(rejudge_metrics[key])), 4)
        for key in primary_metrics
    }
    if any(delta > AGREEMENT_TOLERANCE for delta in metric_deltas.values()):
        raise ValueError("independent rejudge lift metrics disagree beyond tolerance.")

    entries = {
        str(entry.get("pattern_id")): entry
        for entry in catalog.get("guidebook_entries", [])
        if isinstance(entry, Mapping) and entry.get("pattern_id")
    }
    selected = [str(pattern_id).strip() for pattern_id in pattern_ids]
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("pattern_ids must be nonempty and unique.")
    for pattern_id in selected:
        entry = entries.get(pattern_id)
        if entry is None:
            raise ValueError(
                f"pattern_id is not present in the guidebook catalog: {pattern_id}"
            )
        promotion = _mapping(
            entry.get("promotion"), field=f"catalog.{pattern_id}.promotion"
        )
        if (
            promotion.get("eligible") is not False
            or promotion.get("decision") != "hold"
        ):
            raise ValueError(f"pattern_id is not a held guidebook entry: {pattern_id}")

    independence = _mapping(
        rejudge_envelope.get("independence"), field="rejudge.independence"
    )
    return {
        "schema": PROMOTION_CANDIDATE_SCHEMA,
        "campaign_id": campaign["campaign_id"],
        "campaign_digest": campaign["campaign_digest"],
        "pattern_ids": selected,
        "decision": "eligible_for_manual_review",
        "eligible": True,
        "promotion_policy": {
            "auto_apply": False,
            "requires_human_review": True,
            "requires_replication": True,
            "requires_independent_rejudge": True,
        },
        "evidence": {
            "summary_digest": stable_digest(dict(summary)),
            "primary_evaluator_digest": stable_digest(dict(primary_evaluator)),
            "rejudge_digest": stable_digest(dict(rejudge_envelope)),
            "rejudge_execution_id": str(independence["execution_id"]),
            "agreement": {
                **dict(agreement),
                "quality_metric_deltas": metric_deltas,
            },
        },
    }


def score_rejudge(
    campaign: Mapping[str, Any],
    host_results: Mapping[str, Any],
    rejudge_artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    """Score a validated rejudge through the same preregistered scorer."""

    return score_composition_lift_campaign(campaign, host_results, rejudge_artifacts)
