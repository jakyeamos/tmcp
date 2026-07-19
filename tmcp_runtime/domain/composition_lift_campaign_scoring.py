"""Pure repeated-cell lift metrics for a validated composition campaign."""

from __future__ import annotations

from collections.abc import Mapping
from statistics import median
from typing import Any

from .composition_lift_campaign_results import (
    SUMMARY_SCHEMA,
    _campaign_cells,
    _mapping,
    _mappings,
    _variant_medians,
    validate_campaign_evaluator_artifacts,
    validate_campaign_host_results,
)


def score_composition_lift_campaign(
    campaign: Mapping[str, Any],
    host_results: Mapping[str, Any],
    evaluator_artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    """Return repeated-cell lift metrics without writing receipts or artifacts."""

    expected = _campaign_cells(campaign)
    host_cells = validate_campaign_host_results(campaign, host_results)
    evaluator_cells = validate_campaign_evaluator_artifacts(
        campaign, evaluator_artifacts, host_cells
    )
    fixture_summaries: list[dict[str, Any]] = []
    for block in _mappings(campaign.get("blocks"), field="campaign.blocks"):
        fixture_id = str(block["fixture_id"])
        causal = [
            context["cell"]
            for context in expected.values()
            if context["fixture_id"] == fixture_id and context["cohort"] == "causal"
        ]
        by_coordinate = {
            (
                int(cell["configuration_slot"]),
                int(cell["replicate_index"]),
                str(
                    _mapping(cell["binding"], field="campaign.cell.binding")[
                        "variant_id"
                    ]
                ),
            ): str(cell["cell_id"])
            for cell in causal
        }
        variants = set(_variant_medians(causal, evaluator_cells))
        lifts = {"synergy_lift": [], "compiler_lift": [], "order_lift": []}
        leave_one_out: dict[str, list[float]] = {}
        for slot in (1, 2, 3):
            for replicate in (1, 2):
                full_id = by_coordinate[(slot, replicate, "full_composition")]
                full_score = float(evaluator_cells[full_id]["quality_score"])
                singleton_scores = [
                    float(
                        evaluator_cells[by_coordinate[(slot, replicate, variant)]][
                            "quality_score"
                        ]
                    )
                    for variant in sorted(variants)
                    if variant.startswith("singleton:")
                ]
                if len(singleton_scores) != 4:
                    raise ValueError(f"{fixture_id} is missing a singleton comparator.")
                lifts["synergy_lift"].append(full_score - max(singleton_scores))
                lifts["compiler_lift"].append(
                    full_score
                    - float(
                        evaluator_cells[
                            by_coordinate[(slot, replicate, "naive_union")]
                        ]["quality_score"]
                    )
                )
                lifts["order_lift"].append(
                    full_score
                    - float(
                        evaluator_cells[
                            by_coordinate[(slot, replicate, "wrong_order")]
                        ]["quality_score"]
                    )
                )
                for variant in sorted(variants):
                    if variant.startswith("leave_one_out:"):
                        skill_id = variant.partition(":")[2]
                        leave_one_out.setdefault(skill_id, []).append(
                            full_score
                            - float(
                                evaluator_cells[
                                    by_coordinate[(slot, replicate, variant)]
                                ]["quality_score"]
                            )
                        )
        fixture_summaries.append(
            {
                "fixture_id": fixture_id,
                "causal_cell_count": len(causal),
                "variant_median_quality": _variant_medians(causal, evaluator_cells),
                "paired_replicate_count": len(lifts["synergy_lift"]),
                "lift_metrics": {
                    key: round(median(values), 4) for key, values in lifts.items()
                },
                "leave_one_out_lifts": {
                    skill: round(median(values), 4)
                    for skill, values in sorted(leave_one_out.items())
                },
            }
        )
    overall = {
        key: round(median(item["lift_metrics"][key] for item in fixture_summaries), 4)
        for key in ("synergy_lift", "compiler_lift", "order_lift")
    }
    host_real = host_results.get("evidence_class") == "host_executed"
    evaluator_real = (
        _mapping(
            evaluator_artifacts.get("evaluator_execution"),
            field="evaluator_artifacts.evaluator_execution",
        ).get("execution_class")
        == "trusted_evaluator_execution"
    )
    thresholds = {"synergy_lift": 0.10, "compiler_lift": 0.05, "order_lift": 0.05}
    checks = {
        "host_executed": host_real,
        "trusted_evaluator_execution": evaluator_real,
        **{key: overall[key] >= threshold for key, threshold in thresholds.items()},
    }
    return {
        "schema": SUMMARY_SCHEMA,
        "campaign_id": campaign["campaign_id"],
        "campaign_digest": campaign["campaign_digest"],
        "eligible": all(checks.values()),
        "failed_checks": [key for key, passed in checks.items() if not passed],
        "acceptance_checks": checks,
        "thresholds": thresholds,
        "evidence_class": host_results["evidence_class"],
        "evaluator_execution_class": _mapping(
            evaluator_artifacts["evaluator_execution"],
            field="evaluator_artifacts.evaluator_execution",
        )["execution_class"],
        "quality_metrics": overall,
        "fixture_count": len(fixture_summaries),
        "cell_counts": {"baseline": 180, "causal": 360, "total": 540},
        "fixtures": fixture_summaries,
        "proof_scope": "repeated cell-level quality lift only; routing, context, safety, and release gates remain separate",
        "evidence_trust": "advisory_untrusted",
    }
