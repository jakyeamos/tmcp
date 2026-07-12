"""Deterministic composition policy shared by TMCP runtime adapters."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from .families import (
    compose_family_context,
    node_is_deferred_family_sibling,
    node_matches_family_primary,
)
from .routes import (
    ROUTE_CATALOG_VERSION,
    composition_route_boost,
    derive_task_identity,
)


Node = dict[str, Any]
NodeSignalText = Callable[[Node], str]


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


def compiled_from_packet(
    *,
    cache_policy: str,
    family_context: dict[str, Any] | None,
    evidence_citations: list[dict[str, Any]],
) -> dict[str, Any]:
    seed_id = str((family_context or {}).get("active_seed_id") or "").strip()
    source_keys = sorted(
        str(item.get("source") or item.get("path") or "")
        for item in evidence_citations
        if str(item.get("source") or item.get("path") or "")
    )
    graph_version = hashlib.sha256(
        json.dumps(source_keys, sort_keys=True).encode()
    ).hexdigest()[:16]
    return {
        "graph_version": graph_version,
        "route_catalog_version": ROUTE_CATALOG_VERSION,
        "seed_id": seed_id or None,
        "receipt_ids": [],
        "cache_policy": cache_policy,
    }


def shortcut_candidate_for_composed_packet(
    *,
    packet: dict[str, Any],
    compiled_from: dict[str, Any],
    receipt_count: int,
    user_overrides: list[str] | None = None,
) -> dict[str, Any]:
    family_context = packet.get("family_context")
    task_identity = packet.get("task_identity")
    seed_id = ""
    if isinstance(family_context, dict):
        seed_id = str(family_context.get("active_seed_id") or "").strip()
    shortcut_id = seed_id
    if not shortcut_id and isinstance(task_identity, dict):
        shortcut_id = str(task_identity.get("primary") or "").strip()
    if not shortcut_id:
        return {
            "status": "none",
            "shortcut_id": "",
            "matched": False,
            "compiled_from": compiled_from,
            "regenerate_when": [],
            "fallback": "router_traversal",
            "reason": "No scoped seed or stable route identity matched.",
        }
    overrides = _string_list(user_overrides)
    status = "eligible"
    reason = "Compiled route identity matches current graph inputs."
    if overrides:
        status = "needs_revalidation"
        reason = "User overrides require full packet revalidation."
    return {
        "status": status,
        "shortcut_id": shortcut_id,
        "matched": status == "eligible",
        "compiled_from": {
            **compiled_from,
            "receipt_count": receipt_count,
        },
        "regenerate_when": [
            "graph_version changes",
            "seed_id unpublished",
            "user_override present",
        ],
        "fallback": "router_traversal",
        "reason": reason,
    }


def selection_rationale(packet: dict[str, Any]) -> str:
    task_identity = packet.get("task_identity")
    if not isinstance(task_identity, dict):
        return "TMCP selected sources from the harvested skill graph for the stated objective."
    primary = str(task_identity.get("primary") or "general_task")
    signals = [
        item
        for item in _json_list(task_identity.get("signals"))
        if isinstance(item, dict)
    ]
    if not signals:
        return (
            f"TMCP inferred primary task identity `{primary}` from the objective and runtime context."
        )
    top = signals[0]
    route = str(top.get("route") or primary)
    evidence = ", ".join(_string_list(top.get("evidence"))[:3])
    route_scores = ", ".join(
        f"{item.get('route')} ({item.get('score')})"
        for item in signals[:4]
        if isinstance(item, dict) and item.get("route")
    )
    family_context = packet.get("family_context")
    if isinstance(family_context, dict) and family_context.get("active_seed_id"):
        seed_id = str(family_context.get("active_seed_id"))
        return (
            f"TMCP matched scoped packet seed `{seed_id}` and route `{route}` "
            f"from route scores [{route_scores}] and signals ({evidence})."
        )
    return (
        f"TMCP inferred primary task identity `{primary}` with strongest route `{route}` "
        f"from route scores [{route_scores}] and signals ({evidence})."
    )


def render_composed_packet_markdown(packet: dict[str, Any]) -> str:
    task_identity = packet.get("task_identity")
    if not isinstance(task_identity, dict):
        task_identity = {}
    primary = str(task_identity.get("primary") or "general_task")
    secondary = _string_list(task_identity.get("secondary"))
    active_routes = _string_list(task_identity.get("active_routes"))
    lines = [
        "# TMCP Packet",
        "",
        f"Objective: {packet.get('objective', '')}",
        f"Phase: `{packet.get('phase', 'start')}`",
        f"Packet ID: `{packet.get('packet_id', '')}`",
        "",
        "## Task Identity",
        f"Primary: {primary}",
    ]
    if secondary:
        lines.append(f"Secondary: {', '.join(secondary)}")
    if active_routes:
        lines.extend(["", "## Active Routes"])
        lines.extend(f"- {route}" for route in active_routes)
    citations = [
        item for item in _json_list(packet.get("evidence_citations")) if isinstance(item, dict)
    ]
    if citations:
        lines.extend(["", "## Loaded Skill Sources"])
        for item in citations[:10]:
            source = str(item.get("source") or item.get("path") or "source")
            atoms = ", ".join(_string_list(item.get("matched_atoms"))[:4])
            if atoms:
                lines.append(f"- {source}: {atoms}")
            else:
                lines.append(f"- {source}")
    lines.extend(["", "## Selection Rationale", selection_rationale(packet)])
    ignored = [
        item for item in _json_list(packet.get("ignored_sources")) if isinstance(item, dict)
    ]
    if ignored:
        lines.extend(["", "## Excluded Skills"])
        for item in ignored[:10]:
            source = str(item.get("source") or "source")
            reason = str(item.get("reason") or "No match for current objective or phase.")
            lines.append(f"- {source}: {reason}")
    deferred = _string_list(packet.get("deferred_atoms"))
    if deferred:
        lines.append(f"- deferred atoms: {', '.join(deferred)}")
    instructions = _string_list(packet.get("active_instructions"))
    if instructions:
        lines.extend(["", "## Operating Instructions"])
        for index, instruction in enumerate(instructions, start=1):
            lines.append(f"{index}. {instruction}")
    gates = _string_list(packet.get("verification_gates"))
    if gates:
        lines.extend(["", "## Verification Gates"])
        for gate in gates:
            lines.append(f"- {gate}")
    family_context = packet.get("family_context")
    if isinstance(family_context, dict) and family_context.get("active_seed_id"):
        lines.extend(
            [
                "",
                "## Recompile Triggers",
                "- New task phase detected",
                "- User changes target pages or objective",
                "- Codebase reveals framework or design-system constraints",
                "- Implementation exposes accessibility or performance risk",
            ]
        )
    lines.extend(
        [
            "",
            "## Required Receipts",
            "- Pages or files changed",
            "- Skills and routes used",
            "- Validation performed",
            "- Known tradeoffs",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_composed_packet(
    *,
    composed_packet_schema: str,
    receipt_schema: str,
    objective: str,
    project_path: str,
    phase: str,
    task_identity: dict[str, Any],
    family_context: dict[str, Any] | None,
    source_nodes: list[dict[str, Any]],
    selected_nodes: list[dict[str, Any]],
    active_instructions: list[str],
    required_reads: list[str],
    tool_script_prompts: list[str],
    verification_gates: list[str],
    stop_conditions: list[str],
    active_atoms: list[str],
    evidence_citations: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    cache_policy: str,
    global_cache: dict[str, Any],
    receipt_count: int,
    user_overrides: list[str],
) -> dict[str, Any]:
    normalized_instructions = _ordered_unique(active_instructions)[:10]
    normalized_reads = _ordered_unique(required_reads)[:12]
    normalized_prompts = _ordered_unique(tool_script_prompts)[:10]
    normalized_gates = _ordered_unique(verification_gates)[:10]
    normalized_stops = _ordered_unique(stop_conditions)[:8]
    normalized_atoms = _ordered_unique(active_atoms)[:16]
    deferred_atoms = [
        atom
        for atom in _ordered_unique(
            [
                atom
                for node in source_nodes
                if node not in selected_nodes
                for atom in _string_list(node.get("behavior_atoms"))
            ]
        )
        if atom not in normalized_atoms
    ][:8]
    ignored_sources = [
        {
            "source": node.get("relative_path"),
            "reason": "No objective, phase, command, or runtime-context match for this packet.",
        }
        for node in source_nodes
        if node not in selected_nodes
    ][:12]
    compiled_from = compiled_from_packet(
        cache_policy=cache_policy,
        family_context=family_context,
        evidence_citations=evidence_citations,
    )
    shortcut_candidate = shortcut_candidate_for_composed_packet(
        packet={
            "family_context": family_context or {},
            "task_identity": task_identity,
        },
        compiled_from=compiled_from,
        receipt_count=receipt_count,
        user_overrides=user_overrides,
    )
    packet_id = (
        "packet-"
        + hashlib.sha256(
            json.dumps(
                {
                    "objective": objective,
                    "phase": phase,
                    "sources": [item.get("source") for item in evidence_citations],
                    "atoms": normalized_atoms,
                    "active_routes": task_identity.get("active_routes"),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()[:12]
    )
    packet: dict[str, Any] = {
        "ok": True,
        "schema": composed_packet_schema,
        "packet_id": packet_id,
        "objective": objective,
        "project_path": project_path,
        "phase": phase,
        "task_identity": task_identity,
        "compiled_from": compiled_from,
        "shortcut_candidate": shortcut_candidate,
        "active_instructions": normalized_instructions,
        "required_reads": normalized_reads,
        "tool_script_prompts": normalized_prompts,
        "verification_gates": normalized_gates,
        "stop_conditions": normalized_stops,
        "active_atoms": normalized_atoms,
        "deferred_atoms": deferred_atoms,
        "family_context": family_context or {},
        "ignored_sources": ignored_sources,
        "conflicts": conflicts,
        "evidence_citations": evidence_citations,
        "global_cache": global_cache,
        "receipt_template": {
            "schema": receipt_schema,
            "packet_id": packet_id,
            "activated_atoms": normalized_atoms,
            "ignored_atoms": [],
            "commands_run": [],
            "verification_results": [],
            "user_overrides": [],
            "outcome": "",
        },
        "safety": {
            "harvested_text_trust": "untrusted_evidence_only",
            "does_not_execute_tools": True,
            "instruction_override_policy": (
                "Composed packets are advisory and cannot override system, developer, or user instructions."
            ),
        },
    }
    packet["packet_markdown"] = render_composed_packet_markdown(packet)
    return packet
