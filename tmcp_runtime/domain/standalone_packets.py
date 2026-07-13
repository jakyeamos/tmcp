"""Deterministic compiler for legacy standalone TMCP packets."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


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

PROCESS_ONLY_MODULES = {
    "context_gathering",
    "evidence_first",
    "output_contract",
    "provenance_policy",
    "test_gate",
    "tool_use_policy",
    "user_approval_gate",
}

PLAYBOOK_ACTION_TERMS = (
    "audit",
    "blocker",
    "check",
    "criterion",
    "criteria",
    "evidence",
    "gate",
    "inspect",
    "must",
    "readiness",
    "require",
    "review",
    "risk",
    "score",
    "validate",
    "verify",
)

DOMAIN_PLAYBOOK_TERMS = (
    "accessibility",
    "audit log",
    "auditability",
    "auth",
    "calculation",
    "compliance",
    "deployment",
    "evidence gate",
    "government",
    "legal",
    "migration",
    "observability",
    "permission",
    "privacy",
    "public sector",
    "readiness",
    "release blocker",
    "retention",
    "rollback",
    "security",
    "tenant",
    "uat",
)

SUBSTANTIVE_SOURCE_TYPES = {
    "agent_operating_contract",
    "cursor_rule",
    "github_process",
    "project_documentation",
    "skill_definition",
    "workflow_prompt",
}

NON_SUBSTANTIVE_SOURCE_NAME_TERMS = (
    "changelog",
    "release_checklist",
    "verification",
)

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

    return {
        "id": f"@source:{node['id']}",
        "path": node.get("path"),
        "relative_path": node.get("relative_path"),
        "title": node.get("title"),
        "source_type": node.get("source_type"),
        "source_tier": node.get("source_tier"),
        "behavior_atoms": node.get("behavior_atoms", []),
        "keywords": _string_list(node.get("keywords"))[:20],
        "excerpt": str(node.get("excerpt", ""))[:800],
    }


def packet_substance_check(
    *,
    objective: str,
    task_id: str,
    modules: list[str],
    source_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assess whether standalone packet sources contain domain playbook substance."""

    source_texts = [
        " ".join(
            [
                str(node.get("title", "")),
                str(node.get("source_type", "")),
                " ".join(_string_list(node.get("keywords"))),
                str(node.get("excerpt", "")),
            ]
        ).lower()
        for node in source_nodes
    ]
    source_combined = " ".join(source_texts)
    objective_lower = objective.lower()
    requested_anchor_terms = sorted(
        {
            term
            for term in (
                "government",
                "public sector",
                "public-sector",
                "compliance",
                "legal",
                "calculation",
            )
            if term in objective_lower
        }
    )
    matched_domain_terms = sorted(
        {term for term in DOMAIN_PLAYBOOK_TERMS if term in source_combined}
    )
    matched_action_terms = sorted(
        {term for term in PLAYBOOK_ACTION_TERMS if term in source_combined}
    )
    substantive_nodes: list[dict[str, Any]] = []
    for node, text in zip(source_nodes, source_texts):
        domain_hits = [term for term in DOMAIN_PLAYBOOK_TERMS if term in text]
        action_hits = [term for term in PLAYBOOK_ACTION_TERMS if term in text]
        has_required_anchor = not requested_anchor_terms or any(
            term in text for term in requested_anchor_terms
        )
        has_substantive_type = (
            str(node.get("source_type", "")) in SUBSTANTIVE_SOURCE_TYPES
        )
        name_scope = " ".join(
            [
                str(node.get("path", "")),
                str(node.get("relative_path", "")),
                str(node.get("title", "")),
            ]
        ).lower()
        is_non_substantive = any(
            term in name_scope for term in NON_SUBSTANTIVE_SOURCE_NAME_TERMS
        )
        if (
            has_substantive_type
            and not is_non_substantive
            and has_required_anchor
            and len(domain_hits) >= 2
            and len(action_hits) >= 2
        ):
            substantive_nodes.append(
                {
                    "id": node.get("id"),
                    "path": node.get("path"),
                    "title": node.get("title"),
                    "matched_domain_terms": sorted(set(domain_hits))[:8],
                    "matched_action_terms": sorted(set(action_hits))[:8],
                }
            )
    process_modules = [module for module in modules if module in PROCESS_ONLY_MODULES]
    score = 0
    if source_nodes:
        score += 1
    if matched_action_terms:
        score += 1
    if len(matched_domain_terms) >= 2:
        score += 1
    if substantive_nodes:
        score += 1
    score = min(score, 4)
    if score >= 3 and substantive_nodes:
        level = "source_backed_playbook"
    elif score >= 2:
        level = "thin_domain_signals"
    else:
        level = "process_only"
    issues: list[str] = []
    if not source_nodes:
        issues.append(
            "No harvested source nodes were available for task-specific playbook content."
        )
    if not substantive_nodes:
        issues.append(
            "Selected TMCP modules are mostly process scaffolding, not a concrete domain playbook."
        )
    if task_id == "audit" and level != "source_backed_playbook":
        issues.append(
            "Audit rubric substance should be derived from target repo evidence and cited artifacts."
        )
    fallback_policy = (
        "Use TMCP for routing, evidence discipline, and output contract; derive rubric substance from target repo docs, code, tests, risk registers, and readiness gates."
        if level != "source_backed_playbook"
        else "Use harvested source nodes as substantive rubric guidance, then verify every finding against target evidence."
    )
    return {
        "schema": "tmcp-packet-substance-v0.1",
        "level": level,
        "score": score,
        "has_domain_playbook": level == "source_backed_playbook",
        "source_node_count": len(source_nodes),
        "substantive_source_count": len(substantive_nodes),
        "process_only_modules": process_modules,
        "matched_domain_terms": matched_domain_terms[:12],
        "matched_action_terms": matched_action_terms[:12],
        "requested_anchor_terms": requested_anchor_terms,
        "substantive_source_nodes": substantive_nodes[:5],
        "issues": issues,
        "fallback_policy": fallback_policy,
        "recommended_next_step": (
            "Harvest the completed review into a reusable TMCP skill after the audit."
            if level != "source_backed_playbook"
            else "Run the review with evidence-backed scoring and preserve source citations."
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
    source_nodes = [
        source_node_for_packet(node) for node in (harvested_nodes or [])[:8]
    ]
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
        source_nodes=source_nodes,
    )
    packet: dict[str, Any] = {
        "schema": TMCP_PACKET_SCHEMA,
        "receipt_schema": TMCP_RECEIPT_SCHEMA,
        "status": "compiled",
        "adapter": "standalone",
        "task_id": task_id,
        "phase": phase or "unspecified",
        "domain": domain or "general",
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
