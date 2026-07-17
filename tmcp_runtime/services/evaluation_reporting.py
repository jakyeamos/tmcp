"""Small report-assembly helpers for skill evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def aggregate_dimension(scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {"score": 0.0, "confidence": "low"}
    average = sum(float(item.get("score") or 0.0) for item in scores) / len(scores)
    confidences = {str(item.get("confidence") or "low") for item in scores}
    confidence = (
        "high"
        if confidences == {"high"}
        else "medium"
        if "medium" in confidences
        else "low"
    )
    return {"score": round(average, 2), "confidence": confidence}


def harvest_feedback(
    anti_patterns: Sequence[Mapping[str, Any]],
    *,
    anti_pattern_catalog: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    catalog = {
        str(pattern.get("pattern_id")): pattern for pattern in anti_pattern_catalog
    }
    for finding in anti_patterns:
        pattern = catalog.get(str(finding.get("pattern_id") or ""))
        if pattern is None:
            continue
        feedback.append(
            {
                "pattern_id": pattern["pattern_id"],
                "classification": pattern["classification"],
                "suggested_harvest_warning": pattern["suggested_harvest_warning"],
                "suggested_detection_terms": list(pattern["detection_terms"]),
                "safe_to_auto_warn": pattern["safe_to_auto_warn"],
                "safe_to_auto_rewrite": pattern["safe_to_auto_rewrite"],
            }
        )
    return feedback
