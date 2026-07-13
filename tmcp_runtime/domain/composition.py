"""Deterministic source-selection and contextual composition policy."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .families import (
    compose_family_context,
    node_is_deferred_family_sibling,
    node_matches_family_primary,
)
from .routes import composition_route_boost, derive_task_identity


Node = dict[str, Any]
NodeSignalText = Callable[[Node], str]


def normalize_cache_policy(value: object) -> str:
    """Allow shared cache input only through the explicit global opt-in."""

    return "global" if value == "global" else "none"

UI_SIGNAL_TERMS = (
    "ui",
    "ux",
    "frontend",
    "front-end",
    "react",
    "next.js",
    "tsx",
    "jsx",
    "css",
    "dashboard",
    "landing page",
    "design",
    "browser",
    "responsive",
    "contrast",
    "button",
    "buttons",
    "controls",
)
UI_FILE_SUFFIXES = (
    ".tsx",
    ".jsx",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
    ".astro",
    ".html",
)
REPO_BEHAVIOR_PHRASES = (
    "repo behavior",
    "behavior sweep",
    "behavior spec",
    "canonical spreadsheet",
    "feature id",
    "feature ids",
    "status machine",
    "status-machine",
)
UI_VERIFICATION_TERMS = (
    "browser",
    "screenshot",
    "contrast",
    "reduced motion",
    "responsive",
)
COMPOSITION_GENERIC_TERMS = {
    "agent",
    "agents",
    "before",
    "codex",
    "current",
    "improve",
    "make",
    "packet",
    "packets",
    "readiness",
    "release",
    "skill",
    "skills",
    "start",
    "task",
    "tmcp",
    "workflow",
    "workflows",
}
RELEASE_READINESS_PHRASES = (
    "release readiness",
    "ship no ship",
    "ship/no-ship",
    "quality gate",
    "quality gates",
    "package check",
    "package checks",
    "hosted evidence",
    "ci evidence",
    "changelog",
)
PR_RISK_PHRASES = (
    "pr risk",
    "pull request risk",
    "changed surface",
    "merge risk",
)


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


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


def _contains_signal_term(text: str, term: str) -> bool:
    needle = term.lower().strip()
    if not needle:
        return False
    pieces = [piece for piece in re.split(r"[\s_/-]+", needle) if piece]
    if len(pieces) > 1:
        pattern = (
            r"(?<![a-z0-9])"
            + r"[\s_/-]+".join(re.escape(piece) for piece in pieces)
            + r"(?![a-z0-9])"
        )
    else:
        pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def _text_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", value.lower()))


def composition_terms(value: str) -> set[str]:
    """Return objective terms that carry composition-selection signal."""

    return _text_tokens(value).difference(COMPOSITION_GENERIC_TERMS)


def objective_has_phrase(objective: str, phrases: tuple[str, ...]) -> bool:
    """Match a phrase despite dash or underscore spelling differences."""

    lower = objective.lower()
    normalized = lower.replace("-", " ").replace("_", " ")
    return any(phrase in lower or phrase in normalized for phrase in phrases)


def is_uiish_text(value: str) -> bool:
    return any(_contains_signal_term(value, term) for term in UI_SIGNAL_TERMS)


def is_ui_file(path: str) -> bool:
    return path.lower().endswith(UI_FILE_SUFFIXES)


def _routing_metadata(node: Node) -> dict[str, Any]:
    metadata = node.get("routing_metadata")
    return metadata if isinstance(metadata, dict) else {}


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
    """Score one harvested node for inclusion in a composed packet."""

    if node_is_deferred_family_sibling(node, family_context, objective):
        return 0.0

    text = node_signal_text(node)
    objective_lower = objective.lower()
    objective_terms = composition_terms(objective)
    node_terms = composition_terms(text)
    metadata = _routing_metadata(node)
    score = float(len(objective_terms.intersection(node_terms)))
    source_type = str(node.get("source_type") or "")
    rel_path = str(node.get("relative_path") or "").lower()

    if "repo-behavior" in rel_path and not objective_has_phrase(
        objective,
        REPO_BEHAVIOR_PHRASES,
    ):
        return 0.0

    ui_files_changed = any(
        is_ui_file(path) for path in _string_list(context.get("files_changed"))
    )
    if any(term in rel_path for term in ("ui-rubric", "impeccable")) and not (
        is_uiish_text(objective) or ui_files_changed
    ):
        return 0.0

    if source_type == "agent_operating_contract":
        score += 5.0
    if rel_path.endswith("skill.md") and any(
        term in rel_path for term in objective_terms
    ):
        score += 4.0
    if "release-readiness" in rel_path and objective_has_phrase(
        objective,
        RELEASE_READINESS_PHRASES,
    ):
        score += 5.0
    if "pr-risk" in rel_path and not objective_has_phrase(objective, PR_RISK_PHRASES):
        score -= 5.0
    for trigger in _string_list(metadata.get("trigger_phrases")):
        if trigger.lower() in COMPOSITION_GENERIC_TERMS:
            continue
        if trigger.lower() in objective_lower:
            score += 3.0
    for command in _string_list(metadata.get("commands")):
        if command.lower() in objective_lower:
            score += 4.0
    if phase and phase in _string_list(metadata.get("phase_hints")):
        score += 2.0
    if phase == "start" and source_type == "agent_operating_contract":
        score += 1.0
    if is_uiish_text(objective) and any(
        term in text
        for term in ("browser", "contrast", "responsive", "reduced motion", "design")
    ):
        score += 2.5
    if ui_files_changed and is_uiish_text(text):
        score += 2.0
    if any(
        boundary.lower() in objective_lower
        for boundary in _string_list(metadata.get("do_not_use_when"))
    ):
        score -= 6.0
    if node_matches_family_primary(node, family_context, objective):
        score += 8.0
    if family_context and str(node.get("relative_path") or "") in _string_list(
        family_context.get("router_relative_paths")
    ):
        score += 3.0
    score += composition_route_boost(
        active_routes or [],
        relative_path=str(node.get("relative_path") or ""),
        source_type=source_type,
        text=text,
    )
    return score


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
    """Return the eight highest-scoring harvested nodes without mutating inputs."""

    active_family_context = family_context or compose_family_context(
        source_nodes,
        objective,
        context=context,
        active_routes=active_routes,
        node_signal_text=node_signal_text,
    )
    resolved_routes = active_routes or _string_list(
        derive_task_identity(objective, context).get("active_routes")
    )
    scored: list[tuple[float, str, Node]] = []
    for node in source_nodes:
        score = score_composition_node(
            node,
            objective,
            phase,
            context,
            family_context=active_family_context,
            active_routes=resolved_routes,
            node_signal_text=node_signal_text,
        )
        if score <= 0:
            continue
        scored.append((score, str(node.get("relative_path") or ""), node))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [node for _, _, node in scored[:8]]


def merge_composition_nodes(
    primary_nodes: list[Node],
    additional_nodes: list[Node],
    *,
    max_nodes: int = 14,
) -> list[Node]:
    """Merge composition selections while preserving source order and identity."""

    merged: list[Node] = []
    seen: set[str] = set()
    for node in [*primary_nodes, *additional_nodes]:
        rel_path = str(node.get("relative_path") or "")
        if not rel_path or rel_path in seen:
            continue
        seen.add(rel_path)
        merged.append(node)
        if len(merged) >= max_nodes:
            break
    return merged


def contextual_atoms_and_gates(
    objective: str,
    phase: str,
    context: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    files_changed = _string_list(context.get("files_changed"))
    failures = _string_list(context.get("failures"))
    browser_evidence = _string_list(context.get("browser_evidence"))
    objective_lower = objective.lower()
    failure_text = " ".join(failures).lower()
    pending_hosted_release_evidence = any(
        term in failure_text for term in ("hosted evidence", "release evidence")
    ) and any(
        term in failure_text
        for term in ("pending", "no hosted", "no matching", "external")
    )
    active_atoms: list[str] = []
    required_reads: list[str] = []
    verification_gates: list[str] = []
    if is_uiish_text(objective) or any(is_ui_file(path) for path in files_changed):
        active_atoms.append("ui-browser-verification")
        required_reads.append("UI/browser verification guidance for changed surfaces.")
        verification_gates.append(
            "Verify rendered UI in a browser with screenshot or DOM evidence."
        )
        if any(
            term in objective_lower
            for term in ("design", "landing", "frontend", "ui", "dashboard")
        ):
            verification_gates.extend(
                [
                    "Verify contrast on visible UI states.",
                    "Verify reduced motion behavior where animation is present.",
                    "Verify responsive behavior across relevant viewport sizes.",
                ]
            )
    if pending_hosted_release_evidence:
        active_atoms.append("explicit-evidence-gaps")
        required_reads.append(
            "Hosted release evidence record and release evidence checker output."
        )
        verification_gates.append(
            "Do not claim release readiness until hosted evidence is recorded for release."
        )
    elif failures or any(
        term in objective_lower for term in ("bug", "failing", "failure", "debug")
    ):
        active_atoms.append("debugging-regression")
        required_reads.append(
            "Debugging and regression evidence from the current failure."
        )
        verification_gates.append(
            "Re-run the failing command and capture the passing result."
        )
    if phase == "final" or "final" in objective_lower:
        active_atoms.append("verification-before-completion")
        verification_gates.append(
            "Run the highest-signal verification gate before final response."
        )
    if browser_evidence and "ui-browser-verification" not in active_atoms:
        active_atoms.append("ui-browser-verification")
        verification_gates.append("Use browser evidence to confirm the next claim.")
    return (
        _ordered_unique(active_atoms),
        _ordered_unique(required_reads),
        _ordered_unique(verification_gates),
    )


def filter_source_verification_gates(
    gates: list[str],
    objective: str,
    context: dict[str, Any],
) -> list[str]:
    ui_context = is_uiish_text(objective) or any(
        is_ui_file(path) for path in _string_list(context.get("files_changed"))
    )
    repo_behavior_context = objective_has_phrase(objective, REPO_BEHAVIOR_PHRASES)
    filtered: list[str] = []
    for gate in gates:
        lower = gate.lower()
        if any(term in lower for term in UI_VERIFICATION_TERMS) and not ui_context:
            continue
        if "canonical spreadsheet" in lower and not repo_behavior_context:
            continue
        filtered.append(gate)
    return filtered


def matching_reference_reads(
    source_nodes: list[dict[str, Any]],
    objective: str,
) -> list[str]:
    objective_lower = objective.lower()
    reads: list[str] = []
    for node in source_nodes:
        rel_path = str(node.get("relative_path") or "")
        rel_lower = rel_path.lower()
        if (
            "/reference/" not in f"/{rel_lower}"
            and "/references/" not in f"/{rel_lower}"
        ):
            continue
        if "craft" in objective_lower and rel_lower.endswith("craft.md"):
            reads.append(rel_path)
        if any(
            term in objective_lower for term in ("landing", "brand", "site")
        ) and rel_lower.endswith("brand.md"):
            reads.append(rel_path)
        if any(
            term in objective_lower for term in ("dashboard", "product", "audit")
        ) and rel_lower.endswith("product.md"):
            reads.append(rel_path)
        if (
            any(
                term in objective_lower
                for term in ("verify", "verification", "browser")
            )
            and "verification" in rel_lower
        ):
            reads.append(rel_path)
    return reads
