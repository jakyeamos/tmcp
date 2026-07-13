"""Global-promotion artifact assembly over safe adapter callbacks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from tmcp_runtime.services.artifact_plans import ArtifactPlan


GraphNormalizer = Callable[[Mapping[str, Any], str], dict[str, Any]]
MappingRedactor = Callable[[dict[str, Any]], dict[str, Any]]
ArtifactPlanBuilder = Callable[
    [dict[str, Any], dict[str, Any], dict[str, Any] | None], ArtifactPlan
]
NowIso = Callable[[], str]


@dataclass(frozen=True)
class GlobalPromotionContext:
    """Policy callbacks supplied by the adapter for global promotion."""

    normalize_graph: GraphNormalizer
    redact_mapping: MappingRedactor
    build_artifact_plan: ArtifactPlanBuilder
    now_iso: NowIso


class GlobalPromotionArtifactService:
    """Build a safe global-promotion manifest without choosing or writing paths."""

    def __init__(self, context: GlobalPromotionContext) -> None:
        self._context = context

    def build(
        self,
        result: Mapping[str, Any],
        promotion_name: str,
    ) -> ArtifactPlan:
        """Normalize and redact promotion data before manifest assembly."""

        created_at = self._context.now_iso()
        graph = self._context.normalize_graph(result, created_at)
        safe_graph = self._context.redact_mapping(graph)
        summary = {
            "schema": "tmcp-global-promoted-harvest-v0.1",
            "promotion_name": promotion_name,
            "created_at": created_at,
            "promoted_workflow_ids": _string_list(result.get("promoted_workflow_ids")),
            "promoted_scoped_packet_seed_ids": _string_list(
                result.get("promoted_scoped_packet_seed_ids")
            ),
            "promotion_graph": safe_graph,
            "trust": "advisory_untrusted",
        }
        safe_summary = self._context.redact_mapping(summary)
        adaptive_pack = result.get("adaptive_workflow_pack")
        safe_adaptive_pack = (
            self._context.redact_mapping(adaptive_pack)
            if isinstance(adaptive_pack, dict)
            else None
        )
        return self._context.build_artifact_plan(
            safe_summary,
            safe_graph,
            safe_adaptive_pack,
        )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
