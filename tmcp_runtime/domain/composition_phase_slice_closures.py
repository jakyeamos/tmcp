"""Closed cited-slice projections for phase-scoped composition context."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .harvest_nodes import content_digest_for, normalized_source_content


class PhaseSliceClosureError(ValueError):
    """Raised when a phase context would load an uncited or missing source slice."""


def _required(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise PhaseSliceClosureError(f"{field} is required.")
    return result


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise PhaseSliceClosureError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise PhaseSliceClosureError(f"{field} must contain only objects.")
    return result


def _string_list(value: object, *, field: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise PhaseSliceClosureError(f"{field} must be a sequence of strings.")
    result = [_required(item, field=field) for item in value]
    if len(result) != len(set(result)):
        raise PhaseSliceClosureError(f"{field} must not repeat values.")
    return result


def validate_stage_source_slice_closures(
    source_projection: Mapping[str, Any],
    stages: Sequence[Mapping[str, Any]],
    *,
    sources_by_skill: Mapping[str, Sequence[Mapping[str, Any]]],
    governing_skill_ids: Sequence[str],
) -> dict[str, dict[str, set[str]]] | None:
    """Validate optional compiler-issued cited-slice closures by stage."""

    raw_closures = source_projection.get("stage_source_slice_ids")
    if raw_closures is None:
        return None
    if not isinstance(raw_closures, Mapping):
        raise PhaseSliceClosureError("stage_source_slice_ids must be an object.")
    expected_stages = {str(stage["stage_id"]) for stage in stages}
    if {str(stage_id) for stage_id in raw_closures} != expected_stages:
        raise PhaseSliceClosureError(
            "stage_source_slice_ids must cover each runtime stage exactly."
        )
    skill_by_node = {
        str(sources[0]["source_node_id"]): skill_id
        for skill_id, sources in sources_by_skill.items()
    }
    result: dict[str, dict[str, set[str]]] = {}
    for stage in stages:
        stage_id = str(stage["stage_id"])
        raw_stage = raw_closures.get(stage_id)
        if not isinstance(raw_stage, Mapping):
            raise PhaseSliceClosureError(
                f"stage_source_slice_ids.{stage_id} must be an object."
            )
        skill_ids = list(
            dict.fromkeys(list(governing_skill_ids) + list(stage["active_skill_ids"]))
        )
        required_nodes = {
            str(sources_by_skill[skill_id][0]["source_node_id"])
            for skill_id in skill_ids
        }
        if {str(node_id) for node_id in raw_stage} != required_nodes:
            raise PhaseSliceClosureError(
                f"stage_source_slice_ids.{stage_id} must cover its active and governing sources exactly."
            )
        closure: dict[str, set[str]] = {}
        for node_id in sorted(required_nodes):
            slice_ids = _string_list(
                raw_stage.get(node_id),
                field=f"stage_source_slice_ids.{stage_id}.{node_id}",
            )
            if not slice_ids:
                raise PhaseSliceClosureError(
                    f"stage_source_slice_ids.{stage_id}.{node_id} must not be empty."
                )
            skill_id = skill_by_node.get(node_id)
            if skill_id is None:
                raise PhaseSliceClosureError(
                    f"stage_source_slice_ids.{stage_id} references unknown source {node_id}."
                )
            available = {
                str(source["source_slice_id"])
                for source in sources_by_skill[skill_id]
            }
            unknown = sorted(set(slice_ids).difference(available))
            if unknown:
                raise PhaseSliceClosureError(
                    f"stage_source_slice_ids.{stage_id}.{node_id} references unknown source slices: {unknown}."
                )
            closure[node_id] = set(slice_ids)
        result[stage_id] = closure
    return result


def source_capsule_entries(
    skill_ids: Sequence[str],
    *,
    sources_by_skill: Mapping[str, Sequence[Mapping[str, Any]]],
    allowed_slice_ids_by_node: Mapping[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    """Project exactly the source slices a runtime capsule is allowed to load."""

    entries: list[dict[str, Any]] = []
    for skill_id in skill_ids:
        sources = sources_by_skill[skill_id]
        source_node_id = str(sources[0]["source_node_id"])
        allowed = (
            allowed_slice_ids_by_node.get(source_node_id)
            if allowed_slice_ids_by_node is not None
            else None
        )
        selected = [
            dict(source)
            for source in sources
            if allowed is None or str(source["source_slice_id"]) in allowed
        ]
        if not selected:
            raise PhaseSliceClosureError(
                "stage source-slice closure omitted every cited slice for "
                f"{source_node_id}."
            )
        entries.extend(selected)
    return entries


def composition_identity(source_projection: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: str(source_projection[key])
        for key in (
            "composition_plan_id",
            "composition_plan_digest",
            "graph_digest",
        )
        if str(source_projection.get(key) or "").strip()
    }


def preflight_candidate_entries(
    preflight: Mapping[str, Any],
    *,
    sources_by_skill: Mapping[str, Sequence[Mapping[str, Any]]],
    skill_by_node: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Canonicalize bounded discovery candidates without activating them."""

    entries: list[dict[str, Any]] = []
    for index, candidate in enumerate(
        _mapping_list(
            preflight.get("candidate_source_slices"),
            field="preflight.candidate_source_slices",
        )
    ):
        field = f"preflight.candidate_source_slices[{index}]"
        content = candidate.get("content")
        if not isinstance(content, str):
            raise PhaseSliceClosureError(f"{field}.content must be a string.")
        normalized = normalized_source_content(content)
        if not normalized:
            raise PhaseSliceClosureError(f"{field}.content must not be empty.")
        source_node_id = _required(
            candidate.get("source_node_id"), field=f"{field}.source_node_id"
        )
        expected_digest = content_digest_for(normalized)
        declared_slice_digest = str(candidate.get("slice_digest") or "").strip()
        if declared_slice_digest and declared_slice_digest != expected_digest:
            raise PhaseSliceClosureError(
                f"{field}.slice_digest does not match normalized candidate content."
            )
        declared_source_digest = str(candidate.get("source_digest") or "").strip()
        matched_skill_id = skill_by_node.get(source_node_id)
        if matched_skill_id is not None and declared_source_digest:
            expected_source_digest = str(
                sources_by_skill[matched_skill_id][0]["source_digest"]
            )
            if declared_source_digest != expected_source_digest:
                raise PhaseSliceClosureError(
                    f"{field}.source_digest does not match supplied source content."
                )
        entries.append(
            {
                "slice_id": _required(candidate.get("slice_id"), field=f"{field}.slice_id"),
                "source_node_id": source_node_id,
                "source_role": str(candidate.get("source_role") or "").strip(),
                "source_digest": declared_source_digest or expected_digest,
                "slice_digest": declared_slice_digest or expected_digest,
                "content": normalized,
            }
        )
    role_order = {
        "governing_instruction": 0,
        "active_skill": 1,
        "supporting_reference": 2,
        "evidence_only": 3,
    }
    return sorted(
        entries,
        key=lambda item: (
            role_order.get(item["source_role"], 4),
            item["source_digest"],
            item["slice_digest"],
            item["slice_id"],
        ),
    )


def plan_stage_source_slice_closure(
    plan: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> tuple[dict[str, dict[str, list[str]]], set[str]]:
    """Return exact runtime citations for each stage of a validated plan."""

    candidates = {
        _required(item.get("slice_id"), field="preflight source slice id"): item
        for item in _mapping_list(
            preflight.get("candidate_source_slices"),
            field="composition_preflight.candidate_source_slices",
        )
    }
    role_citations: dict[str, set[str]] = {}
    governing_nodes: set[str] = set()
    for index, role in enumerate(
        _mapping_list(plan.get("skill_roles"), field="composition_plan.skill_roles"),
        start=1,
    ):
        field = f"composition_plan.skill_roles[{index}]"
        node_id = _required(role.get("node_id"), field=f"{field}.node_id")
        if node_id in role_citations:
            raise PhaseSliceClosureError("composition_plan.skill_roles repeats a node.")
        citations = set(_string_list(role.get("citations"), field=f"{field}.citations"))
        if not citations:
            raise PhaseSliceClosureError(f"{field}.citations must not be empty.")
        for citation in citations:
            candidate = candidates.get(citation)
            if candidate is None or _required(
                candidate.get("source_node_id"), field=f"preflight.{citation}.source_node_id"
            ) != node_id:
                raise PhaseSliceClosureError(
                    f"{field}.citations must belong to the role source."
                )
        role_citations[node_id] = citations
        if str(role.get("source_role") or "") == "governing_instruction":
            governing_nodes.add(node_id)
    declared_governing = set(
        _string_list(
            plan.get("governing_node_ids") or [],
            field="composition_plan.governing_node_ids",
        )
    )
    if declared_governing and declared_governing != governing_nodes:
        raise PhaseSliceClosureError(
            "composition_plan.governing_node_ids does not match role sources."
        )

    stage_nodes: dict[str, set[str]] = {}
    stages = _mapping_list(plan.get("ordered_stages"), field="composition_plan.ordered_stages")
    for index, stage in enumerate(stages, start=1):
        field = f"composition_plan.ordered_stages[{index}]"
        stage_id = _required(stage.get("stage_id"), field=f"{field}.stage_id")
        node_ids = set(_string_list(stage.get("node_ids") or [], field=f"{field}.node_ids"))
        if stage_id in stage_nodes or not node_ids or not node_ids.issubset(role_citations):
            raise PhaseSliceClosureError(
                f"{field}.node_ids must cover selected role sources."
            )
        stage_nodes[stage_id] = node_ids
    if not stage_nodes:
        raise PhaseSliceClosureError("composition_plan.ordered_stages is required.")
    closure = {
        stage_id: {
            node_id: set(role_citations[node_id])
            for node_id in sorted(governing_nodes.union(node_ids))
        }
        for stage_id, node_ids in stage_nodes.items()
    }

    def add_citations(citations: object, *, endpoints: set[str], field: str) -> None:
        for citation in _string_list(citations, field=field):
            candidate = candidates.get(citation)
            if candidate is None:
                raise PhaseSliceClosureError(f"{field} references an unknown source slice.")
            source_node = _required(
                candidate.get("source_node_id"), field=f"preflight.{citation}.source_node_id"
            )
            if source_node not in role_citations:
                raise PhaseSliceClosureError(f"{field} references an unselected source.")
            for stage_id, node_ids in stage_nodes.items():
                if source_node in governing_nodes.union(node_ids) and endpoints.intersection(node_ids):
                    closure[stage_id][source_node].add(citation)

    for index, edge in enumerate(
        _mapping_list(plan.get("typed_edges"), field="composition_plan.typed_edges"),
        start=1,
    ):
        field = f"composition_plan.typed_edges[{index}]"
        add_citations(
            edge.get("citations"),
            endpoints={
                _required(edge.get("from"), field=f"{field}.from"),
                _required(edge.get("to"), field=f"{field}.to"),
            },
            field=f"{field}.citations",
        )

    def add_handoff(contract: Mapping[str, Any], *, field: str) -> None:
        add_citations(
            contract.get("citations"),
            endpoints={
                _required(contract.get("producer_node_id"), field=f"{field}.producer_node_id"),
                _required(contract.get("consumer_node_id"), field=f"{field}.consumer_node_id"),
            },
            field=f"{field}.citations",
        )

    for index, contract in enumerate(
        _mapping_list(plan.get("handoff_contracts") or [], field="composition_plan.handoff_contracts"),
        start=1,
    ):
        add_handoff(contract, field=f"composition_plan.handoff_contracts[{index}]")
    for index, stage in enumerate(stages, start=1):
        stage_id = _required(stage.get("stage_id"), field="stage.stage_id")
        stage_sources = governing_nodes.union(stage_nodes[stage_id])
        for bridge_index, bridge in enumerate(
            _mapping_list(stage.get("bridge_instructions") or [], field="stage.bridge_instructions"),
            start=1,
        ):
            field = f"composition_plan.ordered_stages[{index}].bridge_instructions[{bridge_index}]"
            node_id = _required(bridge.get("node_id"), field=f"{field}.node_id")
            if node_id not in stage_sources:
                raise PhaseSliceClosureError(f"{field}.node_id must be active or governing.")
            for citation in _string_list(bridge.get("citations"), field=f"{field}.citations"):
                candidate = candidates.get(citation)
                if candidate is None or _required(
                    candidate.get("source_node_id"),
                    field=f"preflight.{citation}.source_node_id",
                ) != node_id:
                    raise PhaseSliceClosureError(
                        f"{field}.citations must belong to its source."
                    )
                closure[stage_id][node_id].add(citation)
        for contract_index, contract in enumerate(
            _mapping_list(stage.get("handoff_contracts") or [], field="stage.handoff_contracts"),
            start=1,
        ):
            add_handoff(
                contract,
                field=(
                    f"composition_plan.ordered_stages[{index}].handoff_contracts[{contract_index}]"
                ),
            )

    result = {
        stage_id: {
            node_id: sorted(citations)
            for node_id, citations in sorted(source_map.items())
            if citations
        }
        for stage_id, source_map in sorted(closure.items())
    }
    if any(
        set(source_map) != governing_nodes.union(stage_nodes[stage_id])
        for stage_id, source_map in result.items()
    ):
        raise PhaseSliceClosureError(
            "Each runtime stage requires cited slices for every active and governing source."
        )
    return result, {
        citation
        for source_map in result.values()
        for citations in source_map.values()
        for citation in citations
    }
