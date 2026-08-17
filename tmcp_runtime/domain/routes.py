from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .route_catalog import (
    COMPOSITE_TASK_PROFILES,
    LEGACY_SEED_MATCH_THRESHOLD,
    MAX_SECONDARY_ROUTES,
    ROUTE_CATALOG_VERSION,
    ROUTE_SCORE_THRESHOLD,
    ROUTE_SOURCE_SLUG_PATTERNS,
    SEED_MATCH_THRESHOLD,
    SEED_MATCH_THRESHOLD_WITH_ROUTE_AFFINITY,
    UI_FILE_SUFFIXES,
)
from .route_resolution import resolve_primary_route
from .signal_text import affirmed_terms_in_text


@dataclass(frozen=True)
class RouteDefinition:
    route_id: str
    objective_terms: tuple[str, ...]
    context_boost: Callable[[dict[str, Any]], tuple[float, list[str]]] | None = None
    negative_terms: tuple[str, ...] = ()
    domain: str = "general"
    action: str = "execute"
    mode: str = "implementation"


def _ui_file_boost(context: dict[str, Any]) -> tuple[float, list[str]]:
    files_changed = context.get("files_changed") or []
    if not isinstance(files_changed, list):
        return 0.0, []
    ui_files = [
        path for path in files_changed if str(path).lower().endswith(UI_FILE_SUFFIXES)
    ]
    if not ui_files:
        return 0.0, []
    return 2.5, [f"files_changed: {path}" for path in ui_files[:3]]


def _failure_boost(context: dict[str, Any]) -> tuple[float, list[str]]:
    failures = context.get("failures") or []
    if not isinstance(failures, list) or not failures:
        return 0.0, []
    return 3.0, [f"failure: {str(item)[:120]}" for item in failures[:2]]


def _browser_evidence_boost(context: dict[str, Any]) -> tuple[float, list[str]]:
    browser_evidence = context.get("browser_evidence") or []
    if not isinstance(browser_evidence, list) or not browser_evidence:
        return 0.0, []
    return 2.0, ["browser_evidence: present"]


ROUTE_DEFINITIONS: tuple[RouteDefinition, ...] = (
    RouteDefinition(
        "explicit_audit",
        (
            "audit",
            "assess readiness",
            "readiness review",
            "risk review",
            "review findings",
        ),
        domain="governance",
        action="audit",
        mode="review",
    ),
    RouteDefinition(
        "ui_ux_redesign",
        (
            "redesign",
            "visually striking",
            "visual design",
            "modern",
            "polish",
            "landing",
            "ui refresh",
            "make it look",
        ),
        _ui_file_boost,
        domain="frontend",
        action="redesign",
    ),
    RouteDefinition(
        "frontend_implementation",
        (
            "frontend implementation",
            "implement component",
            "build component",
            "component",
            "react",
            "web page",
            "landing page",
            "production-ready",
            "tsx",
            "frontend",
        ),
        _ui_file_boost,
        negative_terms=(
            "rest api",
            "backend",
            "database",
            "schema migration",
            "command line",
        ),
        domain="frontend",
    ),
    RouteDefinition(
        "backend_api_implementation",
        (
            "backend",
            "rest api",
            "graphql api",
            "api endpoint",
            "endpoint",
            "server side",
            "service layer",
            "webhook",
        ),
        negative_terms=("frontend", "react component", "landing page"),
        domain="backend",
    ),
    RouteDefinition(
        "data_database_migration",
        (
            "database",
            "schema migration",
            "data migration",
            "backfill",
            "table migration",
            "column migration",
            "database index",
        ),
        domain="data",
        action="migrate",
    ),
    RouteDefinition(
        "security_remediation",
        (
            "security remediation",
            "fix vulnerability",
            "fix a vulnerability",
            "patch vulnerability",
            "security fix",
            "harden authentication",
            "credential leak",
        ),
        domain="security",
        action="remediate",
    ),
    RouteDefinition(
        "documentation",
        (
            "write documentation",
            "update documentation",
            "api documentation",
            "developer guide",
            "readme update",
            "document behavior",
        ),
        domain="documentation",
        action="document",
        mode="writing",
    ),
    RouteDefinition(
        "test_strategy",
        (
            "test strategy",
            "testing strategy",
            "test plan",
            "test coverage plan",
            "quality strategy",
            "dogfood",
        ),
        domain="quality",
        action="plan",
        mode="planning",
    ),
    RouteDefinition(
        "architecture_decision",
        (
            "architecture decision",
            "design decision",
            "adr",
            "system architecture",
            "compatibility design",
        ),
        domain="architecture",
        action="decide",
        mode="planning",
    ),
    RouteDefinition(
        "agent_workflow",
        (
            "agent workflow",
            "agent handoff",
            "multi agent workflow",
            "routing policy",
            "workflow automation",
        ),
        domain="agent_operations",
        action="design",
        mode="planning",
    ),
    RouteDefinition(
        "general_implementation",
        (
            "implement feature",
            "implement this",
            "add support",
            "code change",
            "build feature",
            "build a feature",
        ),
        domain="software",
    ),
    RouteDefinition(
        "motion_interaction",
        (
            "motion",
            "animation",
            "interactive",
            "micro-interaction",
            "motion-rich",
        ),
        domain="frontend",
        action="animate",
    ),
    RouteDefinition(
        "freshness_research",
        (
            "trend",
            "current design",
            "research",
            "inspiration",
            "what's modern",
        ),
        domain="research",
        action="research",
        mode="research",
    ),
    RouteDefinition(
        "accessibility_validation",
        (
            "a11y",
            "accessibility",
            "contrast",
            "reduced motion",
            "wcag",
            "screen reader",
        ),
        domain="accessibility",
        action="validate",
        mode="verification",
    ),
    RouteDefinition(
        "performance_validation",
        (
            "performance",
            "bundle",
            "latency",
            "lighthouse",
            "core web vitals",
        ),
        domain="performance",
        action="validate",
        mode="verification",
    ),
    RouteDefinition(
        "debugging_regression",
        (
            "bug",
            "failing",
            "failure",
            "debug",
            "regression",
            "broken",
        ),
        _failure_boost,
        domain="debugging",
        action="diagnose",
        mode="debugging",
    ),
    RouteDefinition(
        "release_readiness",
        (
            "release",
            "ship",
            "deploy",
            "changelog",
            "production release",
        ),
        domain="release",
        action="validate",
        mode="verification",
    ),
)

KNOWN_ROUTE_IDS = frozenset(route.route_id for route in ROUTE_DEFINITIONS)


def route_definitions_by_id() -> dict[str, RouteDefinition]:
    return {route.route_id: route for route in ROUTE_DEFINITIONS}


def seed_match_threshold(route_affinity_overlap: int) -> float:
    if route_affinity_overlap >= 2:
        return SEED_MATCH_THRESHOLD_WITH_ROUTE_AFFINITY
    return SEED_MATCH_THRESHOLD


def route_affinity_overlap(seed_routes: list[str], active_routes: list[str]) -> int:
    return len(set(seed_routes).intersection(active_routes))


def _pattern_matches_node(pattern: str, rel_lower: str, text_lower: str) -> bool:
    normalized = pattern.lower().replace("_", "-")
    if normalized in text_lower:
        return True
    slug = ""
    parts = [part for part in rel_lower.split("/") if part]
    if len(parts) >= 2 and parts[-1] == "skill.md":
        slug = parts[-2].replace("_", "-")
    if slug and normalized in slug:
        if slug == normalized or slug.startswith(f"{normalized}-"):
            return True
        if f"-{normalized}" in slug and normalized not in {"ui", "ux"}:
            return slug.endswith(f"-{normalized}") or f"-{normalized}-" in slug
    return normalized in rel_lower


def source_boost_for_node(
    route_id: str,
    *,
    relative_path: str,
    source_type: str,
    text: str,
) -> float:
    rel_lower = relative_path.lower().replace("_", "-")
    text_lower = text.lower()
    boost = 0.0
    for pattern in ROUTE_SOURCE_SLUG_PATTERNS.get(route_id, ()):
        if _pattern_matches_node(pattern, rel_lower, text_lower):
            boost += 2.5
    if route_id == "frontend_implementation" and source_type == "skill_definition":
        if any(
            term in rel_lower for term in ("frontend", "react", "ui-implementation")
        ):
            boost += 1.5
    if route_id == "ui_ux_redesign" and source_type == "skill_definition":
        if any(term in rel_lower for term in ("ui-ux", "redesign", "design", "visual")):
            boost += 1.5
    return boost


def composition_route_boost(
    active_routes: list[str],
    *,
    relative_path: str,
    source_type: str,
    text: str,
) -> float:
    if not active_routes:
        return 0.0
    return sum(
        source_boost_for_node(
            route_id,
            relative_path=relative_path,
            source_type=source_type,
            text=text,
        )
        for route_id in active_routes
        if route_id in KNOWN_ROUTE_IDS
    )


def score_scoped_seed(
    seed: dict[str, Any],
    objective: str,
    active_routes: list[str] | None = None,
) -> float:
    seed_id = str(seed.get("seed_id") or seed.get("id") or "")
    score = 0.0
    objective_lower = objective.lower()
    if seed_id and seed_id.lower() in objective_lower:
        score += 8.0
    seed_slug = re.sub(r"_v\d+$", "", seed_id).replace("_", "-")
    if seed_slug and seed_slug in objective_lower.replace("_", "-"):
        score += 6.0
    for pattern in _string_list(seed.get("objective_patterns")):
        if str(pattern).lower() in objective_lower:
            score += 2.5
    objective_terms = set(objective_lower.split())
    for use_when in _string_list(seed.get("use_when")):
        use_terms = set(str(use_when).lower().split())
        score += float(len(objective_terms.intersection(use_terms))) * 1.5
    for source_ref in _string_list(
        seed.get("source_references") or seed.get("sources")
    ):
        slug = _skill_slug_from_path(source_ref)
        if slug and slug.replace("-", " ") in objective_lower.replace("-", " "):
            score += 6.0
        if slug and slug.replace("_", "-") in objective_lower.replace("_", "-"):
            score += 6.0
    seed_routes = _string_list(seed.get("route_affinity"))
    overlap = route_affinity_overlap(seed_routes, active_routes or [])
    score += float(overlap) * 2.0
    return score


def _skill_slug_from_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip().lower()
    if not normalized:
        return ""
    parts = [part for part in normalized.split("/") if part]
    if len(parts) >= 2 and parts[-1] == "skill.md":
        return parts[-2]
    return Path(normalized).stem


def scoped_seed_threshold(
    seed: dict[str, Any], active_routes: list[str] | None = None
) -> float:
    overlap = route_affinity_overlap(
        _string_list(seed.get("route_affinity")), active_routes or []
    )
    if overlap >= 2:
        return seed_match_threshold(overlap)
    if _string_list(seed.get("use_when")) or _string_list(
        seed.get("objective_patterns")
    ):
        return LEGACY_SEED_MATCH_THRESHOLD
    return SEED_MATCH_THRESHOLD


def score_routes(
    objective: str,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    context = context or {}
    combined = objective.strip()
    latest = str(context.get("latest_user_message") or "").strip()
    if latest:
        combined = f"{combined} {latest}".strip()
    scores: list[dict[str, Any]] = []
    route_order = {
        route.route_id: index for index, route in enumerate(ROUTE_DEFINITIONS)
    }
    for route in ROUTE_DEFINITIONS:
        positive_matches = affirmed_terms_in_text(combined, route.objective_terms)
        negative_matches = affirmed_terms_in_text(combined, route.negative_terms)
        evidence = [f"objective: {term}" for term in positive_matches]
        evidence.extend(f"negative: {term}" for term in negative_matches)
        score = float(len(positive_matches)) * 2.0
        score -= float(len(negative_matches)) * 2.5
        if route.context_boost is not None:
            boost, boost_evidence = route.context_boost(context)
            score += boost
            evidence.extend(boost_evidence)
        if score <= 0:
            continue
        scores.append(
            {
                "route": route.route_id,
                "score": round(score, 2),
                "evidence": evidence,
            }
        )
    browser_boost, browser_evidence = _browser_evidence_boost(context)
    if browser_boost:
        for item in scores:
            if item["route"] in {"ui_ux_redesign", "accessibility_validation"}:
                item["score"] = round(float(item["score"]) + browser_boost, 2)
                item["evidence"] = list(item["evidence"]) + browser_evidence
    scores.sort(
        key=lambda item: (
            -float(item["score"]),
            route_order.get(str(item["route"]), len(route_order)),
        )
    )
    return scores


def derive_task_identity(
    objective: str,
    context: dict[str, Any] | None = None,
    family_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    signals = score_routes(objective, context)
    active_routes = [
        str(item["route"])
        for item in signals
        if float(item["score"]) >= ROUTE_SCORE_THRESHOLD
    ]
    if family_context:
        seed_id = str(family_context.get("active_seed_id") or "").strip()
        seed_name = str(family_context.get("seed_name") or "").strip()
        if seed_id:
            signals.insert(
                0,
                {
                    "route": seed_id,
                    "score": 6.0,
                    "evidence": [f"scoped_packet_seed: {seed_id}"],
                },
            )
            if seed_id not in active_routes:
                active_routes.insert(0, seed_id)
        for route in _string_list(family_context.get("route_affinity")):
            if route not in active_routes:
                active_routes.append(route)
        if seed_name and not active_routes:
            active_routes.append(seed_id or seed_name)
    primary = (
        resolve_primary_route(active_routes, objective)
        if active_routes
        else "general_task"
    )
    secondary = [route for route in active_routes if route != primary][
        :MAX_SECONDARY_ROUTES
    ]
    active_signal_scores = [
        float(item["score"]) for item in signals if str(item["route"]) in active_routes
    ]
    top_score = active_signal_scores[0] if active_signal_scores else 0.0
    next_score = active_signal_scores[1] if len(active_signal_scores) > 1 else 0.0
    margin = max(0.0, top_score - next_score)
    confidence = (
        min(0.99, round(0.4 + (top_score / 10.0) + (margin / 20.0), 2))
        if active_routes
        else 0.0
    )
    route_definition = route_definitions_by_id().get(primary)
    profile = COMPOSITE_TASK_PROFILES.get(primary)
    if profile is None and route_definition is not None:
        profile = {
            "domain": route_definition.domain,
            "action": route_definition.action,
            "mode": route_definition.mode,
        }
    if profile is None:
        profile = {"domain": "general", "action": "execute", "mode": "general"}
    return {
        "primary": primary,
        "secondary": secondary,
        "active_routes": active_routes[: MAX_SECONDARY_ROUTES + 1],
        "confidence": confidence,
        "domain": profile["domain"],
        "action": profile["action"],
        "mode": profile["mode"],
        "ambiguous": bool(len(active_signal_scores) > 1 and margin < 1.0),
        "signals": signals[:10],
        "route_catalog_version": ROUTE_CATALOG_VERSION,
    }


def task_identity_delta(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    reason: str = "",
) -> dict[str, Any] | None:
    if not previous:
        return None
    prev_primary = str(previous.get("primary") or "")
    curr_primary = str(current.get("primary") or "")
    prev_routes = set(_string_list(previous.get("active_routes")))
    curr_routes = set(_string_list(current.get("active_routes")))
    changed_routes = sorted(prev_routes ^ curr_routes)
    if prev_primary == curr_primary and not changed_routes:
        return None
    return {
        "previous": previous,
        "current": current,
        "changed_routes": changed_routes,
        "reason": reason or _delta_reason(previous, current, changed_routes),
    }


def _delta_reason(
    previous: dict[str, Any],
    current: dict[str, Any],
    changed_routes: list[str],
) -> str:
    if str(previous.get("primary") or "") != str(current.get("primary") or ""):
        return "task_identity_primary_changed"
    if changed_routes:
        return "task_identity_routes_changed"
    return "task_identity_updated"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def validate_proposed_changes(
    proposed_changes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    validated: list[dict[str, Any]] = []
    warnings: list[str] = []
    for change in proposed_changes:
        if not isinstance(change, dict):
            warnings.append("Ignored non-object proposed change.")
            continue
        action = str(change.get("action") or "")
        if action == "add_route":
            route = str(change.get("route") or "")
            if route in KNOWN_ROUTE_IDS:
                validated.append(change)
            else:
                warnings.append(f"Rejected proposed change: unknown route `{route}`.")
            continue
        warnings.append(f"Rejected proposed change: unsupported action `{action}`.")
    return validated, warnings
