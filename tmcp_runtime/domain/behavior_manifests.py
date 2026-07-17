"""Canonical, content-addressed indexes for lazy behavior hydration."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .behavior_manifest_primitives import (
    BEHAVIOR_HYDRATION_SCHEMA,
    BEHAVIOR_MANIFEST_INDEX_SCHEMA,
    BEHAVIOR_MANIFEST_SCHEMA,
    DEFAULT_METADATA_LIMITS,
    REFERENCE_POLICY,
    _DIGEST,
    _candidates,
    _hash,
    _items,
    _limits,
    _manifest_identity,
    _mapping,
    _source,
    _strings,
)
from .behavior_manifest_hydration import (
    hydrate_behavior_blocks,
    select_hydrated_behavior_blocks,
)
from .harvest_nodes import estimate_tokens


def behavior_metadata_from_node(
    source_node: Mapping[str, Any], *, metadata_limits: Mapping[str, int] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project bounded routing metadata without granting references authority."""

    routing = _mapping(source_node.get("routing_metadata"))
    labels = [
        str(item.get("id") or "")
        for item in _items(source_node.get("guidance_labels"))
        if isinstance(item, Mapping)
    ]
    candidates = {
        "triggers": _strings(routing.get("commands"))
        + _strings(routing.get("trigger_phrases"))
        + _strings(source_node.get("use_when"))
        + _strings(source_node.get("objective_patterns")),
        "facets": _strings(source_node.get("behavior_atoms"))
        + _strings(labels)
        + _strings(source_node.get("route_affinity")),
        "phases": _strings(routing.get("phase_hints"))
        + _strings(list(_mapping(source_node.get("phase_transitions")))),
        "gates": _strings(routing.get("setup_blockers"))
        + _strings(routing.get("stop_conditions"))
        + _strings(routing.get("verification_gates"))
        + _strings(source_node.get("verification_expectations")),
        "inputs": _strings(source_node.get("inputs"))
        + _strings(source_node.get("minimum_spec_fields")),
        "outputs": _strings(source_node.get("outputs"))
        + _strings(routing.get("output_contract")),
        "references": _strings(routing.get("required_reads"))
        + _strings(routing.get("declared_loads"))
        + _strings(source_node.get("source_references"))
        + _strings(source_node.get("loads")),
    }
    limits = _limits(metadata_limits)
    normalized = {field: sorted(set(values)) for field, values in candidates.items()}
    metadata = {field: values[: limits[field]] for field, values in normalized.items()}
    metadata["reference_policy"] = REFERENCE_POLICY
    return metadata, {
        "limits": limits,
        "truncated": {
            field: len(values) > limits[field] for field, values in normalized.items()
        },
        "available_counts": {
            field: len(values) for field, values in normalized.items()
        },
    }


def markdown_behavior_chunks(text: str, max_chars: int) -> list[tuple[int, int, str]]:
    """Split Markdown at behavior headings before applying a hydration budget."""

    if not text:
        return [(0, 0, "")]
    chunks: list[tuple[int, int, str]] = []
    section_starts = [0]
    section_starts.extend(
        match.start()
        for match in re.finditer(r"(?m)^#{1,6}\s+\S.*$", text)
        if match.start() > 0
    )
    section_starts.append(len(text))
    for section_start, section_end in zip(section_starts, section_starts[1:]):
        start = section_start
        while start < section_end:
            end = min(section_end, start + max_chars)
            if end < section_end:
                newline = text.rfind("\n", start, end)
                if newline > start + max_chars // 2:
                    end = newline
            content = text[start:end].strip()
            if content:
                chunks.append((start, end, content))
            start = max(end, start + 1)
            while start < section_end and text[start] == "\n":
                start += 1
    return chunks


def behavior_block_descriptors(
    source_node: Mapping[str, Any],
    source_slices: Sequence[Mapping[str, Any]] = (),
    *,
    max_blocks: int = 24,
    max_block_facets: int = 8,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Describe hydratable blocks without retaining their content."""

    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (max_blocks, max_block_facets)
    ):
        raise ValueError("Behavior block limits must be nonnegative integers.")
    candidates = _candidates(source_node, source_slices)
    source_id = _source(source_node)["source_node_id"]
    blocks = []
    for item in candidates[:max_blocks]:
        identity = {
            key: item[key]
            for key in (
                "source_kind",
                "source_locator",
                "block_digest",
                "char_start",
                "char_end",
            )
        }
        blocks.append(
            {
                "block_id": f"behavior-block-{_hash([source_id, identity])[:20]}",
                "source_node_id": source_id,
                **identity,
                "token_estimate": item["token_estimate"],
                "facets": item["facets"][:max_block_facets],
                "phases": item["phases"][:max_block_facets],
                "metadata_truncated": len(item["facets"]) > max_block_facets
                or len(item["phases"]) > max_block_facets,
            }
        )
    return blocks, {
        "max_blocks": max_blocks,
        "available_block_count": len(candidates),
        "indexed_block_count": len(blocks),
        "blocks_truncated": len(candidates) > max_blocks,
        "max_block_facets": max_block_facets,
    }


def build_behavior_manifest(
    source_node: Mapping[str, Any],
    source_slices: Sequence[Mapping[str, Any]] = (),
    *,
    metadata_limits: Mapping[str, int] | None = None,
    max_blocks: int = 24,
    max_block_facets: int = 8,
) -> dict[str, Any]:
    """Build one deterministic always-on behavior index."""

    metadata, metadata_bounds = behavior_metadata_from_node(
        source_node, metadata_limits=metadata_limits
    )
    blocks, block_bounds = behavior_block_descriptors(
        source_node,
        source_slices,
        max_blocks=max_blocks,
        max_block_facets=max_block_facets,
    )
    source = _source(source_node)
    core = {
        "schema": BEHAVIOR_MANIFEST_SCHEMA,
        "source": source,
        "behavior_metadata": metadata,
        "behavior_blocks": blocks,
        "bounds": {"metadata": metadata_bounds, "blocks": block_bounds},
    }
    digest = _hash(_manifest_identity(source, metadata, blocks, core["bounds"]))
    manifest = {
        **core,
        "manifest_id": f"behavior-manifest-{digest[:20]}",
        "manifest_digest": digest,
    }
    source_tokens = source_node.get("token_estimate")
    if isinstance(source_tokens, bool) or not isinstance(source_tokens, int):
        source_tokens = sum(item["token_estimate"] for item in blocks)
    manifest["cost_telemetry"] = {
        "always_on_index_tokens": estimate_tokens(
            json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        ),
        "hydration_tokens": sum(item["token_estimate"] for item in blocks),
        "source_tokens": max(0, source_tokens),
        "indexed_block_count": len(blocks),
        "cost_policy": "canonical_json_chars_divided_by_four",
    }
    return manifest


def build_behavior_manifest_index(
    source_nodes: Sequence[Mapping[str, Any]],
    source_slices: Sequence[Mapping[str, Any]] = (),
    **options: Any,
) -> dict[str, Any]:
    """Build a canonical manifest set with aggregate cost telemetry."""

    manifests = sorted(
        [
            build_behavior_manifest(node, source_slices, **options)
            for node in source_nodes
        ],
        key=lambda item: (item["source"]["source_node_id"], item["manifest_digest"]),
    )
    digest = _hash(sorted(item["manifest_digest"] for item in manifests))
    index = {
        "schema": BEHAVIOR_MANIFEST_INDEX_SCHEMA,
        "index_id": f"behavior-index-{digest[:20]}",
        "index_digest": digest,
        "manifests": manifests,
    }
    index["cost_telemetry"] = {
        "manifest_count": len(manifests),
        "behavior_block_count": sum(len(item["behavior_blocks"]) for item in manifests),
        "always_on_index_tokens": estimate_tokens(
            json.dumps(index, sort_keys=True, separators=(",", ":"))
        ),
        "manifest_core_tokens": sum(
            item["cost_telemetry"]["always_on_index_tokens"] for item in manifests
        ),
        "hydration_tokens": sum(
            item["cost_telemetry"]["hydration_tokens"] for item in manifests
        ),
        "source_tokens": sum(
            item["cost_telemetry"]["source_tokens"] for item in manifests
        ),
        "cost_policy": "canonical_json_chars_divided_by_four",
    }
    return index


def compact_behavior_manifest_index(full_index: Mapping[str, Any]) -> dict[str, Any]:
    """Project the low-context index that accompanies hydrated source blocks."""

    manifests = _items(full_index.get("manifests"))
    summaries = [
        {
            "source_node_id": str(_mapping(item.get("source")).get("source_node_id")),
            "behavior_block_count": len(_items(item.get("behavior_blocks"))),
        }
        for item in manifests
        if isinstance(item, Mapping)
    ]
    compact = {
        "schema": str(full_index.get("schema") or BEHAVIOR_MANIFEST_INDEX_SCHEMA),
        "index_id": str(full_index.get("index_id") or ""),
        "index_digest": str(full_index.get("index_digest") or ""),
        "manifest_summaries": summaries,
    }
    compact["cost_telemetry"] = {}
    compact["cost_telemetry"]["always_on_index_tokens"] = estimate_tokens(
        json.dumps(compact, sort_keys=True, separators=(",", ":"))
    )
    return compact
