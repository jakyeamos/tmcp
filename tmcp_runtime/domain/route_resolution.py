"""Primary-route precedence for compound task identities."""

from __future__ import annotations

from .route_catalog import (
    COMPOSITE_PRIMARY_ROUTES,
    CREATION_OR_RESEARCH_LEADS,
    CREATION_OR_RESEARCH_ROUTES,
)


def resolve_primary_route(active_routes: list[str], objective: str = "") -> str:
    active = set(active_routes)
    for primary, required in COMPOSITE_PRIMARY_ROUTES.items():
        if required.issubset(active):
            return primary
    leading_word = (
        objective.strip().lower().split(maxsplit=1)[0] if objective.strip() else ""
    )
    if "explicit_audit" in active and leading_word in CREATION_OR_RESEARCH_LEADS:
        for route in active_routes:
            if route in CREATION_OR_RESEARCH_ROUTES:
                return route
    if "explicit_audit" in active:
        return "explicit_audit"
    return active_routes[0] if active_routes else "general_task"
