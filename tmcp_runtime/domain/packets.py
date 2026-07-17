"""Final composed-packet construction, provenance, and presentation policy."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .harvest_nodes import node_source_role, source_role_is_activation_eligible
from .receipts import build_receipt_template
from .routes import KNOWN_ROUTE_IDS, ROUTE_CATALOG_VERSION


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
    selected_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    seed_id = str((family_context or {}).get("active_seed_id") or "").strip()
    graph_inputs: dict[str, str] = {}
    for item in evidence_citations:
        source = str(item.get("source") or item.get("path") or "")
        if source:
            graph_inputs[source] = str(item.get("content_digest") or "")
    for node in selected_nodes or []:
        source = str(node.get("relative_path") or node.get("path") or "")
        if source:
            graph_inputs[source] = str(
                node.get("content_digest") or graph_inputs.get(source) or ""
            )
    source_keys = [
        {"source": source, "content_digest": graph_inputs[source] or None}
        for source in sorted(graph_inputs)
    ]
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
    routing_status = ""
    validated_routes: list[str] = []
    confidence = 0.0
    task_primary = ""
    if isinstance(task_identity, dict):
        task_primary = str(task_identity.get("primary") or "").strip()
        routing_status = str(task_identity.get("routing_status") or "").strip()
        validated_routes = _string_list(task_identity.get("validated_routes"))
        if not routing_status and not validated_routes:
            validated_routes = _string_list(task_identity.get("active_routes"))
        try:
            confidence = float(task_identity.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
    if task_primary == "general_task" and confidence <= 0.0:
        return {
            "status": "ineligible",
            "shortcut_id": shortcut_id,
            "matched": False,
            "compiled_from": {
                **compiled_from,
                "receipt_count": receipt_count,
            },
            "regenerate_when": [
                "task identity gains positive confidence",
                "graph_version changes",
                "user_override present",
            ],
            "fallback": "router_traversal",
            "reason": (
                "Zero-confidence general_task identities cannot become reusable shortcuts."
            ),
        }
    has_validated_route = bool(set(validated_routes).intersection(KNOWN_ROUTE_IDS))
    if not seed_id and routing_status and not (
        routing_status == "catalog_match" and has_validated_route
    ):
        return {
            "status": "ineligible",
            "shortcut_id": shortcut_id,
            "matched": False,
            "compiled_from": {**compiled_from, "receipt_count": receipt_count},
            "regenerate_when": [
                "task identity gains a validated active route",
                "graph_version changes",
                "user_override present",
            ],
            "fallback": "router_traversal",
            "reason": (
                "Compound or unresolved task identities cannot become reusable shortcuts "
                "without a scoped seed or validated active route."
            ),
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
    routing_status = str(task_identity.get("routing_status") or "")
    facets = _string_list(task_identity.get("intent_facets"))
    signals = [
        item
        for item in _json_list(task_identity.get("signals"))
        if isinstance(item, dict)
    ]
    if not signals:
        if routing_status == "compound_fallback":
            return (
                "TMCP recognized a compound task across facets "
                f"({', '.join(facets) or 'unspecified'}); no catalog route cleared "
                "the activation threshold, so selection remains source-backed."
            )
        return f"TMCP inferred primary task identity `{primary}` from the objective and runtime context."
    if routing_status == "compound_fallback":
        return (
            "TMCP recognized a compound task across facets "
            f"({', '.join(facets) or 'unspecified'}); route signals remain advisory "
            "until a catalog route clears the activation threshold."
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
    routing_status = str(task_identity.get("routing_status") or "")
    facets = _string_list(task_identity.get("intent_facets"))
    if routing_status:
        lines.append(f"Routing status: {routing_status}")
    if facets:
        lines.append(f"Intent facets: {', '.join(facets)}")
    if secondary:
        lines.append(f"Secondary: {', '.join(secondary)}")
    if active_routes:
        lines.extend(["", "## Active Routes"])
        lines.extend(f"- {route}" for route in active_routes)
    composition_plan = packet.get("composition_plan")
    if isinstance(composition_plan, dict):
        lines.extend(
            [
                "",
                "## Composition Plan",
                f"Recipe: `{composition_plan.get('composition_plan_id', '')}`",
                "Graph: `"
                + str(
                    dict(composition_plan.get("provenance") or {}).get(
                        "graph_digest", ""
                    )
                )
                + "`",
            ]
        )
        for stage in _json_list(composition_plan.get("ordered_stages")):
            if not isinstance(stage, dict):
                continue
            status = str(stage.get("status") or "deferred")
            node_ids = ", ".join(_string_list(stage.get("node_ids")))
            lines.append(f"- {stage.get('stage_id', 'stage')} [{status}]: {node_ids}")
            if status == "deferred":
                conditions = "; ".join(_string_list(stage.get("entry_conditions")))
                if conditions:
                    lines.append(f"  - enter when: {conditions}")
        coverage = composition_plan.get("coverage")
        if isinstance(coverage, dict):
            gaps = _string_list(coverage.get("unresolved_gaps"))
            if gaps:
                lines.append(f"- unresolved gaps: {', '.join(gaps)}")
    citations = [
        item
        for item in _json_list(packet.get("evidence_citations"))
        if isinstance(item, dict)
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
        item
        for item in _json_list(packet.get("ignored_sources"))
        if isinstance(item, dict)
    ]
    if ignored:
        lines.extend(["", "## Excluded Skills"])
        for item in ignored[:10]:
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
                and source_role_is_activation_eligible(node_source_role(node))
                for atom in _string_list(node.get("behavior_atoms"))
            ]
        )
        if atom not in normalized_atoms
    ][:8]
    ignored_sources = [
        {
            "source": node.get("relative_path"),
            "source_role": node_source_role(node),
            "reason": (
                "Evidence-only source remains harvestable but is inactive unless explicitly scoped."
                if node_source_role(node) == "evidence_only"
                else "Supporting reference may be read as evidence but cannot activate behavior."
                if node_source_role(node) == "supporting_reference"
                else "No objective, phase, command, or runtime-context match for this packet."
            ),
        }
        for node in source_nodes
        if node not in selected_nodes
    ][:12]
    digest_by_source: dict[str, str] = {}
    for node in selected_nodes:
        digest = str(node.get("content_digest") or "")
        if not digest:
            continue
        for source in (node.get("relative_path"), node.get("path")):
            source_key = str(source or "")
            if source_key:
                digest_by_source[source_key] = digest
    normalized_citations: list[dict[str, Any]] = []
    for citation in evidence_citations:
        normalized = dict(citation)
        source = str(citation.get("source") or citation.get("path") or "")
        digest = str(
            citation.get("content_digest") or digest_by_source.get(source) or ""
        )
        if digest:
            normalized["content_digest"] = digest
        normalized_citations.append(normalized)
    compiled_from = compiled_from_packet(
        cache_policy=cache_policy,
        family_context=family_context,
        evidence_citations=normalized_citations,
        selected_nodes=selected_nodes,
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
                    "sources": [item.get("source") for item in normalized_citations],
                    "graph_version": compiled_from["graph_version"],
                    "atoms": normalized_atoms,
                    "task_identity": {
                        "primary": task_identity.get("primary"),
                        "active_routes": task_identity.get("active_routes"),
                        "validated_routes": task_identity.get("validated_routes"),
                        "intent_facets": task_identity.get("intent_facets"),
                        "routing_status": task_identity.get("routing_status"),
                        "route_catalog_version": task_identity.get(
                            "route_catalog_version"
                        ),
                    },
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
        "evidence_citations": normalized_citations,
        "composition_diagnostics": {
            "source_role_counts": {
                role: sum(1 for node in source_nodes if node_source_role(node) == role)
                for role in (
                    "governing_instruction",
                    "active_skill",
                    "supporting_reference",
                    "evidence_only",
                )
            },
            "composition_ineligible_sources": [
                {
                    "source": node.get("relative_path"),
                    "source_role": node_source_role(node),
                    "reason": (
                        "Source role cannot activate packet behavior."
                        if not source_role_is_activation_eligible(
                            node_source_role(node)
                        )
                        else "Source was eligible but did not match this packet."
                    ),
                }
                for node in source_nodes
                if not source_role_is_activation_eligible(node_source_role(node))
            ][:20],
        },
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
    packet["packet_markdown"] = render_composed_packet_markdown(packet)
    return packet
