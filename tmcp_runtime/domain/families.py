"""Deterministic task-family routing policy for composed TMCP packets."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .declared_loads import (
    normalize_declared_load_pattern,
    resolve_declared_load_paths,
)
from .routes import derive_task_identity, score_scoped_seed, scoped_seed_threshold


Node = dict[str, Any]
FamilyContext = dict[str, Any]
NodeSignalText = Callable[[Node], str]

ROUTER_CHILD_PATTERN = re.compile(r"→\s*([a-z0-9-]+)")
FAMILY_SUPPORT_DOC_NAMES = frozenset({"install.md", "example_workflow.md", "readme.md"})
FAMILY_PHASE_ALIASES = {
    "start": "runtime",
    "discover": "runtime",
    "verify": "polish-verify",
    "verification": "polish-verify",
    "final": "review",
}


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


def _routing_metadata(node: Node) -> dict[str, Any]:
    metadata = node.get("routing_metadata")
    return metadata if isinstance(metadata, dict) else {}


def normalize_skill_slug(value: str) -> str:
    """Normalize a skill name for deterministic family comparisons."""

    return re.sub(r"\s+", "-", str(value or "").strip().lower())


def skill_slug_from_relative_path(rel_path: str) -> str:
    """Return a skill slug only for a skill-definition path."""

    normalized = str(rel_path or "").replace("\\", "/")
    if not normalized.lower().endswith("/skill.md"):
        return ""
    return Path(normalized).parent.name


def _objective_names_skill_slug(objective: str, slug: str) -> bool:
    if not slug:
        return False
    lower = objective.lower()
    normalized = normalize_skill_slug(slug)
    return normalized in lower or normalized.replace("-", " ") in lower


def _is_skill_family_router(node: Node, node_signal_text: NodeSignalText) -> bool:
    if str(node.get("source_type") or "") != "skill_definition":
        return False
    text = node_signal_text(node).lower()
    rel_path = str(node.get("relative_path") or "").lower()
    return (
        "choose exactly one primary mode" in text
        or "skill family" in text
        or "/product-judgment/" in rel_path
        or bool(ROUTER_CHILD_PATTERN.search(text))
    )


def _router_child_slugs(node: Node, node_signal_text: NodeSignalText) -> list[str]:
    return _ordered_unique(ROUTER_CHILD_PATTERN.findall(node_signal_text(node)))


def _family_skills_root_from_sources(source_patterns: list[str]) -> str:
    if not source_patterns:
        return ""
    normalized = [
        pattern.replace("\\", "/").lstrip("./") for pattern in source_patterns
    ]
    if not normalized:
        return ""
    common = os.path.commonpath(normalized)
    if common.endswith(".md"):
        common = str(Path(common).parent)
    if not common.endswith("/"):
        common = f"{common}/"
    return common


def family_context_from_seed_node(seed_node: Node, objective: str) -> FamilyContext:
    """Build a family context from a selected scoped seed node."""

    source_references = _string_list(seed_node.get("source_references"))
    matched_sources = [
        source_ref
        for source_ref in source_references
        if _objective_names_skill_slug(
            objective, skill_slug_from_relative_path(source_ref)
        )
    ]
    primary_source_patterns = matched_sources or source_references
    primary_skill_slugs = {
        skill_slug_from_relative_path(source_ref)
        for source_ref in primary_source_patterns
        if skill_slug_from_relative_path(source_ref)
    }
    declared_loads = _ordered_unique(
        [
            normalize_declared_load_pattern(pattern)
            for pattern in _string_list(seed_node.get("loads"))
        ]
        + _string_list(_routing_metadata(seed_node).get("declared_loads"))
    )
    deferred_skill_slugs = {
        normalize_skill_slug(item)
        for item in _string_list(seed_node.get("chains_before"))
        + _string_list(seed_node.get("do_not_activate_with"))
    }
    deferred_skill_slugs -= {normalize_skill_slug(slug) for slug in primary_skill_slugs}
    return {
        "kind": "scoped_packet_seed",
        "active_seed_id": str(seed_node.get("seed_id") or seed_node.get("id") or ""),
        "seed_name": str(seed_node.get("title") or seed_node.get("seed_id") or ""),
        "route_affinity": _string_list(seed_node.get("route_affinity")),
        "primary_source_patterns": primary_source_patterns,
        "primary_skill_slugs": sorted(primary_skill_slugs),
        "declared_loads": [pattern for pattern in declared_loads if pattern],
        "deferred_skill_slugs": sorted(deferred_skill_slugs),
        "chains_after": _string_list(seed_node.get("chains_after")),
        "family_skills_root": _family_skills_root_from_sources(source_references),
        "router_relative_paths": [],
    }


def _family_context_from_router(
    router_node: Node,
    source_nodes: list[Node],
    objective: str,
    node_signal_text: NodeSignalText,
) -> FamilyContext | None:
    child_slugs = _router_child_slugs(router_node, node_signal_text)
    matched_children = [
        slug for slug in child_slugs if _objective_names_skill_slug(objective, slug)
    ]
    if not matched_children:
        return None
    primary_slug = matched_children[0]
    router_path = str(router_node.get("relative_path") or "")
    family_root = str(Path(router_path.replace("\\", "/")).parent)
    if family_root and not family_root.endswith("/"):
        family_root = f"{family_root}/"
    deferred_skill_slugs = {
        normalize_skill_slug(slug)
        for slug in child_slugs
        if normalize_skill_slug(slug) != normalize_skill_slug(primary_slug)
    }
    primary_patterns = [
        str(node.get("relative_path") or "")
        for node in source_nodes
        if skill_slug_from_relative_path(str(node.get("relative_path") or ""))
        == primary_slug
    ]
    declared_loads: list[str] = []
    for node in source_nodes:
        if (
            skill_slug_from_relative_path(str(node.get("relative_path") or ""))
            != primary_slug
        ):
            continue
        declared_loads.extend(
            _string_list(_routing_metadata(node).get("declared_loads"))
        )
    return {
        "kind": "router_skill",
        "active_seed_id": "",
        "primary_source_patterns": primary_patterns,
        "primary_skill_slugs": [primary_slug],
        "declared_loads": _ordered_unique(declared_loads),
        "deferred_skill_slugs": sorted(deferred_skill_slugs),
        "chains_after": [],
        "family_skills_root": family_root,
        "router_relative_paths": [router_path] if router_path else [],
    }


def compose_family_context(
    source_nodes: list[Node],
    objective: str,
    *,
    context: dict[str, Any] | None = None,
    active_routes: list[str] | None = None,
    node_signal_text: NodeSignalText,
) -> FamilyContext | None:
    """Resolve the active seed or router family without mutating source nodes."""

    resolved_routes = active_routes
    if not resolved_routes:
        identity_context = dict(context or {})
        resolved_routes = _string_list(
            derive_task_identity(objective, identity_context).get("active_routes")
        )
    seed_candidates: list[tuple[float, Node]] = []
    for node in source_nodes:
        if str(node.get("source_type") or "") != "scoped_packet_seed":
            continue
        score = score_scoped_seed(node, objective, resolved_routes)
        threshold = scoped_seed_threshold(node, resolved_routes)
        if score >= threshold:
            seed_candidates.append((score, node))
    if seed_candidates:
        _, seed_node = max(
            seed_candidates,
            key=lambda item: (
                item[0],
                str(item[1].get("seed_id") or item[1].get("id") or ""),
            ),
        )
        return family_context_from_seed_node(seed_node, objective)

    for router_node in source_nodes:
        if not _is_skill_family_router(router_node, node_signal_text):
            continue
        family_context = _family_context_from_router(
            router_node,
            source_nodes,
            objective,
            node_signal_text,
        )
        if family_context is not None:
            return family_context
    return None


def node_matches_family_primary(
    node: Node,
    family_context: FamilyContext | None,
    objective: str,
) -> bool:
    """Return whether a harvested node is the active family primary source."""

    if not family_context:
        return False
    rel_path = str(node.get("relative_path") or "")
    slug = skill_slug_from_relative_path(rel_path)
    if slug and slug in _string_list(family_context.get("primary_skill_slugs")):
        return True
    for pattern in _string_list(family_context.get("primary_source_patterns")):
        normalized_pattern = pattern.replace("\\", "/").lstrip("./")
        if rel_path.endswith(normalized_pattern) or normalized_pattern in rel_path:
            return True
    seed_id = str(family_context.get("active_seed_id") or "")
    if seed_id and seed_id in rel_path:
        return True
    return _objective_names_skill_slug(objective, slug)


def node_is_deferred_family_sibling(
    node: Node,
    family_context: FamilyContext | None,
    objective: str,
) -> bool:
    """Return whether a sibling or support document should stay out of this packet."""

    if not family_context:
        return False
    rel_path = str(node.get("relative_path") or "")
    rel_lower = rel_path.lower()
    basename = Path(rel_lower).name
    if basename in FAMILY_SUPPORT_DOC_NAMES and not any(
        term in objective.lower()
        for term in ("install", "example", "workflow", "readme")
    ):
        return True
    slug = skill_slug_from_relative_path(rel_path)
    if not slug:
        return False
    if node_matches_family_primary(node, family_context, objective):
        return False
    if _objective_names_skill_slug(objective, slug):
        return False
    deferred = {
        normalize_skill_slug(item)
        for item in _string_list(family_context.get("deferred_skill_slugs"))
    }
    if normalize_skill_slug(slug) in deferred:
        return True
    family_root = str(family_context.get("family_skills_root") or "")
    primary_slugs = {
        normalize_skill_slug(item)
        for item in _string_list(family_context.get("primary_skill_slugs"))
    }
    if (
        family_root
        and family_root in rel_path.replace("\\", "/")
        and rel_lower.endswith("/skill.md")
        and normalize_skill_slug(slug) not in primary_slugs
    ):
        return True
    return False


def normalize_family_phase(phase: str) -> str:
    """Normalize public runtime aliases to a family transition phase."""

    normalized = str(phase or "start").strip().lower()
    return FAMILY_PHASE_ALIASES.get(normalized, normalized)


def _seed_node_for_family_context(
    source_nodes: list[Node], family_context: FamilyContext | None
) -> Node | None:
    if not family_context:
        return None
    seed_id = str(family_context.get("active_seed_id") or "")
    if not seed_id:
        return None
    for node in source_nodes:
        if str(node.get("seed_id") or node.get("id") or "") == seed_id:
            return node
    return None


def _phase_transitions_for_seed_node(
    seed_node: Node | None,
    family_context: FamilyContext | None,
) -> dict[str, dict[str, Any]]:
    if seed_node:
        raw = seed_node.get("phase_transitions")
        if isinstance(raw, dict) and raw:
            return {
                str(phase).lower(): dict(value)
                for phase, value in raw.items()
                if isinstance(value, dict)
            }
    if family_context and _string_list(family_context.get("chains_after")):
        activate_skills = _string_list(family_context.get("chains_after"))
        fallback = {
            "next_phases": ["implementation"],
            "activate_skills": activate_skills,
            "verification_gates": [
                "Complete the current family phase before advancing."
            ],
        }
        return {
            "runtime": dict(fallback),
            "start": dict(fallback),
        }
    return {}


def _pick_next_family_phase(
    candidates: list[str], context: dict[str, Any], objective: str
) -> str:
    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]
    objective_lower = objective.lower()
    browser_evidence = _string_list(context.get("browser_evidence"))
    if browser_evidence:
        for candidate in candidates:
            if "polish" in candidate or "review" in candidate:
                return candidate
    if any("review" in candidate for candidate in candidates) and any(
        term in objective_lower for term in ("review", "pr", "diff")
    ):
        for candidate in candidates:
            if "review" in candidate:
                return candidate
    if any("polish" in candidate for candidate in candidates) and any(
        term in objective_lower for term in ("polish", "motion", "screenshot")
    ):
        for candidate in candidates:
            if "polish" in candidate:
                return candidate
    return candidates[0]


def _skill_relative_paths_for_slugs(
    source_nodes: list[Node], skill_slugs: list[str]
) -> list[str]:
    wanted = {normalize_skill_slug(slug) for slug in skill_slugs if slug}
    if not wanted:
        return []
    paths: list[str] = []
    for node in source_nodes:
        rel_path = str(node.get("relative_path") or "")
        slug = skill_slug_from_relative_path(rel_path)
        if normalize_skill_slug(slug) in wanted:
            paths.append(rel_path)
    return _ordered_unique(paths)


def runtime_family_packet_delta(
    *,
    current_phase: str,
    family_context: FamilyContext | None,
    seed_node: Node | None,
    source_nodes: list[Node],
    objective: str,
    context: dict[str, Any],
    latest_user_message: str,
) -> dict[str, Any]:
    """Build a deterministic, advisory delta for an active skill family."""

    if not family_context:
        return {}
    if any(
        term in latest_user_message.lower()
        for term in ("not yet", "before implementing", "hold on", "stay in runtime")
    ):
        return {}

    transitions = _phase_transitions_for_seed_node(seed_node, family_context)
    current = transitions.get(normalize_family_phase(current_phase))
    if not current:
        return {}

    next_phases = _string_list(current.get("next_phases")) or _string_list(
        current.get("next")
    )
    if not next_phases:
        return {}

    suggested_phase = _pick_next_family_phase(next_phases, context, objective)
    activate_skills = _string_list(current.get("activate_skills"))
    if not activate_skills:
        activate_skills = _string_list(family_context.get("chains_after"))

    activate_paths = _skill_relative_paths_for_slugs(source_nodes, activate_skills)
    virtual_selected = [
        node
        for node in source_nodes
        if str(node.get("relative_path") or "") in activate_paths
    ]
    newly_required_reads = list(activate_paths)
    newly_required_reads.extend(
        resolve_declared_load_paths(
            selected_nodes=virtual_selected,
            source_nodes=source_nodes,
            objective=objective,
            family_context=family_context,
        )
    )
    for node in virtual_selected:
        newly_required_reads.extend(
            _string_list(_routing_metadata(node).get("required_reads"))
        )

    primary_slugs = {
        normalize_skill_slug(slug)
        for slug in _string_list(family_context.get("primary_skill_slugs"))
    }
    activate_normalized = {normalize_skill_slug(slug) for slug in activate_skills}
    deferred_skills = [
        slug
        for slug in _string_list(family_context.get("deferred_skill_slugs"))
        if normalize_skill_slug(slug) not in activate_normalized
    ]
    activated_atoms = [f"skill:{slug}" for slug in activate_skills if slug]
    deactivated_atoms = [
        f"skill:{slug}"
        for slug in sorted(primary_slugs)
        if slug not in activate_normalized
    ]

    return {
        "suggested_phase": suggested_phase,
        "suggested_skills": activate_skills,
        "deferred_skills": deferred_skills,
        "activated_atoms": _ordered_unique(activated_atoms),
        "deactivated_atoms": _ordered_unique(deactivated_atoms),
        "newly_required_reads": _ordered_unique(newly_required_reads),
        "verification_gates": _string_list(current.get("verification_gates")),
        "family_context": family_context,
    }


def runtime_family_seed_context(
    source_nodes: list[Node],
    objective: str,
    current_phase: str,
    *,
    node_signal_text: NodeSignalText,
) -> tuple[FamilyContext | None, Node | None]:
    """Resolve the family context, including transition-only seed fallbacks."""

    family_context = compose_family_context(
        source_nodes,
        objective,
        node_signal_text=node_signal_text,
    )
    seed_node = _seed_node_for_family_context(source_nodes, family_context)
    if seed_node is not None and family_context is not None:
        return family_context, seed_node

    normalized_phase = normalize_family_phase(current_phase)
    for node in source_nodes:
        if str(node.get("source_type") or "") != "scoped_packet_seed":
            continue
        transitions = _phase_transitions_for_seed_node(node, None)
        if normalized_phase not in transitions:
            continue
        return family_context_from_seed_node(node, objective), node
    return None, None
