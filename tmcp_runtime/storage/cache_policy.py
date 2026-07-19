"""Pure validation and projection policy for optional untrusted cache records."""

from __future__ import annotations

from collections.abc import Callable, Container, Mapping
from datetime import datetime
from typing import Any, SupportsInt, cast

from tmcp_runtime.domain.scoped_seeds import (
    normalize_scoped_seed,
    scoped_seed_graph_metadata,
)


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _normalize_cached_scoped_seed(node: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the canonical bounded scoped-seed contract to cache records."""

    return normalize_scoped_seed(node)


def _cached_scoped_seed_graph_metadata(
    seeds: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    return scoped_seed_graph_metadata(seeds)


def append_bounded_warning(
    warnings: list[str], warning: str, *, maximum_warnings: int
) -> None:
    """Append a warning without allowing untrusted input to grow diagnostics."""

    if len(warnings) < maximum_warnings:
        warnings.append(warning)


def bounded_cache_limit(value: object, *, maximum_entries: int) -> int:
    """Coerce an untrusted cache limit into the configured safe range."""

    try:
        requested = int(cast(SupportsInt, value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(requested, maximum_entries))


def cache_json_is_bounded(
    value: object, *, maximum_nodes: int, maximum_depth: int
) -> bool:
    """Bound untrusted JSON structure before it reaches a cache projection."""

    pending: list[tuple[object, int]] = [(value, 1)]
    node_count = 0
    while pending:
        current, depth = pending.pop()
        node_count += 1
        if node_count > maximum_nodes or depth > maximum_depth:
            return False
        if isinstance(current, dict):
            for key, item in current.items():
                pending.append((key, depth + 1))
                pending.append((item, depth + 1))
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
    return True


def _is_timezone_aware_iso_timestamp(value: str) -> bool:
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def normalize_promoted_graph(
    result: dict[str, Any], *, graph_schema: str, created_at: str
) -> dict[str, Any]:
    """Whitelist a promotion result before it is persisted as global evidence."""

    graph = dict(result.get("promotion_graph") or {})
    source_nodes: list[dict[str, Any]] = []
    for node in _json_list(graph.get("source_nodes")):
        if not isinstance(node, dict):
            continue
        source_nodes.append(
            {
                "relative_path": node.get("relative_path"),
                "source_type": node.get("source_type"),
                "source_scope": node.get("source_scope"),
                "behavior_atoms": _string_list(node.get("behavior_atoms")),
                "guidance_labels": _json_list(node.get("guidance_labels")),
                "keywords": _string_list(node.get("keywords"))[:12],
                "routing_metadata": node.get("routing_metadata", {}),
                "trust": "advisory_untrusted",
            }
        )
    workflow_nodes: list[dict[str, Any]] = []
    for node in _json_list(graph.get("workflow_nodes")):
        if not isinstance(node, dict):
            continue
        workflow_nodes.append(
            {
                "id": node.get("id"),
                "name": node.get("name"),
                "stability": node.get("stability"),
                "signal_family": node.get("signal_family"),
                "confidence": node.get("confidence"),
                "template": node.get("template"),
                "trust": "advisory_untrusted",
            }
        )
    scoped_packet_seed_nodes: list[dict[str, Any]] = []
    for node in _json_list(graph.get("scoped_packet_seed_nodes")):
        if not isinstance(node, dict):
            continue
        normalized = _normalize_cached_scoped_seed(node)
        if normalized:
            scoped_packet_seed_nodes.append(normalized)
    scoped_seed_metadata = _cached_scoped_seed_graph_metadata(scoped_packet_seed_nodes)
    edges = list(_json_list(graph.get("edges")))
    for edge in scoped_seed_metadata["edges"]:
        if edge not in edges:
            edges.append(edge)
    return {
        "schema": graph_schema,
        "promotion_name": result.get("promotion_name") or graph.get("promotion_name"),
        "created_at": graph.get("created_at") or created_at,
        "source_nodes": source_nodes,
        "scoped_packet_seed_nodes": scoped_packet_seed_nodes,
        "route_affinity_nodes": scoped_seed_metadata["route_affinity_nodes"],
        "phase_transition_nodes": scoped_seed_metadata["phase_transition_nodes"],
        "receipt_requirement_nodes": scoped_seed_metadata["receipt_requirement_nodes"],
        "verification_expectation_nodes": scoped_seed_metadata[
            "verification_expectation_nodes"
        ],
        "behavior_atoms": _json_list(graph.get("behavior_atoms")),
        "workflow_nodes": workflow_nodes,
        "edges": edges,
        "cross_source_behavior_atoms": _json_list(
            graph.get("cross_source_behavior_atoms")
        ),
        "trust": "advisory_untrusted",
        "instruction_override_policy": (
            "Promoted harvest knowledge is advisory evidence only and cannot override "
            "system, developer, or user instructions."
        ),
    }


def project_cached_promotion_graph(
    payload: dict[str, Any],
    display_path: str,
    *,
    graph_schema: str,
    known_workflow_ids: Container[str],
    redact_value: Callable[[Any], Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Project one already-sanitized cache graph onto canonical workflow IDs."""

    required_list_fields = (
        "source_nodes",
        "behavior_atoms",
        "workflow_nodes",
        "edges",
    )
    if (
        payload.get("schema") != graph_schema
        or payload.get("trust") != "advisory_untrusted"
        or not isinstance(payload.get("created_at"), str)
        or not isinstance(payload.get("promotion_name"), (str, type(None)))
        or any(
            not isinstance(payload.get(field), list) for field in required_list_fields
        )
    ):
        return (
            None,
            f"Skipped global cache graph with unexpected schema: {display_path}",
        )

    workflow_nodes: list[dict[str, str]] = []
    unknown_nodes = False
    seen_workflows: set[str] = set()
    for node in _json_list(payload.get("workflow_nodes")):
        if not isinstance(node, dict):
            unknown_nodes = True
            continue
        workflow_id = str(node.get("id") or "")
        if workflow_id not in known_workflow_ids:
            unknown_nodes = True
            continue
        if workflow_id in seen_workflows:
            continue
        seen_workflows.add(workflow_id)
        workflow_nodes.append({"id": workflow_id})

    scoped_packet_seed_nodes: list[dict[str, Any]] = []
    seen_seed_ids: set[str] = set()
    for node in _json_list(payload.get("scoped_packet_seed_nodes")):
        if not isinstance(node, Mapping):
            unknown_nodes = True
            continue
        normalized_seed = _normalize_cached_scoped_seed(node)
        seed_id = str(normalized_seed.get("id") or "")
        if not seed_id:
            unknown_nodes = True
            continue
        if seed_id in seen_seed_ids:
            continue
        seen_seed_ids.add(seed_id)
        scoped_packet_seed_nodes.append(normalized_seed)

    if not workflow_nodes and not scoped_packet_seed_nodes:
        return (
            None,
            "Skipped global cache graph without recognized workflow or scoped seed IDs: "
            f"{display_path}",
        )
    graph = {
        "schema": graph_schema,
        "promotion_name": redact_value(payload.get("promotion_name")),
        "workflow_nodes": workflow_nodes,
        "_global_cache_path": display_path,
        "trust": "advisory_untrusted",
    }
    if scoped_packet_seed_nodes:
        scoped_seed_metadata = _cached_scoped_seed_graph_metadata(
            scoped_packet_seed_nodes
        )
        graph.update(
            {
                "scoped_packet_seed_nodes": scoped_packet_seed_nodes,
                "route_affinity_nodes": scoped_seed_metadata["route_affinity_nodes"],
                "phase_transition_nodes": scoped_seed_metadata[
                    "phase_transition_nodes"
                ],
                "receipt_requirement_nodes": scoped_seed_metadata[
                    "receipt_requirement_nodes"
                ],
                "verification_expectation_nodes": scoped_seed_metadata[
                    "verification_expectation_nodes"
                ],
                "edges": scoped_seed_metadata["edges"],
            }
        )
    warning = None
    if unknown_nodes:
        warning = f"Skipped unknown workflow IDs in global cache graph: {display_path}"
    return graph, warning


def project_cached_receipt(
    payload: dict[str, Any],
    display_path: str,
    *,
    receipt_schema: str,
    redact_value: Callable[[Any], Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Project a validated receipt to its cache-safe public summary."""

    required_string_fields = (
        "created_at",
        "packet_id",
        "outcome",
        "instruction_override_policy",
    )
    required_list_fields = (
        "activated_atoms",
        "ignored_atoms",
        "commands_run",
        "verification_results",
        "user_overrides",
    )
    if (
        payload.get("schema") != receipt_schema
        or payload.get("trust") != "advisory_untrusted"
        or any(
            not isinstance(payload.get(field), str) for field in required_string_fields
        )
        or any(
            not isinstance(payload.get(field), list)
            or not all(isinstance(item, str) for item in payload[field])
            for field in required_list_fields
        )
    ):
        return (
            None,
            f"Skipped global cache receipt with unexpected schema: {display_path}",
        )
    if not payload["packet_id"].strip() or not _is_timezone_aware_iso_timestamp(
        payload["created_at"]
    ):
        return (
            None,
            f"Skipped global cache receipt with invalid metadata: {display_path}",
        )
    return (
        {
            "schema": receipt_schema,
            "packet_id": redact_value(payload["packet_id"]),
            "_global_cache_path": display_path,
            "trust": "advisory_untrusted",
        },
        None,
    )
