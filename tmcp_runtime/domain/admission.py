"""Pure admission policy for deciding when TMCP composition adds value."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .signal_text import affirmed_terms_in_text


ADMISSION_POLICY_VERSION = "2026-08-02.1"
VALID_ADMISSION_MODES = frozenset({"forced", "automatic", "shadow"})
AUTO_COMPOSE_MIN_CONFIDENCE = 0.60
AUTO_COMPOSE_MIN_COMPLEXITY = 2

TRIVIAL_PATTERNS = (
    r"^translate\b",
    r"^what (?:is|does)\b",
    r"^explain\b",
    r"^fix (?:a |the )?typo\b",
    r"^rename\b",
    r"^change (?:the )?(?:label|text|word|copy)\b",
    r"^format\b",
)

COMPLEXITY_MARKERS = (
    "migration",
    "backfill",
    "architecture",
    "security",
    "release",
    "audit",
    "test strategy",
    "verification",
    "rollout",
    "compatibility",
    "multiple",
    "across",
    "end to end",
    "citation",
    "citations",
    "provenance",
    "dogfood",
)

MULTI_PHASE_ACTION_MARKERS = (
    "research",
    "design",
    "write",
    "draft",
    "implement",
    "review",
    "verify",
    "test",
    "release",
)


def normalize_admission_mode(value: object) -> str:
    """Keep explicit composition backward compatible while exposing safe policies."""

    mode = str(value or "forced").strip().lower()
    return mode if mode in VALID_ADMISSION_MODES else "forced"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _is_trivial(objective: str, context: Mapping[str, Any]) -> bool:
    lower = objective.strip().lower()
    words = re.findall(r"[a-z0-9]+", lower)
    if _string_list(context.get("failures")) or _string_list(
        context.get("files_changed")
    ):
        return False
    return len(words) <= 12 and any(re.search(pattern, lower) for pattern in TRIVIAL_PATTERNS)


def complexity_score(
    objective: str,
    task_identity: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
) -> tuple[int, list[str]]:
    """Estimate whether compilation has enough task surface to repay its overhead."""

    context = context or {}
    lower = objective.lower().replace("-", " ")
    words = re.findall(r"[a-z0-9]+", lower)
    reasons: list[str] = []
    score = 0
    if len(words) >= 18:
        score += 1
        reasons.append("long_objective")
    if affirmed_terms_in_text(lower, COMPLEXITY_MARKERS):
        score += 1
        reasons.append("complex_domain_or_constraint")
    if len(_string_list(task_identity.get("active_routes"))) >= 2:
        score += 1
        reasons.append("compound_task_identity")
    if len(_string_list(context.get("files_changed"))) >= 2:
        score += 1
        reasons.append("multiple_changed_surfaces")
    if _string_list(context.get("failures")):
        score += 1
        reasons.append("runtime_failure")
    if any(term in lower for term in (" then ", " before ", " after ", " and verify")):
        score += 1
        reasons.append("multi_phase_or_verification")
    phase_actions = [
        marker
        for marker in MULTI_PHASE_ACTION_MARKERS
        if re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?:s|ed|ing)?(?![a-z0-9])", lower)
    ]
    if len(phase_actions) >= 3 and "multi_phase_or_verification" not in reasons:
        score += 1
        reasons.append("multi_phase_or_verification")
    return score, reasons


def decide_admission(
    objective: str,
    task_identity: Mapping[str, Any],
    *,
    mode: object = "forced",
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a transparent bypass, shadow, compose, or forced decision."""

    context = context or {}
    normalized_mode = normalize_admission_mode(mode)
    confidence = float(task_identity.get("confidence") or 0.0)
    primary = str(task_identity.get("primary") or "general_task")
    complexity, complexity_reasons = complexity_score(
        objective, task_identity, context
    )
    trivial = _is_trivial(objective, context)
    eligible = (
        not trivial
        and primary != "general_task"
        and confidence >= AUTO_COMPOSE_MIN_CONFIDENCE
        and complexity >= AUTO_COMPOSE_MIN_COMPLEXITY
    )
    if trivial:
        recommendation = "bypass"
        reasons = ["trivial_request"]
    elif primary == "general_task":
        recommendation = "bypass"
        reasons = ["unresolved_task_identity"]
    elif confidence < AUTO_COMPOSE_MIN_CONFIDENCE:
        recommendation = "bypass"
        reasons = ["route_confidence_below_threshold"]
    elif complexity < AUTO_COMPOSE_MIN_COMPLEXITY:
        recommendation = "bypass"
        reasons = ["composition_value_below_threshold"]
    else:
        recommendation = "compose"
        reasons = ["task_complexity_and_route_confidence_support_composition"]
    reasons.extend(complexity_reasons)

    if normalized_mode == "forced":
        action = "forced"
        reasons.insert(0, "explicit_tmcp_invocation")
    elif normalized_mode == "shadow":
        action = "shadow"
    else:
        action = recommendation

    expected_value = "high" if eligible else "low"
    return {
        "policy_version": ADMISSION_POLICY_VERSION,
        "mode": normalized_mode,
        "action": action,
        "recommended_action": recommendation,
        "expected_value": expected_value,
        "route_confidence": confidence,
        "complexity_score": complexity,
        "minimum_confidence": AUTO_COMPOSE_MIN_CONFIDENCE,
        "minimum_complexity": AUTO_COMPOSE_MIN_COMPLEXITY,
        "trivial": trivial,
        "reasons": list(dict.fromkeys(reasons)),
    }


def apply_packet_utility_gate(
    admission: Mapping[str, Any],
    *,
    selected_source_count: int,
    task_specific_contribution_count: int,
) -> dict[str, Any]:
    """Downgrade automatic admission when the compiled packet adds no substance."""

    decision = dict(admission)
    useful = selected_source_count > 0 and task_specific_contribution_count > 0
    decision["selected_source_count"] = selected_source_count
    decision["task_specific_contribution_count"] = task_specific_contribution_count
    decision["packet_utility"] = "useful" if useful else "insufficient"
    if useful or decision.get("mode") == "forced":
        return decision
    decision["recommended_action"] = "bypass"
    decision["expected_value"] = "low"
    decision["reasons"] = list(
        dict.fromkeys(
            [*list(decision.get("reasons") or []), "no_task_specific_packet_contribution"]
        )
    )
    if decision.get("mode") == "automatic":
        decision["action"] = "bypass"
    return decision
