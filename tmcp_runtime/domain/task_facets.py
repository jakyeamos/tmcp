"""Deterministic, source-cited task facets for unresolved compound work."""

from __future__ import annotations

import re
from typing import Any


FACET_DEFINITIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "discovery",
        (
            "discover",
            "assess",
            "analyze",
            "investigate",
            "research",
            "diagnose",
            "trace",
            "clarify",
            "evaluate",
            "find",
            "gather",
            "reconcile",
        ),
    ),
    (
        "planning",
        (
            "plan",
            "design",
            "define",
            "decide",
            "specify",
            "model",
            "structure",
            "restructure",
            "establish",
            "prepare",
            "compose",
            "route",
            "map",
        ),
    ),
    (
        "implementation",
        (
            "implement",
            "build",
            "create",
            "generate",
            "write",
            "draft",
            "patch",
            "fix",
            "harden",
            "hardening",
            "apply",
            "migrate",
            "ship",
            "rebuild",
        ),
    ),
    (
        "verification",
        (
            "verify",
            "validate",
            "test",
            "review",
            "audit",
            "inspect",
            "prove",
            "check",
            "evidence",
            "receipt",
            "regression",
            "benchmark",
            "cover",
            "confirm",
            "protect",
            "gate",
            "parity",
            "idempotency",
        ),
    ),
    (
        "lifecycle",
        (
            "promote",
            "promotion",
            "cache",
            "recipe",
            "deploy",
            "release",
            "install",
            "harvest",
            "recompile",
            "runtime",
            "cutover",
            "rollback",
            "handoff",
            "retain",
            "preserve",
            "recover",
            "recovery",
        ),
    ),
)


def lexical_term_matches(text: str, term: str) -> bool:
    """Match a configured prefix only at a lexical boundary."""

    return re.search(rf"(?<!\w){re.escape(term.lower())}", text.lower()) is not None


def derive_intent_facets(
    objective: str,
    latest_user_message: str = "",
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return stable intent facets and objective-backed evidence for each facet."""

    objective_lower = objective.lower()
    latest_lower = latest_user_message.lower()
    facets: list[str] = []
    signals: list[dict[str, Any]] = []
    for facet, terms in FACET_DEFINITIONS:
        objective_matches = [
            term for term in terms if lexical_term_matches(objective_lower, term)
        ]
        latest_matches = [
            term for term in terms if lexical_term_matches(latest_lower, term)
        ]
        if objective_matches or latest_matches:
            facets.append(facet)
            signals.append(
                {
                    "facet": facet,
                    "evidence": (
                        [f"objective: {term}" for term in objective_matches]
                        + [f"latest_user_message: {term}" for term in latest_matches]
                    )[:4],
                }
            )
    return facets, signals
