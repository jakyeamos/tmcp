"""Deterministic declared-load parsing and source-selection policy."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any


Node = dict[str, Any]
FamilyContext = dict[str, Any]

DECLARED_LOAD_VERB_PATTERN = re.compile(
    r"(?:search|load|read from|check|inspect|open)\s+`([^`]+)`",
    re.IGNORECASE,
)
DECLARED_LOAD_PATH_PATTERN = re.compile(
    r"`((?:[a-zA-Z0-9][a-zA-Z0-9_.-]*/)+|"
    r"[a-zA-Z0-9][a-zA-Z0-9_.-]*\.(?:md|json|yaml|yml))`"
)
DECLARED_LOAD_GLOBAL_BASENAMES = frozenset(
    {
        "coverage-gaps.md",
        "lint-candidates.md",
        "readme.md",
    }
)
DECLARED_LOAD_SURFACE_TERMS = (
    "onboarding",
    "settings",
    "billing",
    "dashboard",
    "dashboards",
    "forms",
    "permissions",
    "destructive",
    "empty state",
    "empty states",
    "loading state",
    "loading states",
    "validation",
    "checkout",
    "workspace",
)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def normalize_declared_load_pattern(pattern: str) -> str:
    """Normalize a seed or source-declared read pattern for path matching."""

    normalized = pattern.strip().strip("`").replace("\\", "/").lstrip("./")
    if not normalized:
        return ""
    if normalized.endswith("/"):
        return f"{normalized.rstrip('/')}/**"
    if "**" not in normalized and not Path(normalized).suffix:
        return f"{normalized}/**"
    return normalized


def declared_load_patterns_from_text(text: str) -> list[str]:
    """Parse the declared local reads embedded in harvested source text."""

    patterns: list[str] = []
    for match in DECLARED_LOAD_VERB_PATTERN.finditer(text):
        patterns.append(normalize_declared_load_pattern(match.group(1)))
    for match in DECLARED_LOAD_PATH_PATTERN.finditer(text):
        candidate = normalize_declared_load_pattern(match.group(1))
        if candidate and (
            "/" in candidate or candidate.endswith((".md", ".json", ".yaml", ".yml"))
        ):
            patterns.append(candidate)
    return [pattern for pattern in _ordered_unique(patterns) if pattern]


def node_matches_declared_load_pattern(rel_path: str, pattern: str) -> bool:
    """Return whether a harvested relative path satisfies a declared read."""

    rel = rel_path.replace("\\", "/").lstrip("./")
    pat = pattern.replace("\\", "/").lstrip("./")
    if not rel or not pat:
        return False
    if "**" in pat:
        regex = "^" + re.escape(pat).replace(r"\*\*", ".*") + "$"
        return bool(re.match(regex, rel))
    if "/" not in pat and Path(pat).suffix:
        return rel == pat or rel.endswith(f"/{pat}")
    return fnmatch.fnmatch(rel, pat) or rel == pat


def _surface_terms_from_objective(objective: str) -> list[str]:
    lower = objective.lower()
    return [term for term in DECLARED_LOAD_SURFACE_TERMS if term in lower]


def narrow_declared_load_paths(
    paths: list[str], objective: str, *, limit: int = 12
) -> list[str]:
    """Prefer objective-relevant paths while retaining global decision sources."""

    if not paths:
        return []
    ordered = _ordered_unique(paths)
    surfaces = _surface_terms_from_objective(objective)
    if not surfaces:
        return ordered[:limit]

    matched: list[str] = []
    global_paths: list[str] = []
    for path in ordered:
        lower = path.lower()
        basename = Path(path).name.lower()
        if basename in DECLARED_LOAD_GLOBAL_BASENAMES or "/standards/" in lower:
            global_paths.append(path)
            continue
        if any(
            surface in lower
            or surface.replace(" ", "-") in lower
            or surface.replace(" ", "_") in lower
            for surface in surfaces
        ):
            matched.append(path)
    return _ordered_unique(matched + global_paths)[:limit]


def _routing_metadata(node: Node) -> dict[str, Any]:
    metadata = node.get("routing_metadata")
    return metadata if isinstance(metadata, dict) else {}


def resolve_declared_load_paths(
    *,
    selected_nodes: list[Node],
    source_nodes: list[Node],
    objective: str,
    family_context: FamilyContext | None = None,
) -> list[str]:
    """Resolve declared reads from selected nodes and active family context."""

    patterns: list[str] = []
    for node in selected_nodes:
        patterns.extend(_string_list(_routing_metadata(node).get("declared_loads")))
    if family_context:
        patterns.extend(_string_list(family_context.get("declared_loads")))
    patterns = _ordered_unique(patterns)
    if not patterns:
        return []

    matched_paths: list[str] = []
    for node in source_nodes:
        rel_path = str(node.get("relative_path") or "")
        if not rel_path:
            continue
        if any(
            node_matches_declared_load_pattern(rel_path, pattern)
            for pattern in patterns
        ):
            matched_paths.append(rel_path)
    return narrow_declared_load_paths(matched_paths, objective)


def resolve_declared_load_nodes(
    *,
    selected_nodes: list[Node],
    source_nodes: list[Node],
    objective: str,
    family_context: FamilyContext | None = None,
    max_nodes: int = 6,
) -> tuple[list[str], list[Node]]:
    """Return narrowed read paths and unselected source nodes for enrichment."""

    narrowed_paths = resolve_declared_load_paths(
        selected_nodes=selected_nodes,
        source_nodes=source_nodes,
        objective=objective,
        family_context=family_context,
    )
    if not narrowed_paths:
        return [], []

    selected_paths = {
        str(node.get("relative_path") or "")
        for node in selected_nodes
        if node.get("relative_path")
    }
    narrowed_nodes = [
        node
        for node in source_nodes
        if str(node.get("relative_path") or "") in narrowed_paths
        and str(node.get("relative_path") or "") not in selected_paths
    ][:max_nodes]
    return narrowed_paths, narrowed_nodes
