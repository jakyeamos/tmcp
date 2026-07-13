"""Read-only projections for legacy TMCP artifact formats."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


LEGACY_GLOBAL_PROMOTION_SCHEMA = "tmcp-global-promoted-harvest-v0.1"


def migrate_legacy_promotion_summary(
    payload: Mapping[str, Any],
    *,
    graph_schema: str,
) -> dict[str, Any] | None:
    """Project a legacy summary artifact onto the current graph contract.

    The projection is in-memory and never rewrites or deletes the source file.
    Current ``promotion-graph.json`` artifacts remain the preferred source when
    both formats exist in one promotion directory.
    """

    if payload.get("schema") != LEGACY_GLOBAL_PROMOTION_SCHEMA:
        return None
    graph = payload.get("promotion_graph")
    if not isinstance(graph, dict):
        return None
    migrated = dict(graph)
    migrated["schema"] = graph_schema
    migrated["promotion_name"] = payload.get("promotion_name") or graph.get(
        "promotion_name"
    )
    migrated["created_at"] = graph.get("created_at") or payload.get("created_at")
    migrated["trust"] = "advisory_untrusted"
    return migrated
