"""Materialized source and graph provenance for composition benchmarks."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .composition_preflight import stable_digest
from .harvest_nodes import content_digest_for


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
    return result


def _nonempty_strings(value: object, *, field: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of strings.")
    result = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if len(result) != len(value) or not result or len(set(result)) != len(result):
        raise ValueError(f"{field} must contain unique nonempty strings.")
    return result


def _relationship_source(relationship: Mapping[str, Any]) -> str:
    return str(
        relationship.get("source_id")
        or relationship.get("from")
        or relationship.get("source")
        or ""
    ).strip()


def _relationship_target(relationship: Mapping[str, Any]) -> str:
    return str(
        relationship.get("target_id")
        or relationship.get("to")
        or relationship.get("target")
        or ""
    ).strip()


def fixture_source_node_id(
    fixture_id: str,
    skill_id: str,
    content: str,
) -> str:
    """Return the content-derived source identity used by benchmark replays."""

    return "benchmark-source-" + stable_digest(
        {
            "fixture_id": fixture_id,
            "skill_id": skill_id,
            "content_digest": content_digest_for(content),
        },
        20,
    )


def validate_fixture_skill_sources(
    fixture_id: str,
    fixture: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    candidate_skill_ids = _nonempty_strings(
        fixture.get("candidate_skill_ids"),
        field=f"{fixture_id}.candidate_skill_ids",
    )
    raw_sources = _mapping_list(
        fixture.get("skill_sources"),
        field=f"{fixture_id}.skill_sources",
    )
    sources: dict[str, Mapping[str, Any]] = {}
    relative_paths: set[str] = set()
    for index, source in enumerate(raw_sources, start=1):
        field = f"{fixture_id}.skill_sources[{index}]"
        skill_id = str(source.get("skill_id") or "").strip()
        relative_path = str(source.get("relative_path") or "").strip()
        content = str(source.get("content") or "").strip()
        if not skill_id or not relative_path or len(content) < 40:
            raise ValueError(
                f"{field} requires skill_id, relative_path, and behavior-bearing content."
            )
        if skill_id in sources:
            raise ValueError(f"{fixture_id} has duplicate skill source {skill_id}.")
        if relative_path in relative_paths:
            raise ValueError(
                f"{fixture_id} has duplicate skill source path {relative_path}."
            )
        if not relative_path.startswith("skills/") or not relative_path.endswith(
            "/SKILL.md"
        ):
            raise ValueError(
                f"{field}.relative_path must be a stable skills/<id>/SKILL.md path."
            )
        sources[skill_id] = source
        relative_paths.add(relative_path)
    candidates = set(candidate_skill_ids)
    if set(sources) != candidates:
        raise ValueError(
            f"{fixture_id}.skill_sources must cover every candidate exactly; "
            f"missing={sorted(candidates.difference(sources))}, "
            f"unexpected={sorted(set(sources).difference(candidates))}."
        )
    return sources


def validate_source_slice_bindings(
    fixture_id: str,
    selected_skill_ids: list[str],
    observation: Mapping[str, Any],
    skill_sources: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, set[str]],
    set[str],
    dict[str, str],
    dict[str, Mapping[str, Any]],
]:
    source_slices = _mapping_list(
        observation.get("source_slices"), field=f"{fixture_id}.source_slices"
    )
    if not source_slices:
        raise ValueError(f"{fixture_id}.source_slices must not be empty.")
    bindings: dict[str, set[str]] = {}
    slice_ids: set[str] = set()
    source_node_bindings: dict[str, str] = {}
    node_ids_by_skill: dict[str, set[str]] = {}
    slices_by_id: dict[str, Mapping[str, Any]] = {}
    for index, source_slice in enumerate(source_slices, start=1):
        field = f"{fixture_id}.source_slices[{index}]"
        skill_id = str(source_slice.get("skill_id") or "").strip()
        source_node_id = str(source_slice.get("source_node_id") or "").strip()
        relative_path = str(source_slice.get("relative_path") or "").strip()
        source_path = str(source_slice.get("source_path") or "").strip()
        content = source_slice.get("content")
        slice_id = str(source_slice.get("slice_id") or "").strip()
        if not all(
            (skill_id, source_node_id, relative_path, source_path)
        ) or not isinstance(content, str):
            raise ValueError(
                f"{field} requires skill_id, source identity, path, and content."
            )
        declared_source = skill_sources.get(skill_id)
        if declared_source is None:
            raise ValueError(
                f"{field}.skill_id is not a fixture candidate: {skill_id}."
            )
        if relative_path != str(declared_source["relative_path"]):
            raise ValueError(
                f"{field}.relative_path must match the fixture skill source."
            )
        if not source_path.replace("\\", "/").endswith("/" + relative_path):
            raise ValueError(
                f"{field}.source_path must end with the materialized relative path."
            )
        declared_content = str(declared_source["content"])
        if content != declared_content:
            raise ValueError(
                f"{field}.content must match the materialized fixture source."
            )
        char_start = source_slice.get("char_start")
        char_end = source_slice.get("char_end")
        if char_start != 0 or char_end != len(content):
            raise ValueError(
                f"{field} must bind the complete materialized fixture source slice."
            )
        if re.fullmatch(r"slice-[a-f0-9]{20}", slice_id) is None:
            raise ValueError(f"{field}.slice_id must be a harvested slice id.")
        if slice_id in slice_ids:
            raise ValueError(
                f"{fixture_id}.source_slices contains duplicate {slice_id}."
            )
        digests = {
            key: str(source_slice.get(key) or "").strip()
            for key in ("source_digest", "slice_digest", "content_digest")
        }
        if any(
            re.fullmatch(r"[a-f0-9]{64}", digest) is None for digest in digests.values()
        ):
            raise ValueError(f"{field} source and slice digests must be SHA-256.")
        if digests["content_digest"] != digests["source_digest"]:
            raise ValueError(f"{field}.content_digest must match source_digest.")
        if digests["source_digest"] != content_digest_for(declared_content):
            raise ValueError(
                f"{field}.source_digest must match the materialized fixture source."
            )
        if digests["slice_digest"] != stable_digest(content):
            raise ValueError(
                f"{field}.slice_digest must match the source slice content."
            )
        legacy_path_node_id = hashlib.sha256(
            f"{source_path}:{digests['source_digest']}".encode()
        ).hexdigest()[:12]
        content_node_id = fixture_source_node_id(
            fixture_id,
            skill_id,
            declared_content,
        )
        if source_node_id not in {legacy_path_node_id, content_node_id}:
            raise ValueError(
                f"{field}.source_node_id must match the content-derived benchmark "
                "or legacy materialized source identity."
            )
        expected_slice_id = "slice-" + stable_digest(
            [
                digests["source_digest"],
                digests["slice_digest"],
                0,
                char_end,
                source_node_id,
            ],
            20,
        )
        if slice_id != expected_slice_id:
            raise ValueError(f"{field}.slice_id must be content-derived.")
        bound_skill = source_node_bindings.setdefault(source_node_id, skill_id)
        if bound_skill != skill_id:
            raise ValueError(
                f"{fixture_id} source_node_id {source_node_id} binds multiple skills."
            )
        slice_ids.add(slice_id)
        slices_by_id[slice_id] = source_slice
        bindings.setdefault(skill_id, set()).add(slice_id)
        node_ids_by_skill.setdefault(skill_id, set()).add(source_node_id)
    selected = set(selected_skill_ids)
    if set(bindings) != selected:
        raise ValueError(
            f"{fixture_id}.source_slices must bind every selected skill exactly; "
            f"missing={sorted(selected.difference(bindings))}, "
            f"unexpected={sorted(set(bindings).difference(selected))}."
        )
    ambiguous = sorted(
        skill_id
        for skill_id, node_ids in node_ids_by_skill.items()
        if len(node_ids) != 1
    )
    if ambiguous:
        raise ValueError(
            f"{fixture_id}.source_slices bind skills to multiple source nodes: {ambiguous}."
        )
    return (
        bindings,
        slice_ids,
        {skill_id: next(iter(ids)) for skill_id, ids in node_ids_by_skill.items()},
        slices_by_id,
    )


def graph_digest_for_observation(
    selected_skill_ids: Sequence[str],
    relationships: Sequence[Mapping[str, Any]],
    *,
    source_node_by_skill: Mapping[str, str],
    slices_by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    source_digests = {
        skill_id: str(
            next(
                item.get("source_digest")
                for item in slices_by_id.values()
                if str(item.get("skill_id") or "") == skill_id
            )
        )
        for skill_id in selected_skill_ids
    }
    normalized_edges = sorted(
        {
            (
                source_digests[_relationship_source(relationship)],
                str(relationship.get("relation") or relationship.get("type") or ""),
                source_digests[_relationship_target(relationship)],
                tuple(
                    sorted(
                        str(slices_by_id[citation].get("slice_digest") or "")
                        for citation in _nonempty_strings(
                            relationship.get("citations"),
                            field="relationships.citations",
                        )
                    )
                ),
            )
            for relationship in relationships
        }
    )
    return stable_digest(
        {
            "content_digests": sorted(set(source_digests.values())),
            "edges": normalized_edges,
            "scoped_seed_edges": [],
        },
        32,
    )


def relationship_provenance_is_complete(
    fixture_id: str,
    relationship: Mapping[str, Any],
    *,
    bindings: Mapping[str, set[str]],
    slice_ids: set[str],
) -> bool:
    source_id = _relationship_source(relationship)
    target_id = _relationship_target(relationship)
    if source_id not in bindings or target_id not in bindings:
        raise ValueError(
            f"{fixture_id} relationship endpoints must use bound logical skill ids: "
            f"{source_id!r} -> {target_id!r}."
        )
    citations = set(
        _nonempty_strings(
            relationship.get("citations"),
            field=f"{fixture_id}.relationships.citations",
        )
    )
    unknown = sorted(citations.difference(slice_ids))
    if unknown:
        raise ValueError(
            f"{fixture_id} relationship cites unknown harvested slices: {unknown}."
        )
    return bool(citations.intersection(bindings[source_id])) and bool(
        citations.intersection(bindings[target_id])
    )
