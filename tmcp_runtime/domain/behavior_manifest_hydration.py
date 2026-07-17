"""Bounded content hydration for behavior manifests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .behavior_manifest_primitives import (
    BEHAVIOR_HYDRATION_SCHEMA,
    BEHAVIOR_MANIFEST_SCHEMA,
    _candidates,
    _hash,
    _items,
    _manifest_identity,
    _mapping,
    _source,
)


def select_hydrated_behavior_blocks(
    candidates: Sequence[Mapping[str, Any]],
    *,
    max_slices: int,
    max_total_chars: int,
    max_hydration_tokens: int,
    target_hydration_tokens: int,
    governing_source_count: int,
    include_all_active_source_slices: bool = False,
) -> dict[str, Any]:
    """Select bounded behavior blocks with explicit context-budget exceptions.

    ``include_all_active_source_slices`` is an opt-in semantic-evidence mode.
    It still honors the hard slice, character, and token ceilings, but ensures a
    host can cite one ranked slice for every active source.  It deliberately
    does not change the default low-context hydration policy.
    """

    selected: list[dict[str, Any]] = []
    selected_slice_ids: set[str] = set()
    represented_governing_sources: set[str] = set()
    represented_active_sources: set[str] = set()
    represented_supporting_sources: set[str] = set()
    mandatory_context_overrides: list[str] = []
    minimum_active_context_override = ""
    required_active_context_overrides: list[str] = []
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
        return not (
            enforce_target and total_tokens + token_size > target_hydration_tokens
        )

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
    if include_all_active_source_slices:
        required_active_source_ids = {
            str(candidate.get("source_node_id") or "")
            for candidate in candidates
            if str(candidate.get("source_role") or "") == "active_skill"
        }
        for candidate in candidates:
            source_node_id = str(candidate.get("source_node_id") or "")
            if (
                str(candidate.get("source_role") or "") != "active_skill"
                or source_node_id in represented_active_sources
                or not fits(candidate, enforce_target=False)
            ):
                continue
            if not fits(candidate, enforce_target=True):
                required_active_context_overrides.append(source_node_id)
            select(candidate)
            represented_active_sources.add(source_node_id)
        missing_active_source_ids = sorted(
            required_active_source_ids.difference(represented_active_sources)
        )
        if missing_active_source_ids:
            raise ValueError(
                "Composition limits cannot include every active source for "
                "semantic proposal evidence."
            )
    if not represented_active_sources:
        for candidate in candidates:
            source_node_id = str(candidate.get("source_node_id") or "")
            if str(candidate.get("source_role") or "") != "active_skill" or not fits(
                candidate, enforce_target=False
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
        "required_active_context_overrides": required_active_context_overrides,
        "represented_active_source_ids": sorted(represented_active_sources),
    }


def hydrate_behavior_blocks(
    manifest: Mapping[str, Any],
    *,
    source_node: Mapping[str, Any],
    source_slices: Sequence[Mapping[str, Any]] = (),
    block_ids: Sequence[str] | None = None,
    max_tokens: int = 3000,
) -> dict[str, Any]:
    """Resolve selected content and fail closed on provenance mismatch."""

    if max_tokens < 1 or str(manifest.get("schema") or "") != BEHAVIOR_MANIFEST_SCHEMA:
        raise ValueError(
            "Behavior hydration requires a supported manifest and positive token limit."
        )
    if _mapping(manifest.get("source")) != _source(source_node):
        raise ValueError("Hydration source does not match the behavior manifest.")
    descriptors = [
        item
        for item in _items(manifest.get("behavior_blocks"))
        if isinstance(item, Mapping)
    ]
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
        candidate = content_by_locator.get(
            (descriptor["source_kind"], descriptor["source_locator"])
        )
        if candidate is None:
            missing.append(block_id)
            continue
        if descriptor["block_digest"] != candidate["block_digest"]:
            raise ValueError(f"Behavior block digest mismatch: {block_id}")
        block_tokens = int(descriptor["token_estimate"])
        if tokens + block_tokens > max_tokens:
            skipped.append(block_id)
            continue
        hydrated.append(
            {
                key: descriptor[key]
                for key in (
                    "block_id",
                    "block_digest",
                    "source_kind",
                    "source_locator",
                    "token_estimate",
                )
            }
            | {"content": candidate["content"]}
        )
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
