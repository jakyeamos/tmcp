"""Narrow deterministic activation for compatibility composition packets."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .families import (
    compose_family_context,
    node_is_deferred_family_sibling,
    node_matches_family_primary,
    skill_slug_from_relative_path,
)
from .harvest_nodes import node_source_role, source_role_is_activation_eligible
from .routes import composition_route_boost, derive_task_identity


Node = dict[str, Any]
NodeSignalText = Callable[[Node], str]
MAX_COMPOSITION_NODES = 8
MAX_AUTOMATIC_BOOTSTRAP_SKILLS = 1
PHASE_TIE_BREAK_BOOST = 0.01
EXPLICIT_COMPOSITION_PHRASES = (
    "release readiness",
    "pr risk",
    "repo behavior",
    "migration readiness",
    "performance readiness",
    "ui rubric",
    "semantic proposal",
    "behavior manifest",
    "skill handoff",
)


def _core() -> Any:
    """Resolve shared lexical helpers after the compatibility module loads."""

    from . import composition

    return composition


def _routing_metadata(node: Node) -> dict[str, Any]:
    metadata = node.get("routing_metadata")
    return metadata if isinstance(metadata, dict) else {}


def _is_explicitly_scoped(node: Node, context: dict[str, Any]) -> bool:
    if bool(node.get("explicitly_scoped")):
        return True
    core = _core()
    scoped_paths = {
        str(path).strip()
        for path in core._string_list(context.get("explicitly_scoped_paths"))
        if str(path).strip()
    }
    relative_path = str(node.get("relative_path") or node.get("path") or "")
    return relative_path in scoped_paths


def _objective_names_skill(node: Node, objective: str) -> bool:
    core = _core()
    slug = skill_slug_from_relative_path(str(node.get("relative_path") or ""))
    return bool(slug and core.composition_terms(slug) and core._contains_signal_term(objective, slug))


def _selection_evidence(
    node: Node,
    objective: str,
    context: dict[str, Any],
    *,
    family_context: dict[str, Any] | None,
    active_routes: list[str],
    node_signal_text: NodeSignalText,
) -> dict[str, Any]:
    """Collect non-process evidence that makes an active source selectable."""

    core = _core()
    text = node_signal_text(node)
    objective_terms = core.composition_terms(objective)
    node_terms = core.composition_terms(text)
    metadata = _routing_metadata(node)
    rel_path = str(node.get("relative_path") or "")
    lexical_terms = sorted(objective_terms.intersection(node_terms))
    path_terms = sorted(
        term for term in objective_terms if core._contains_signal_term(rel_path, term)
    )
    phrase_matches = sorted(
        phrase
        for phrase in EXPLICIT_COMPOSITION_PHRASES
        if core._contains_signal_term(objective, phrase)
        and (
            core._contains_signal_term(rel_path, phrase)
            or core._contains_signal_term(text, phrase)
        )
    )
    trigger_matches = sorted(
        trigger
        for trigger in core._string_list(metadata.get("trigger_phrases"))
        if core.composition_terms(trigger)
        and core._contains_signal_term(objective, trigger)
    )
    command_matches = sorted(
        command
        for command in core._string_list(metadata.get("commands"))
        if core.composition_terms(command)
        and core._contains_signal_term(objective, command)
    )
    route_score = composition_route_boost(
        active_routes,
        relative_path=rel_path,
        source_type=str(node.get("source_type") or ""),
        text=text,
    )
    ui_files_changed = any(
        core.is_ui_file(path)
        for path in core._string_list(context.get("files_changed"))
    )
    ui_context = core.is_uiish_text(objective) or ui_files_changed
    ui_source = core.is_uiish_text(text) or any(
        core._contains_signal_term(rel_path, term)
        for term in ("ui rubric", "impeccable")
    )
    family_primary = node_matches_family_primary(node, family_context, objective)
    explicitly_scoped = _is_explicitly_scoped(node, context)
    named_skill = _objective_names_skill(node, objective)
    return {
        "text": text,
        "lexical_terms": lexical_terms,
        "path_terms": path_terms,
        "phrase_matches": phrase_matches,
        "trigger_matches": trigger_matches,
        "command_matches": command_matches,
        "route_score": route_score,
        "ui_context_match": ui_context and ui_source,
        "family_primary": family_primary,
        "explicitly_scoped": explicitly_scoped,
        "named_skill": named_skill,
        "has_real_relevance": bool(
            lexical_terms
            or path_terms
            or phrase_matches
            or trigger_matches
            or command_matches
            or route_score > 0
            or (ui_context and ui_source)
            or family_primary
            or explicitly_scoped
            or named_skill
        ),
    }


def _selection_rejection_reason(
    node: Node,
    objective: str,
    phase: str,
    context: dict[str, Any],
    *,
    family_context: dict[str, Any] | None,
    active_routes: list[str],
    node_signal_text: NodeSignalText,
) -> str:
    core = _core()
    metadata = _routing_metadata(node)
    evidence = _selection_evidence(
        node,
        objective,
        context,
        family_context=family_context,
        active_routes=active_routes,
        node_signal_text=node_signal_text,
    )
    phase_matches = phase and phase in core._string_list(metadata.get("phase_hints"))
    if phase_matches and not evidence["has_real_relevance"]:
        return "phase_hint_without_non_process_relevance"
    return "no_non_process_objective_route_or_explicit_scope_match"


def score_composition_node(
    node: Node,
    objective: str,
    phase: str,
    context: dict[str, Any],
    *,
    family_context: dict[str, Any] | None = None,
    active_routes: list[str] | None = None,
    node_signal_text: NodeSignalText,
) -> float:
    """Score one harvested node for compatibility-packet inclusion."""

    core = _core()
    source_role = node_source_role(node)
    if not source_role_is_activation_eligible(source_role):
        return 0.0
    if node_is_deferred_family_sibling(node, family_context, objective):
        return 0.0
    evidence = _selection_evidence(
        node,
        objective,
        context,
        family_context=family_context,
        active_routes=active_routes or [],
        node_signal_text=node_signal_text,
    )
    if source_role != "governing_instruction" and not evidence["has_real_relevance"]:
        return 0.0
    text = str(evidence["text"])
    metadata = _routing_metadata(node)
    score = float(len(evidence["lexical_terms"]))
    source_type = str(node.get("source_type") or "")
    rel_path = str(node.get("relative_path") or "").lower()
    if core._contains_signal_term(rel_path, "repo behavior") and not core.objective_has_phrase(
        objective, core.REPO_BEHAVIOR_PHRASES
    ):
        return 0.0
    ui_files_changed = any(
        core.is_ui_file(path)
        for path in core._string_list(context.get("files_changed"))
    )
    if any(
        core._contains_signal_term(rel_path, term)
        for term in ("ui rubric", "impeccable")
    ) and not (core.is_uiish_text(objective) or ui_files_changed):
        return 0.0
    if source_role == "governing_instruction":
        score += 5.0
    score += 5.0 * len(evidence["phrase_matches"])
    if rel_path.endswith("skill.md") and evidence["path_terms"]:
        score += 4.0
    if core._contains_signal_term(rel_path, "release readiness") and core.objective_has_phrase(
        objective, core.RELEASE_READINESS_PHRASES
    ):
        score += 5.0
    if core._contains_signal_term(rel_path, "pr risk") and not core.objective_has_phrase(
        objective, core.PR_RISK_PHRASES
    ):
        score -= 5.0
    score += 3.0 * len(evidence["trigger_matches"])
    score += 4.0 * len(evidence["command_matches"])
    if (
        evidence["has_real_relevance"]
        and phase
        and phase in core._string_list(metadata.get("phase_hints"))
    ):
        score += PHASE_TIE_BREAK_BOOST
    if phase == "start" and source_type == "agent_operating_contract":
        score += 1.0
    if core.is_uiish_text(objective) and any(
        term in text
        for term in ("browser", "contrast", "responsive", "reduced motion", "design")
    ):
        score += 2.5
    if ui_files_changed and core.is_uiish_text(text):
        score += 2.0
    if any(
        core._contains_signal_term(objective, boundary)
        for boundary in core._string_list(metadata.get("do_not_use_when"))
    ):
        score -= 6.0
    if evidence["family_primary"]:
        score += 8.0
    if evidence["explicitly_scoped"]:
        score += 8.0
    if family_context and str(node.get("relative_path") or "") in core._string_list(
        family_context.get("router_relative_paths")
    ):
        score += 3.0
    return score + float(evidence["route_score"])


def select_composition_nodes_with_diagnostics(
    source_nodes: list[Node],
    objective: str,
    phase: str,
    context: dict[str, Any],
    *,
    family_context: dict[str, Any] | None = None,
    active_routes: list[str] | None = None,
    node_signal_text: NodeSignalText,
) -> tuple[list[Node], dict[str, Any]]:
    """Select governing sources plus a bounded, evidence-backed skill bootstrap."""

    core = _core()
    active_family_context = family_context or compose_family_context(
        source_nodes,
        objective,
        context=context,
        active_routes=active_routes,
        node_signal_text=node_signal_text,
    )
    resolved_routes = active_routes or core._string_list(
        derive_task_identity(objective, context).get("active_routes")
    )
    governing: list[tuple[float, str, Node]] = []
    explicit_candidates: list[tuple[float, str, Node]] = []
    automatic_candidates: list[tuple[float, str, Node]] = []
    rejected: list[dict[str, str]] = []
    ineligible_source_counts: dict[str, int] = {}

    def reject(node: Node, reason: str) -> None:
        rejected.append(
            {
                "source": str(node.get("relative_path") or node.get("id") or ""),
                "source_role": node_source_role(node),
                "reason": reason,
            }
        )

    for node in source_nodes:
        source_role = node_source_role(node)
        if not source_role_is_activation_eligible(source_role):
            ineligible_source_counts[source_role] = (
                ineligible_source_counts.get(source_role, 0) + 1
            )
            continue
        if node_is_deferred_family_sibling(node, active_family_context, objective):
            reject(node, "deferred_family_sibling")
            continue
        score = score_composition_node(
            node,
            objective,
            phase,
            context,
            family_context=active_family_context,
            active_routes=resolved_routes,
            node_signal_text=node_signal_text,
        )
        path = str(node.get("relative_path") or "")
        if source_role == "governing_instruction":
            governing.append((score, path, node))
            continue
        if score <= 0:
            reject(
                node,
                _selection_rejection_reason(
                    node,
                    objective,
                    phase,
                    context,
                    family_context=active_family_context,
                    active_routes=resolved_routes,
                    node_signal_text=node_signal_text,
                ),
            )
            continue
        evidence = _selection_evidence(
            node,
            objective,
            context,
            family_context=active_family_context,
            active_routes=resolved_routes,
            node_signal_text=node_signal_text,
        )
        candidate = (score, path, node)
        if (
            evidence["explicitly_scoped"]
            or evidence["family_primary"]
            or evidence["named_skill"]
            or (
                str(node.get("source_type") or "") == "scoped_packet_seed"
                and core._contains_signal_term(
                    objective, str(node.get("seed_id") or node.get("id") or "")
                )
            )
        ):
            explicit_candidates.append(candidate)
        else:
            automatic_candidates.append(candidate)

    sort_key = lambda item: (-item[0], item[1])
    governing.sort(key=sort_key)
    explicit_candidates.sort(key=sort_key)
    automatic_candidates.sort(key=sort_key)
    selected = [node for _score, _path, node in governing[:MAX_COMPOSITION_NODES]]
    for _score, _path, node in governing[MAX_COMPOSITION_NODES:]:
        reject(node, "governing_source_capacity_exceeded")
    remaining_capacity = MAX_COMPOSITION_NODES - len(selected)
    selected_explicit = explicit_candidates[:remaining_capacity]
    selected.extend(node for _score, _path, node in selected_explicit)
    for _score, _path, node in explicit_candidates[remaining_capacity:]:
        reject(node, "explicit_source_capacity_exceeded")
    remaining_capacity = MAX_COMPOSITION_NODES - len(selected)
    automatic_limit = (
        remaining_capacity
        if active_family_context
        else min(remaining_capacity, MAX_AUTOMATIC_BOOTSTRAP_SKILLS)
    )
    selected_automatic = automatic_candidates[:automatic_limit]
    selected.extend(node for _score, _path, node in selected_automatic)
    for _score, _path, node in automatic_candidates[automatic_limit:]:
        reject(node, "deferred_after_narrow_bootstrap_cap")
    diagnostics: dict[str, Any] = {
        "selection_mode": "family_scoped" if active_family_context else "narrow_bootstrap",
        "max_selected_nodes": MAX_COMPOSITION_NODES,
        "max_automatic_bootstrap_skills": MAX_AUTOMATIC_BOOTSTRAP_SKILLS,
        "selected_sources": [
            str(node.get("relative_path") or node.get("id") or "")
            for node in selected
        ],
        "selected_governing_sources": [
            str(node.get("relative_path") or node.get("id") or "")
            for _score, _path, node in governing[:MAX_COMPOSITION_NODES]
        ],
        "selected_explicit_sources": [
            str(node.get("relative_path") or node.get("id") or "")
            for _score, _path, node in selected_explicit
        ],
        "selected_automatic_bootstrap_sources": [
            str(node.get("relative_path") or node.get("id") or "")
            for _score, _path, node in selected_automatic
        ],
        "ineligible_source_counts": dict(sorted(ineligible_source_counts.items())),
        "rejected_sources": rejected,
        "warnings": [],
    }
    if not automatic_candidates and not explicit_candidates:
        diagnostics["warnings"].append(
            "No active skill had explicit scope or non-process objective/route relevance; active skills were deferred."
        )
    elif automatic_candidates[automatic_limit:]:
        diagnostics["warnings"].append(
            "Additional relevant active skills were deferred until a semantic proposal supplies source-backed relationships."
        )
    return selected, diagnostics


def select_composition_nodes(
    source_nodes: list[Node],
    objective: str,
    phase: str,
    context: dict[str, Any],
    *,
    family_context: dict[str, Any] | None = None,
    active_routes: list[str] | None = None,
    node_signal_text: NodeSignalText,
) -> list[Node]:
    """Return the deterministic selection without diagnostics."""

    selected, _diagnostics = select_composition_nodes_with_diagnostics(
        source_nodes,
        objective,
        phase,
        context,
        family_context=family_context,
        active_routes=active_routes,
        node_signal_text=node_signal_text,
    )
    return selected
