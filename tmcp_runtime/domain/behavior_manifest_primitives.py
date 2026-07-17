"""Shared provenance and identity primitives for behavior manifests."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .harvest_nodes import (
    content_digest_for,
    estimate_tokens,
    node_source_role,
    normalized_source_content,
)


BEHAVIOR_MANIFEST_SCHEMA = "tmcp-behavior-manifest-v0.1"
BEHAVIOR_MANIFEST_INDEX_SCHEMA = "tmcp-behavior-manifest-index-v0.1"
BEHAVIOR_HYDRATION_SCHEMA = "tmcp-behavior-hydration-v0.1"
REFERENCE_POLICY = "advisory_only_never_activates_behavior"
DEFAULT_METADATA_LIMITS = {
    "triggers": 16,
    "facets": 16,
    "phases": 8,
    "gates": 16,
    "inputs": 12,
    "outputs": 12,
    "references": 16,
}
_DIGEST = re.compile(r"[a-f0-9]{64}")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    return sorted(
        {
            normalized_source_content(str(item))
            for item in value
            if normalized_source_content(str(item))
        }
    )


def _hash(value: object) -> str:
    payload = (
        value
        if isinstance(value, str)
        else json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    )
    return hashlib.sha256(str(payload).encode()).hexdigest()


def _source(node: Mapping[str, Any]) -> dict[str, str]:
    signal = normalized_source_content(
        str(node.get("signal_excerpt") or node.get("excerpt") or "")
    )
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
        "relative_path": str(
            node.get("relative_path") or node.get("path") or ""
        ).strip(),
    }


def _limits(overrides: Mapping[str, int] | None) -> dict[str, int]:
    limits = dict(DEFAULT_METADATA_LIMITS)
    for field, limit in dict(overrides or {}).items():
        if field not in limits:
            raise ValueError(f"Unknown behavior manifest metadata field: {field}")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError(
                f"Behavior metadata limit for {field} must be nonnegative."
            )
        limits[field] = limit
    return limits


def _candidates(
    node: Mapping[str, Any], slices: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    source = _source(node)
    source_id = source["source_node_id"]
    result: list[dict[str, Any]] = []
    for item in slices:
        if str(item.get("source_node_id") or "") != source_id:
            continue
        declared_source_digest = str(item.get("source_digest") or "").strip().lower()
        if (
            _DIGEST.fullmatch(declared_source_digest)
            and declared_source_digest != source["content_digest"]
        ):
            raise ValueError(
                f"Source slice digest does not match source: {item.get('slice_id')}"
            )
        content = normalized_source_content(str(item.get("content") or ""))
        if not content:
            continue
        digest = content_digest_for(content)
        declared = str(item.get("slice_digest") or "").strip().lower()
        if _DIGEST.fullmatch(declared) and declared != digest:
            raise ValueError(
                f"Source slice digest does not match: {item.get('slice_id')}"
            )
        start = int(item.get("char_start") or 0)
        result.append(
            {
                "source_kind": "source_slice",
                "source_locator": str(item.get("slice_id") or f"slice-{digest[:20]}"),
                "block_digest": digest,
                "char_start": start,
                "char_end": int(item.get("char_end") or start + len(content)),
                "token_estimate": max(
                    1, int(item.get("token_estimate") or estimate_tokens(content))
                ),
                "facets": _strings(item.get("behavior_atoms")),
                "phases": _strings(item.get("phase_hints")),
                "content": content,
            }
        )
    if not result:
        content = normalized_source_content(
            str(node.get("signal_excerpt") or node.get("excerpt") or "")
        )
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
                    "phases": _strings(
                        _mapping(node.get("routing_metadata")).get("phase_hints")
                    ),
                    "content": content,
                }
            )
    return sorted(
        result,
        key=lambda item: (item["char_start"], item["char_end"], item["source_locator"]),
    )


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
