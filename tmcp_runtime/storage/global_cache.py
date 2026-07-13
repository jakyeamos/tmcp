"""Bounded, redacted, read-only ingestion of advisory global-cache records."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Container
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tmcp_runtime.domain.composition import normalize_cache_policy
from tmcp_runtime.safety import (
    HarvestCandidate,
    collect_harvest_roots,
    iter_harvest_candidates,
    redact_json_value,
    redact_path,
    read_harvest_text,
)
from tmcp_runtime.storage.cache_policy import (
    append_bounded_warning,
    bounded_cache_limit,
    cache_json_is_bounded,
    project_cached_promotion_graph,
    project_cached_receipt,
)
from tmcp_runtime.storage.migrations import migrate_legacy_promotion_summary


MAX_GLOBAL_CACHE_CANDIDATES = 64
MAX_GLOBAL_CACHE_SCAN_ENTRIES = 256
MAX_GLOBAL_CACHE_ENTRIES = 32
MAX_GLOBAL_CACHE_ENTRY_BYTES = 262_144
MAX_GLOBAL_CACHE_JSON_DEPTH = 32
MAX_GLOBAL_CACHE_JSON_NODES = 2_048
MAX_GLOBAL_CACHE_WARNINGS = 12


@dataclass(frozen=True)
class GlobalCacheSnapshot:
    """Redacted, schema-projected advisory records from explicit cache opt-in."""

    promoted_graphs: tuple[dict[str, Any], ...]
    receipts: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]


def _append_warning(warnings: list[str], warning: str) -> None:
    append_bounded_warning(
        warnings,
        warning,
        maximum_warnings=MAX_GLOBAL_CACHE_WARNINGS,
    )


def _bounded_entry_limit(value: object) -> int:
    return bounded_cache_limit(value, maximum_entries=MAX_GLOBAL_CACHE_ENTRIES)


def _json_is_bounded(value: object) -> bool:
    return cache_json_is_bounded(
        value,
        maximum_nodes=MAX_GLOBAL_CACHE_JSON_NODES,
        maximum_depth=MAX_GLOBAL_CACHE_JSON_DEPTH,
    )


def _safe_global_cache_entries(
    root: Path,
    *,
    filename: str | None,
    limit: int = MAX_GLOBAL_CACHE_ENTRIES,
) -> tuple[list[tuple[dict[str, Any], str, int]], list[str]]:
    try:
        root.lstat()
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], [
            "Could not inspect TMCP global cache root "
            f"{redact_path(root)}: {redact_path(str(exc))}"
        ]
    roots, root_warnings = collect_harvest_roots([root], follow_symlinks=False)
    warnings = list(root_warnings[:MAX_GLOBAL_CACHE_WARNINGS])
    if len(roots) != 1 or roots[0].kind != "directory":
        return [], warnings
    entry_limit = _bounded_entry_limit(limit)
    if entry_limit == 0:
        return [], warnings
    include_globs = [f"*/{filename}"] if filename is not None else ["*.json"]
    candidates, traversal_warnings = iter_harvest_candidates(
        roots,
        include_globs,
        [],
        set(),
        follow_symlinks=False,
        max_candidates=MAX_GLOBAL_CACHE_CANDIDATES,
        max_scan_entries=MAX_GLOBAL_CACHE_SCAN_ENTRIES,
        max_relative_depth=2,
    )
    for warning in traversal_warnings:
        _append_warning(warnings, warning)

    eligible_candidates: list[tuple[HarvestCandidate, os.stat_result]] = []
    matching_candidate_count = 0
    for candidate in candidates:
        parts = Path(candidate.relative_path).parts
        if len(parts) != 2 or (filename is not None and parts[-1] != filename):
            continue
        matching_candidate_count += 1
        if matching_candidate_count > MAX_GLOBAL_CACHE_CANDIDATES:
            _append_warning(
                warnings,
                "Global cache candidate limit reached; skipped additional entries.",
            )
            break
        try:
            metadata = candidate.resolved_path.lstat()
        except OSError as exc:
            _append_warning(
                warnings,
                "Could not inspect global cache entry "
                f"{candidate.display_path}: {redact_path(str(exc))}",
            )
            continue
        if not stat.S_ISREG(metadata.st_mode) or (metadata.st_dev, metadata.st_ino) != (
            candidate.device,
            candidate.inode,
        ):
            _append_warning(
                warnings,
                "Skipped global cache entry that changed before reading: "
                f"{candidate.display_path}",
            )
            continue
        if metadata.st_size > MAX_GLOBAL_CACHE_ENTRY_BYTES:
            _append_warning(
                warnings,
                "Skipped large global cache entry "
                f"{candidate.display_path} ({metadata.st_size} bytes > "
                f"{MAX_GLOBAL_CACHE_ENTRY_BYTES})",
            )
            continue
        eligible_candidates.append((candidate, metadata))

    eligible_candidates.sort(key=lambda item: item[1].st_mtime_ns, reverse=True)
    entries: list[tuple[dict[str, Any], str, int]] = []
    for candidate, _ in eligible_candidates[:entry_limit]:
        source, warning = read_harvest_text(
            candidate,
            MAX_GLOBAL_CACHE_ENTRY_BYTES,
            redact_sensitive=True,
        )
        if warning or source is None:
            _append_warning(
                warnings,
                warning
                or f"Skipped unreadable global cache entry {candidate.display_path}.",
            )
            continue
        try:
            payload = json.loads(source.text)
        except (json.JSONDecodeError, MemoryError, RecursionError, ValueError) as exc:
            _append_warning(
                warnings,
                "Skipped invalid global cache entry "
                f"{candidate.display_path}: {redact_path(str(exc))}",
            )
            continue
        if not isinstance(payload, dict):
            _append_warning(
                warnings,
                f"Skipped non-object global cache entry: {candidate.display_path}",
            )
            continue
        if not _json_is_bounded(payload):
            _append_warning(
                warnings,
                f"Skipped overly complex global cache entry: {candidate.display_path}",
            )
            continue
        try:
            metadata = candidate.resolved_path.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(metadata.st_mode) or (metadata.st_dev, metadata.st_ino) != (
            candidate.device,
            candidate.inode,
        ):
            _append_warning(
                warnings,
                "Skipped global cache entry that changed while reading: "
                f"{candidate.display_path}",
            )
            continue
        try:
            safe_payload, _ = redact_json_value(payload, enabled=True)
        except (MemoryError, RecursionError):
            _append_warning(
                warnings,
                "Skipped global cache entry that could not be redacted safely: "
                f"{candidate.display_path}",
            )
            continue
        if isinstance(safe_payload, dict):
            entries.append((safe_payload, candidate.display_path, metadata.st_mtime_ns))
    return entries, warnings[:MAX_GLOBAL_CACHE_WARNINGS]


def read_global_cache_snapshot(
    *,
    promoted_root: Path,
    receipts_root: Path,
    cache_policy: object,
    graph_schema: str,
    receipt_schema: str,
    known_workflow_ids: Container[str],
    receipt_limit: object = 25,
) -> GlobalCacheSnapshot:
    """Load only explicit-opt-in global cache records through safety boundaries."""

    if normalize_cache_policy(cache_policy) != "global":
        return GlobalCacheSnapshot((), (), ())

    graph_entries, graph_warnings = _safe_global_cache_entries(
        promoted_root,
        filename="promotion-graph.json",
    )
    legacy_graph_entries, legacy_graph_warnings = _safe_global_cache_entries(
        promoted_root,
        filename="promoted-harvest.json",
    )
    graph_warnings.extend(legacy_graph_warnings)
    current_graph_directories = {
        str(Path(display_path).parent)
        for _payload, display_path, _mtime in graph_entries
    }
    for payload, display_path, mtime in legacy_graph_entries:
        if str(Path(display_path).parent) in current_graph_directories:
            continue
        migrated = migrate_legacy_promotion_summary(
            payload,
            graph_schema=graph_schema,
        )
        if migrated is not None:
            graph_entries.append((migrated, display_path, mtime))
    promoted_graphs: list[dict[str, Any]] = []
    for payload, display_path, _ in graph_entries:
        graph, warning = project_cached_promotion_graph(
            payload,
            display_path,
            graph_schema=graph_schema,
            known_workflow_ids=known_workflow_ids,
            redact_value=lambda value: redact_json_value(value, enabled=True)[0],
        )
        if warning:
            _append_warning(graph_warnings, warning)
        if graph is not None:
            promoted_graphs.append(graph)

    receipts: list[dict[str, Any]] = []
    receipt_warnings: list[str] = []
    bounded_receipt_limit = _bounded_entry_limit(receipt_limit)
    if bounded_receipt_limit:
        receipt_entries, receipt_warnings = _safe_global_cache_entries(
            receipts_root,
            filename=None,
            limit=bounded_receipt_limit,
        )
        receipt_entries.sort(key=lambda item: item[2], reverse=True)
        for payload, display_path, _ in receipt_entries:
            receipt, warning = project_cached_receipt(
                payload,
                display_path,
                receipt_schema=receipt_schema,
                redact_value=lambda value: redact_json_value(value, enabled=True)[0],
            )
            if warning:
                _append_warning(receipt_warnings, warning)
            if receipt is not None:
                receipts.append(receipt)

    return GlobalCacheSnapshot(
        promoted_graphs=tuple(promoted_graphs),
        receipts=tuple(receipts),
        warnings=tuple(graph_warnings + receipt_warnings),
    )
