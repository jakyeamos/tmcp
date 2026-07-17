"""Canonical, content-addressed indexes for lazy behavior hydration."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .harvest_nodes import content_digest_for, estimate_tokens, node_source_role, normalized_source_content


BEHAVIOR_MANIFEST_SCHEMA = "tmcp-behavior-manifest-v0.1"
BEHAVIOR_MANIFEST_INDEX_SCHEMA = "tmcp-behavior-manifest-index-v0.1"
BEHAVIOR_HYDRATION_SCHEMA = "tmcp-behavior-hydration-v0.1"
REFERENCE_POLICY = "advisory_only_never_activates_behavior"
DEFAULT_METADATA_LIMITS = {"triggers": 16, "facets": 16, "phases": 8, "gates": 16, "inputs": 12, "outputs": 12, "references": 16}
_DIGEST = re.compile(r"[a-f0-9]{64}")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    return sorted({normalized_source_content(str(item)) for item in value if normalized_source_content(str(item))})


def _hash(value: object) -> str:
    payload = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(str(payload).encode()).hexdigest()


def _source(node: Mapping[str, Any]) -> dict[str, str]:
    signal = normalized_source_content(str(node.get("signal_excerpt") or node.get("excerpt") or ""))
    digest = str(node.get("content_digest") or "").strip().lower()
    if not _DIGEST.fullmatch(digest):
        digest = content_digest_for(signal)
    node_id = str(node.get("id") or f"source-{digest[:16]}").strip()
    return {
        "source_node_id": node_id,
        "skill_id": str(node.get("skill_id") or node.get("seed_id") or node_id).strip(),
        "source_role": node_source_role(dict(node)),
        "source_type": str(node.get("source_type") or "unknown").strip(),
        "content_digest": digest,
        "relative_path": str(node.get("relative_path") or node.get("path") or "").strip(),
    }


def _limits(overrides: Mapping[str, int] | None) -> dict[str, int]:
    limits = dict(DEFAULT_METADATA_LIMITS)
    for field, limit in dict(overrides or {}).items():
        if field not in limits:
            raise ValueError(f"Unknown behavior manifest metadata field: {field}")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError(f"Behavior metadata limit for {field} must be nonnegative.")
        limits[field] = limit
    return limits


def behavior_metadata_from_node(source_node: Mapping[str, Any], *, metadata_limits: Mapping[str, int] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project bounded routing metadata without granting references authority."""

    routing = _mapping(source_node.get("routing_metadata"))
    labels = [str(item.get("id") or "") for item in _items(source_node.get("guidance_labels")) if isinstance(item, Mapping)]
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
        "available_counts": {field: len(values) for field, values in normalized.items()},
    }


def _candidates(node: Mapping[str, Any], slices: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    source = _source(node)
    source_id = source["source_node_id"]
    result: list[dict[str, Any]] = []
    for item in slices:
        if str(item.get("source_node_id") or "") != source_id:
            continue
        declared_source_digest = str(item.get("source_digest") or "").strip().lower()
        if _DIGEST.fullmatch(declared_source_digest) and declared_source_digest != source[
            "content_digest"
        ]:
            raise ValueError(f"Source slice digest does not match source: {item.get('slice_id')}")
        content = normalized_source_content(str(item.get("content") or ""))
        if not content:
            continue
        digest = content_digest_for(content)
        declared = str(item.get("slice_digest") or "").strip().lower()
        if _DIGEST.fullmatch(declared) and declared != digest:
            raise ValueError(f"Source slice digest does not match: {item.get('slice_id')}")
        start = int(item.get("char_start") or 0)
        result.append(
            {
                "source_kind": "source_slice",
                "source_locator": str(item.get("slice_id") or f"slice-{digest[:20]}"),
                "block_digest": digest,
                "char_start": start,
                "char_end": int(item.get("char_end") or start + len(content)),
                "token_estimate": max(1, int(item.get("token_estimate") or estimate_tokens(content))),
                "facets": _strings(item.get("behavior_atoms")),
                "phases": _strings(item.get("phase_hints")),
                "content": content,
            }
        )
    if not result:
        content = normalized_source_content(str(node.get("signal_excerpt") or node.get("excerpt") or ""))
        if content:
            result.append(
                {
                    "source_kind": "node_signal",
                    "source_locator": "signal_excerpt",
                    "block_digest": content_digest_for(content),
                    "char_start": 0,
                    "char_end": len(content),
                    "token_estimate": estimate_tokens(content),
                    "facets": _strings(node.get("behavior_atoms")),
                    "phases": _strings(_mapping(node.get("routing_metadata")).get("phase_hints")),
                    "content": content,
                }
            )
    return sorted(result, key=lambda item: (item["char_start"], item["char_end"], item["source_locator"]))


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

    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (max_blocks, max_block_facets)):
        raise ValueError("Behavior block limits must be nonnegative integers.")
    candidates = _candidates(source_node, source_slices)
    source_id = _source(source_node)["source_node_id"]
    blocks = []
    for item in candidates[:max_blocks]:
        identity = {key: item[key] for key in ("source_kind", "source_locator", "block_digest", "char_start", "char_end")}
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


def _manifest_identity(
    source: Mapping[str, Any],
    metadata: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
    bounds: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": BEHAVIOR_MANIFEST_SCHEMA,
        "source": {
            key: str(source.get(key) or "")
            for key in ("source_role", "source_type", "content_digest")
        },
        "behavior_metadata": dict(metadata),
        "behavior_blocks": [
            {
                key: block.get(key)
                for key in (
                    "source_kind",
                    "block_digest",
                    "char_start",
                    "char_end",
                    "token_estimate",
                    "facets",
                    "phases",
                    "metadata_truncated",
                )
            }
            for block in blocks
        ],
        "bounds": dict(bounds),
    }


def build_behavior_manifest(source_node: Mapping[str, Any], source_slices: Sequence[Mapping[str, Any]] = (), *, metadata_limits: Mapping[str, int] | None = None, max_blocks: int = 24, max_block_facets: int = 8) -> dict[str, Any]:
    """Build one deterministic always-on behavior index."""

    metadata, metadata_bounds = behavior_metadata_from_node(source_node, metadata_limits=metadata_limits)
    blocks, block_bounds = behavior_block_descriptors(
        source_node, source_slices, max_blocks=max_blocks, max_block_facets=max_block_facets
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
    manifest = {**core, "manifest_id": f"behavior-manifest-{digest[:20]}", "manifest_digest": digest}
    source_tokens = source_node.get("token_estimate")
    if isinstance(source_tokens, bool) or not isinstance(source_tokens, int):
        source_tokens = sum(item["token_estimate"] for item in blocks)
    manifest["cost_telemetry"] = {
        "always_on_index_tokens": estimate_tokens(json.dumps(manifest, sort_keys=True, separators=(",", ":"))),
        "hydration_tokens": sum(item["token_estimate"] for item in blocks),
        "source_tokens": max(0, source_tokens),
        "indexed_block_count": len(blocks),
        "cost_policy": "canonical_json_chars_divided_by_four",
    }
    return manifest


def build_behavior_manifest_index(source_nodes: Sequence[Mapping[str, Any]], source_slices: Sequence[Mapping[str, Any]] = (), **options: Any) -> dict[str, Any]:
    """Build a canonical manifest set with aggregate cost telemetry."""

    manifests = sorted(
        [build_behavior_manifest(node, source_slices, **options) for node in source_nodes],
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
        "always_on_index_tokens": estimate_tokens(json.dumps(index, sort_keys=True, separators=(",", ":"))),
        "manifest_core_tokens": sum(item["cost_telemetry"]["always_on_index_tokens"] for item in manifests),
        "hydration_tokens": sum(item["cost_telemetry"]["hydration_tokens"] for item in manifests),
        "source_tokens": sum(item["cost_telemetry"]["source_tokens"] for item in manifests),
        "cost_policy": "canonical_json_chars_divided_by_four",
    }
    return index


def compact_behavior_manifest_index(full_index: Mapping[str, Any]) -> dict[str, Any]:
    """Project the low-context index that accompanies hydrated source blocks."""

    manifests = _items(full_index.get("manifests"))
    summaries = [
        {
            "source_node_id": str(
                _mapping(item.get("source")).get("source_node_id")
            ),
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


def select_hydrated_behavior_blocks(
    candidates: Sequence[Mapping[str, Any]],
    *,
    max_slices: int,
    max_total_chars: int,
    max_hydration_tokens: int,
    target_hydration_tokens: int,
    governing_source_count: int,
) -> dict[str, Any]:
    """Select bounded behavior blocks with explicit context-budget exceptions."""

    selected: list[dict[str, Any]] = []
    selected_slice_ids: set[str] = set()
    represented_governing_sources: set[str] = set()
    represented_active_sources: set[str] = set()
    represented_supporting_sources: set[str] = set()
    mandatory_context_overrides: list[str] = []
    minimum_active_context_override = ""
    total_chars = 0
    total_tokens = 0

    def fits(candidate: Mapping[str, Any], *, enforce_target: bool) -> bool:
        content_size = len(str(candidate.get("content") or ""))
        token_size = int(candidate.get("token_estimate") or 0)
        if (
            len(selected) >= max_slices
            or total_chars + content_size > max_total_chars
            or total_tokens + token_size > max_hydration_tokens
        ):
            return False
        return not (enforce_target and total_tokens + token_size > target_hydration_tokens)

    def select(candidate: Mapping[str, Any]) -> None:
        nonlocal total_chars, total_tokens
        selected.append(dict(candidate))
        selected_slice_ids.add(str(candidate.get("slice_id") or ""))
        total_chars += len(str(candidate.get("content") or ""))
        total_tokens += int(candidate.get("token_estimate") or 0)

    for candidate in candidates:
        source_node_id = str(candidate.get("source_node_id") or "")
        if (
            str(candidate.get("source_role") or "") != "governing_instruction"
            or source_node_id in represented_governing_sources
            or not fits(candidate, enforce_target=False)
        ):
            continue
        if not fits(candidate, enforce_target=True):
            mandatory_context_overrides.append(source_node_id)
        select(candidate)
        represented_governing_sources.add(source_node_id)
    if len(represented_governing_sources) != governing_source_count:
        raise ValueError(
            "Composition token limit cannot include every governing source with the behavior manifest index."
        )

    for candidate in candidates:
        source_node_id = str(candidate.get("source_node_id") or "")
        if (
            str(candidate.get("source_role") or "") != "active_skill"
            or source_node_id in represented_active_sources
            or not fits(candidate, enforce_target=True)
        ):
            continue
        select(candidate)
        represented_active_sources.add(source_node_id)
    if not represented_active_sources:
        for candidate in candidates:
            source_node_id = str(candidate.get("source_node_id") or "")
            if (
                str(candidate.get("source_role") or "") != "active_skill"
                or not fits(candidate, enforce_target=False)
            ):
                continue
            select(candidate)
            represented_active_sources.add(source_node_id)
            minimum_active_context_override = source_node_id
            break

    for candidate in candidates:
        source_node_id = str(candidate.get("source_node_id") or "")
        if (
            str(candidate.get("source_role") or "") != "supporting_reference"
            or source_node_id in represented_supporting_sources
            or not fits(candidate, enforce_target=True)
        ):
            continue
        select(candidate)
        represented_supporting_sources.add(source_node_id)
    for candidate in candidates:
        if str(candidate.get("slice_id") or "") in selected_slice_ids or not fits(
            candidate,
            enforce_target=True,
        ):
            continue
        select(candidate)
    return {
        "selected": selected,
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "mandatory_context_overrides": mandatory_context_overrides,
        "minimum_active_context_override": minimum_active_context_override,
    }


def hydrate_behavior_blocks(manifest: Mapping[str, Any], *, source_node: Mapping[str, Any], source_slices: Sequence[Mapping[str, Any]] = (), block_ids: Sequence[str] | None = None, max_tokens: int = 3000) -> dict[str, Any]:
    """Resolve selected content and fail closed on provenance mismatch."""

    if max_tokens < 1 or str(manifest.get("schema") or "") != BEHAVIOR_MANIFEST_SCHEMA:
        raise ValueError("Behavior hydration requires a supported manifest and positive token limit.")
    if _mapping(manifest.get("source")) != _source(source_node):
        raise ValueError("Hydration source does not match the behavior manifest.")
    descriptors = [item for item in _items(manifest.get("behavior_blocks")) if isinstance(item, Mapping)]
    expected_manifest_digest = _hash(
        _manifest_identity(
            _source(source_node),
            _mapping(manifest.get("behavior_metadata")),
            descriptors,
            _mapping(manifest.get("bounds")),
        )
    )
    if (
        str(manifest.get("manifest_digest") or "") != expected_manifest_digest
        or str(manifest.get("manifest_id") or "")
        != f"behavior-manifest-{expected_manifest_digest[:20]}"
    ):
        raise ValueError("Behavior manifest digest does not match its provenance.")
    by_id = {str(item.get("block_id") or ""): item for item in descriptors}
    requested_ids = sorted(set(block_ids)) if block_ids is not None else list(by_id)
    unknown = sorted(set(requested_ids) - set(by_id))
    if unknown:
        raise ValueError(f"Unknown behavior block ids: {', '.join(unknown)}")
    content_by_locator = {
        (item["source_kind"], item["source_locator"]): item
        for item in _candidates(source_node, source_slices)
    }
    hydrated, missing, skipped, tokens = [], [], [], 0
    for descriptor in descriptors:
        block_id = str(descriptor.get("block_id") or "")
        if block_id not in requested_ids:
            continue
        candidate = content_by_locator.get((descriptor["source_kind"], descriptor["source_locator"]))
        if candidate is None:
            missing.append(block_id)
            continue
        if descriptor["block_digest"] != candidate["block_digest"]:
            raise ValueError(f"Behavior block digest mismatch: {block_id}")
        block_tokens = int(descriptor["token_estimate"])
        if tokens + block_tokens > max_tokens:
            skipped.append(block_id)
            continue
        hydrated.append({key: descriptor[key] for key in ("block_id", "block_digest", "source_kind", "source_locator", "token_estimate")} | {"content": candidate["content"]})
        tokens += block_tokens
    return {
        "schema": BEHAVIOR_HYDRATION_SCHEMA,
        "manifest_id": manifest.get("manifest_id"),
        "manifest_digest": manifest.get("manifest_digest"),
        "blocks": hydrated,
        "cost_telemetry": {
            "requested_block_count": len(requested_ids),
            "hydrated_block_count": len(hydrated),
            "hydrated_tokens": tokens,
            "max_tokens": max_tokens,
            "missing_block_ids": missing,
            "budget_skipped_block_ids": skipped,
            "truncated": bool(missing or skipped),
        },
    }
