"""Final composed-packet construction, provenance, and presentation policy."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .receipts import build_receipt_template
from .routes import ROUTE_CATALOG_VERSION


OBSERVABILITY_REVIEW_SOURCE_PATH_TERMS = (
    "audit",
    "rubric",
    "readiness",
    "postmortem",
    "pr-risk",
    "risk-review",
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
    admission = packet.get("admission")
    if isinstance(admission, dict) and admission.get("action") == "bypass":
        return {
            "status": "none",
            "shortcut_id": "",
            "matched": False,
            "compiled_from": compiled_from,
            "regenerate_when": [],
            "fallback": "router_traversal",
            "reason": "Admission bypass produced no reusable compiled route.",
        }
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
        return f"TMCP inferred primary task identity `{primary}` from the objective and runtime context."
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
    admission = packet.get("admission")
    if isinstance(admission, dict):
        lines.extend(
            [
                "",
                "## Admission",
                f"Decision: {admission.get('action', 'forced')}",
                f"Expected value: {admission.get('expected_value', 'unknown')}",
            ]
        )
        if admission.get("action") == "bypass":
            reasons = ", ".join(_string_list(admission.get("reasons"))[:3])
            if reasons:
                lines.append(f"Reason: {reasons}")
            return "\n".join(lines).rstrip() + "\n"
    if secondary:
        lines.append(f"Secondary: {', '.join(secondary)}")
    if active_routes:
        lines.extend(["", "## Active Routes"])
        lines.extend(f"- {route}" for route in active_routes)
    citations = [
        item
        for item in _json_list(packet.get("evidence_citations"))
        if isinstance(item, dict)
    ]
    if citations:
        lines.extend(["", "## Loaded Skill Sources"])
        for item in citations[:6]:
            source = str(item.get("source") or item.get("path") or "source")
            atoms = ", ".join(_string_list(item.get("matched_atoms"))[:4])
            if atoms:
                lines.append(f"- {source}: {atoms}")
            else:
                lines.append(f"- {source}")
    lines.extend(["", "## Selection Rationale", selection_rationale(packet)])
    ignored = [
        item
        for item in _json_list(packet.get("ignored_sources"))
        if isinstance(item, dict)
    ]
    if ignored:
        lines.extend(["", "## Excluded Skills"])
        for item in ignored[:3]:
            source = str(item.get("source") or "source")
            reason = str(
                item.get("reason") or "No match for current objective or phase."
            )
            lines.append(f"- {source}: {reason}")
    deferred = _string_list(packet.get("deferred_atoms"))
    if deferred:
        lines.append(f"- deferred atoms: {', '.join(deferred)}")
    instructions = _string_list(packet.get("active_instructions"))
    if instructions:
        lines.extend(["", "## Operating Instructions"])
        for index, instruction in enumerate(instructions[:6], start=1):
            lines.append(f"{index}. {instruction}")
    gates = _string_list(packet.get("verification_gates"))
    if gates:
        lines.extend(["", "## Verification Gates"])
        for gate in gates[:6]:
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
    admission: dict[str, Any] | None = None,
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
            "admission": admission or {},
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
        "status": "bypassed" if (admission or {}).get("action") == "bypass" else "composed",
        "admission": admission or {
            "mode": "forced",
            "action": "forced",
            "recommended_action": "compose",
            "expected_value": "unknown",
            "reasons": ["legacy_explicit_composition"],
        },
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
        "receipt_template": build_receipt_template(
            packet_id=packet_id,
            activated_atoms=normalized_atoms,
        ),
        "safety": {
            "harvested_text_trust": "untrusted_evidence_only",
            "does_not_execute_tools": True,
            "instruction_override_policy": (
                "Composed packets are advisory and cannot override system, developer, or user instructions."
            ),
        },
    }
    rendered = render_composed_packet_markdown(packet)
    if len(rendered) > 2500:
        compact_view = dict(packet)
        compact_view["objective"] = objective[:500]
        compact_view["evidence_citations"] = evidence_citations[:4]
        compact_view["ignored_sources"] = []
        compact_view["deferred_atoms"] = []
        compact_view["active_instructions"] = normalized_instructions[:4]
        compact_view["verification_gates"] = normalized_gates[:4]
        compact_view["family_context"] = {}
        rendered = render_composed_packet_markdown(compact_view)
    if len(rendered) > 2500:
        rendered = rendered[:2490].rsplit("\n", 1)[0] + "\n...\n"
    packet["packet_markdown"] = rendered
    packet["packet_budget"] = {
        "max_markdown_chars": 2500,
        "markdown_chars": len(packet["packet_markdown"]),
        "within_budget": len(packet["packet_markdown"]) <= 2500,
        "max_sources": 6,
    }
    source_paths = [
        str(item.get("source") or item.get("path") or "").lower()
        for item in evidence_citations
        if isinstance(item, dict)
    ]
    packet["observability"] = {
        "policy": "local_ephemeral_redacted",
        "persistent_telemetry": False,
        "admission_action": packet["admission"].get("action"),
        "route_confidence": packet["admission"].get("route_confidence"),
        "selected_source_count": len(source_paths),
        "review_source_count": sum(
            any(term in path for term in OBSERVABILITY_REVIEW_SOURCE_PATH_TERMS)
            for path in source_paths
        ),
        "test_fixture_source_count": sum(
            any(part in path.split("/") for part in ("test", "tests", "fixture", "fixtures"))
            for path in source_paths
        ),
        "packet_markdown_chars": len(packet["packet_markdown"]),
    }
    return packet
