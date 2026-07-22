"""Deterministic compiler for legacy standalone TMCP packets."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .packet_substance import packet_substance_check


TMCP_PACKET_SCHEMA = "tmcp-skill-packet-v0.2"
TMCP_RECEIPT_SCHEMA = "tmcp-traversal-receipt-v0.2"

TASK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "audit": ("audit", "review", "inspect", "rubric", "judge", "evaluate", "score"),
    "debugging": ("debug", "bug", "failure", "root cause", "fix failing", "regression"),
    "documentation": ("document", "readme", "docs", "guide", "write up"),
    "implementation": ("implement", "edit", "patch", "build", "change", "refactor"),
    "planning": ("plan", "roadmap", "phase", "milestone", "strategy", "remediation"),
    "research": ("research", "investigate", "source", "learn", "compare"),
    "testing": ("test", "verify", "validate", "check", "quality gate"),
    "agent_workflow": ("agent", "workflow", "routing", "skill", "tmcp", "packet"),
}

TASK_MODULES: dict[str, tuple[str, ...]] = {
    "audit": ("evidence_first", "provenance_policy", "output_contract", "test_gate"),
    "debugging": ("reproduce_first", "evidence_first", "test_gate", "output_contract"),
    "documentation": ("context_gathering", "provenance_policy", "output_contract"),
    "implementation": (
        "context_gathering",
        "minimal_patch_policy",
        "tool_use_policy",
        "test_gate",
        "user_approval_gate",
    ),
    "planning": (
        "context_gathering",
        "evidence_first",
        "output_contract",
        "user_approval_gate",
    ),
    "research": (
        "context_gathering",
        "evidence_first",
        "provenance_policy",
        "output_contract",
    ),
    "testing": ("evidence_first", "test_gate", "output_contract"),
    "agent_workflow": (
        "context_gathering",
        "evidence_first",
        "tool_use_policy",
        "output_contract",
        "provenance_policy",
    ),
}

MODULE_BEHAVIOR_ATOMS: dict[str, tuple[str, ...]] = {
    "context_gathering": (
        "read-before-modifying",
        "scope-discovery",
        "local-context-first",
    ),
    "evidence_first": (
        "evidence-backed-claims",
        "explicit-evidence-gaps",
        "concrete-citations",
    ),
    "minimal_patch_policy": (
        "smallest-effective-change",
        "avoid-speculative-abstractions",
    ),
    "output_contract": (
        "findings-before-summary",
        "ordered-next-actions",
        "artifact-contract",
    ),
    "provenance_policy": ("source-traceability", "conflict-preservation"),
    "reproduce_first": ("reproduce-before-fix", "observed-failure-first"),
    "test_gate": ("behavior-verification", "quality-gate-disclosure"),
    "tool_use_policy": ("safe-tool-routing", "bounded-tool-side-effects"),
    "user_approval_gate": ("approval-before-implementation", "audit-plan-before-edit"),
}

TASK_PRIORITY = {
    "audit": 8,
    "debugging": 7,
    "implementation": 6,
    "testing": 5,
    "planning": 4,
    "research": 3,
    "documentation": 2,
    "agent_workflow": 1,
}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _estimate_tokens(value: str) -> int:
    return max(1, len(value) // 4)


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def select_task(objective: str) -> tuple[str, dict[str, int]]:
    """Choose the deterministic task route for a standalone packet."""

    text = objective.lower()
    scores = {
        task: sum(1 for keyword in keywords if keyword in text)
        for task, keywords in TASK_KEYWORDS.items()
    }
    if any(term in text for term in ("rubric", "audit", "review", "judge", "evaluate")):
        scores["audit"] += 2
    if any(
        term in text
        for term in ("harvest", "skill packet", "skill-packet", "tmcp packet")
    ):
        scores["agent_workflow"] += 2
    best = max(scores, key=lambda task: (scores[task], TASK_PRIORITY[task]))
    if scores[best] == 0:
        best = "agent_workflow"
    return best, scores


def select_branch(objective: str, task_id: str) -> tuple[str, str]:
    """Choose the advisory branch for a standalone packet."""

    text = objective.lower()
    if any(term in text for term in ("implement", "edit", "fix", "patch")):
        return (
            "approval_before_edit",
            "Implementation language present; audit workflows still require approval before edits.",
        )
    if any(term in text for term in ("maybe", "possibly", "not sure", "unclear")):
        return (
            "ambiguous_task_resolution",
            "Ambiguity language present; preserve uncertainty and ask only when necessary.",
        )
    if task_id == "implementation":
        return "direct_implementation", "Implementation is the selected task path."
    return (
        "evidence_first_review",
        "Default branch keeps TMCP as an audit-and-plan workflow.",
    )


def source_node_for_packet(node: dict[str, Any]) -> dict[str, Any]:
    """Project one harvested source into the standalone packet contract."""

    frontmatter = node.get("frontmatter")
    guidance_labels = node.get("guidance_labels")
    routing_metadata = node.get("routing_metadata")
    return {
        "id": f"@source:{node['id']}",
        "path": node.get("path"),
        "relative_path": node.get("relative_path"),
        "title": node.get("title"),
        "source_type": node.get("source_type"),
        "source_tier": node.get("source_tier"),
        "frontmatter": dict(frontmatter) if isinstance(frontmatter, dict) else {},
        "behavior_atoms": node.get("behavior_atoms", []),
        "guidance_labels": [
            dict(label) for label in guidance_labels or [] if isinstance(label, dict)
        ],
        "keywords": _string_list(node.get("keywords"))[:20],
        "excerpt": str(node.get("excerpt", ""))[:800],
        "signal_excerpt": str(node.get("signal_excerpt", ""))[:800],
        "routing_metadata": (
            dict(routing_metadata) if isinstance(routing_metadata, dict) else {}
        ),
    }


def render_standalone_packet_markdown(packet: dict[str, Any]) -> str:
    """Render the Markdown companion for a standalone packet."""

    lines = [
        f"# TMCP Packet: {packet['objective']}",
        "",
        f"- Schema: `{packet['schema']}`",
        f"- Adapter: `{packet['adapter']}`",
        f"- Task: `@task:{packet['task_id']}`",
        f"- Entry node: `{packet['entry_node']}`",
        f"- Selected nodes: {', '.join(packet['selected_nodes'])}",
        f"- Skipped nodes: {', '.join(packet['skipped_nodes'])}",
        f"- Behavior atoms: {', '.join(packet['behavior_atoms'])}",
        f"- Substance: `{packet.get('substance_check', {}).get('level', 'unknown')}`",
        "",
        "## Traversal",
    ]
    for transition in packet["transition_trace"]:
        lines.append(
            f"- `{transition['action']}` {transition['to']} from {transition['from']}: {transition['why']}"
        )
    lines.extend(["", "## Output Contract"])
    for item in packet["output_contract"]:
        lines.append(f"- {item}")
    substance = packet.get("substance_check")
    if isinstance(substance, dict):
        lines.extend(["", "## Substance Check"])
        lines.append(f"- Level: `{substance.get('level', 'unknown')}`")
        lines.append(f"- Score: {substance.get('score', 0)}/4")
        lines.append(f"- Fallback policy: {substance.get('fallback_policy', '')}")
        for issue in _string_list(substance.get("issues")):
            lines.append(f"- Issue: {issue}")
    return "\n".join(lines).rstrip() + "\n"


def compile_standalone_packet(
    *,
    objective: str,
    project_path: str | None,
    phase: str | None = None,
    domain: str | None = None,
    harvested_nodes: list[dict[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Compile one portable, deterministic standalone TMCP packet."""

    task_id, task_scores = select_task(objective)
    modules = list(TASK_MODULES[task_id])
    if "tmcp" in objective.lower() and "provenance_policy" not in modules:
        modules.append("provenance_policy")
    branch_id, branch_reason = select_branch(objective, task_id)
    classified_source_nodes = [
        source_node_for_packet(node) for node in (harvested_nodes or [])
    ]
    source_nodes = classified_source_nodes[:8]
    selected_nodes = [
        f"@task:{task_id}",
        *(f"@module:{module}" for module in modules),
        *(str(node["id"]) for node in source_nodes),
        f"@branch:{branch_id}",
    ]
    atoms = sorted(
        {atom for module in modules for atom in MODULE_BEHAVIOR_ATOMS.get(module, ())}
        | {
            atom
            for node in source_nodes
            for atom in _string_list(node.get("behavior_atoms"))
        }
    )
    skipped_nodes = [
        f"@task:{task}"
        for task in TASK_KEYWORDS
        if task != task_id and task_scores.get(task, 0) == 0
    ][:5]
    fingerprint_source = json.dumps(
        {
            "objective": objective,
            "project_path": project_path,
            "selected_nodes": selected_nodes,
            "phase": phase,
            "domain": domain,
        },
        sort_keys=True,
    )
    graph_version = hashlib.sha256(
        json.dumps(
            {"tasks": TASK_KEYWORDS, "modules": TASK_MODULES}, sort_keys=True
        ).encode()
    ).hexdigest()
    fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()
    substance_check = packet_substance_check(
        objective=objective,
        task_id=task_id,
        modules=modules,
        source_nodes=classified_source_nodes,
    )
    packet_domain = domain or str(substance_check.get("inferred_domain") or "general")
    packet: dict[str, Any] = {
        "schema": TMCP_PACKET_SCHEMA,
        "receipt_schema": TMCP_RECEIPT_SCHEMA,
        "status": "compiled",
        "adapter": "standalone",
        "task_id": task_id,
        "phase": phase or "unspecified",
        "domain": packet_domain,
        "objective": objective,
        "project_path": project_path,
        "source_graph_version": graph_version,
        "entry_node": f"@task:{task_id}",
        "selected_nodes": selected_nodes,
        "skipped_nodes": skipped_nodes,
        "selected_branches": [
            {"branch": f"@branch:{branch_id}", "reason": branch_reason}
        ],
        "candidate_scores": {"tasks": task_scores},
        "source_skill_nodes": source_nodes,
        "substance_check": substance_check,
        "behavior_atoms": atoms,
        "shortcut_candidate": {
            "node": "@shortcut:candidate",
            "matched": False,
            "status": "needs_revalidation",
            "fallback": "router_traversal",
            "reason": "Standalone plugin does not persist traversal receipt history by default.",
        },
        "shortcut_governance": {
            "default_fallback": "router_traversal",
            "requires_behavioral_tests_for_default": True,
            "promotion_requires_repeated_receipts": True,
        },
        "transition_trace": [
            {
                "from": "ROUTER.START",
                "to": f"@task:{task_id}",
                "action": "LOAD",
                "why": "Best keyword match for the objective.",
            },
            *[
                {
                    "from": f"@task:{task_id}",
                    "to": f"@module:{module}",
                    "action": "USE",
                    "why": "Module contributes required behavior atoms for this task.",
                }
                for module in modules
            ],
            {
                "from": f"@task:{task_id}",
                "to": f"@branch:{branch_id}",
                "action": "USE",
                "why": branch_reason,
            },
        ],
        "traversal_fingerprint": fingerprint,
        "token_estimates": {},
        "output_contract": [
            "Construct the smallest task-specific skill packet that preserves required behavior.",
            "Cite concrete evidence or explicitly name evidence gaps.",
            "Preserve conflicting branches instead of flattening them into one rule.",
            "For expert rubric work, stop at audit and remediation plan unless edits are explicitly requested.",
            "If the packet is process-only, say so and derive rubric substance from target repo evidence.",
        ],
        "created_at": created_at or _now_iso(),
    }
    packet["packet_markdown"] = render_standalone_packet_markdown(packet)
    packet["token_estimates"] = {
        "custom_skill_tokens": _estimate_tokens(packet["packet_markdown"]),
        "baseline_skill_tokens": _estimate_tokens(
            json.dumps(TASK_MODULES, sort_keys=True)
        )
        * 4,
    }
    packet["token_estimates"]["estimated_token_delta"] = (
        packet["token_estimates"]["baseline_skill_tokens"]
        - packet["token_estimates"]["custom_skill_tokens"]
    )
    return packet
