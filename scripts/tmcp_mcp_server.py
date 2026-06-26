#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import fnmatch
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from tmcp_mcp_framing import read_message, write_message  # noqa: E402
from tmcp_redaction import merge_redactions, redact_sensitive_text  # noqa: E402

AIOS_ROOT = Path(os.environ.get("AIOS_ROOT", "~/AIOS")).expanduser()

TMCP_PACKET_SCHEMA = "tmcp-skill-packet-v0.2"
TMCP_RECEIPT_SCHEMA = "tmcp-traversal-receipt-v0.2"
RUBRIC_SCHEMA = "tmcp-expert-rubric-v0.1"
AUDIT_REPORT_SCHEMA = "tmcp-expert-audit-report-v0.1"
REMEDIATION_PLAN_SCHEMA = "tmcp-expert-remediation-plan-v0.1"
IMPLEMENTATION_HANDOFF_SCHEMA = "tmcp-expert-implementation-handoff-v0.1"

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
    "planning": ("context_gathering", "evidence_first", "output_contract", "user_approval_gate"),
    "research": ("context_gathering", "evidence_first", "provenance_policy", "output_contract"),
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
    "context_gathering": ("read-before-modifying", "scope-discovery", "local-context-first"),
    "evidence_first": ("evidence-backed-claims", "explicit-evidence-gaps", "concrete-citations"),
    "minimal_patch_policy": ("smallest-effective-change", "avoid-speculative-abstractions"),
    "output_contract": ("findings-before-summary", "ordered-next-actions", "artifact-contract"),
    "provenance_policy": ("source-traceability", "conflict-preservation"),
    "reproduce_first": ("reproduce-before-fix", "observed-failure-first"),
    "test_gate": ("behavior-verification", "quality-gate-disclosure"),
    "tool_use_policy": ("safe-tool-routing", "bounded-tool-side-effects"),
    "user_approval_gate": ("approval-before-implementation", "audit-plan-before-edit"),
}

DEFAULT_HARVEST_INCLUDE_GLOBS = (
    "**/SKILL.md",
    "**/AGENTS.md",
    "**/CLAUDE.md",
    "**/README.md",
    "**/.cursorrules",
    "**/.cursor/rules/**/*.md",
    "**/.github/**/*.md",
    "**/docs/**/*.md",
    "**/doc/**/*.md",
    "**/.planning/**/*.md",
    "**/planning/**/*.md",
    "**/plans/**/*.md",
    "**/workflows/**/*.md",
    "**/*.md",
)

DEFAULT_HARVEST_EXCLUDE_DIR_NAMES = {
    ".DS_Store",
    ".cache",
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".turbo",
    ".venv",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
    "venv",
}

DEFAULT_HARVEST_EXCLUDE_GLOBS = (
    "**/.codex/plugins/cache/**",
    "**/.agents/plugins/cache/**",
    "**/.git/**",
    "**/node_modules/**",
    "**/dist/**",
    "**/build/**",
    "**/.next/**",
    "**/coverage/**",
    "**/package-lock.json",
    "**/pnpm-lock.yaml",
    "**/yarn.lock",
)

HARVEST_SOURCE_TYPE_ATOMS: dict[str, tuple[str, ...]] = {
    "skill_definition": ("skill-routing", "behavior-preservation", "source-traceability"),
    "agent_operating_contract": (
        "agent-operating-contract",
        "instruction-precedence",
        "source-traceability",
    ),
    "cursor_rule": ("editor-rule", "workflow-routing", "source-traceability"),
    "github_process": ("repository-process", "quality-gate-disclosure"),
    "project_documentation": ("project-context", "source-grounding"),
    "workflow_prompt": ("workflow-routing", "artifact-contract"),
    "markdown_process_doc": ("process-documentation", "source-grounding"),
}

PROFILE_DIMENSIONS: dict[str, list[dict[str, Any]]] = {
    "visual_polish": [
        {
            "id": "surface_hierarchy",
            "name": "Surface Hierarchy",
            "weight": 4,
            "expectations": [
                "Screen, file, or screenshot evidence showing primary and supporting regions."
            ],
            "questions": [
                "Is there one dominant work region?",
                "Are cards used only where they frame real repeated objects?",
            ],
        },
        {
            "id": "interaction_architecture",
            "name": "Interaction Architecture",
            "weight": 4,
            "expectations": [
                "Evidence for containers, loading states, empty states, overlays, and actions."
            ],
            "questions": [
                "Does the container match the task?",
                "Are states decision-useful instead of decorative?",
            ],
        },
        {
            "id": "data_realism",
            "name": "Data Realism",
            "weight": 4,
            "expectations": [
                "Evidence for source, freshness, deterministic data, and non-vanity metrics."
            ],
            "questions": [
                "Are metrics credible?",
                "Are visuals driven by real state rather than decoration?",
            ],
        },
        {
            "id": "product_evidence",
            "name": "Product Evidence",
            "weight": 3,
            "expectations": [
                "Evidence that the first screen reveals the actual product, object, or state."
            ],
            "questions": [
                "Can a viewer understand the product from the first screen?",
                "Is decoration replacing product proof?",
            ],
        },
        {
            "id": "design_system_fit",
            "name": "Design System Fit",
            "weight": 3,
            "expectations": [
                "Evidence for tokens, component conventions, typography, spacing, and states."
            ],
            "questions": [
                "Does the surface follow local tokens?",
                "Are generic utility colors or defaults leaking through?",
            ],
        },
    ],
    "security_privacy": [
        {
            "id": "secret_exposure",
            "name": "Secret Exposure",
            "weight": 4,
            "expectations": ["Evidence for env, logs, fixtures, configs, and generated artifacts."],
            "questions": ["Can credentials leak through logs?", "Are sensitive values redacted?"],
        },
        {
            "id": "permission_boundary",
            "name": "Permission Boundary",
            "weight": 4,
            "expectations": ["Evidence for file, network, auth, database, and tool side effects."],
            "questions": ["Are mutations explicit?", "Are privileged operations approval-gated?"],
        },
        {
            "id": "data_flow_privacy",
            "name": "Data Flow Privacy",
            "weight": 4,
            "expectations": ["Evidence for inputs, persistence, retention, and outbound data flow."],
            "questions": ["Is sensitive data minimized?", "Can retained data be audited?"],
        },
        {
            "id": "supply_chain",
            "name": "Supply Chain",
            "weight": 3,
            "expectations": ["Evidence for dependency changes, lockfiles, and provenance."],
            "questions": ["Are dependencies justified?", "Do lockfiles match repo policy?"],
        },
    ],
    "developer_experience": [
        {
            "id": "command_discoverability",
            "name": "Command Discoverability",
            "weight": 4,
            "expectations": ["Evidence for setup, test, lint, typecheck, build, and run commands."],
            "questions": ["Can a developer find the right commands?", "Do docs match scripts?"],
        },
        {
            "id": "validation_loop",
            "name": "Validation Loop",
            "weight": 4,
            "expectations": ["Evidence for fast targeted checks and complete release checks."],
            "questions": ["Is the inner loop fast?", "Are failures actionable?"],
        },
        {
            "id": "interface_clarity",
            "name": "Interface Clarity",
            "weight": 3,
            "expectations": ["Evidence for API, CLI, schema, errors, and examples."],
            "questions": ["Are public interfaces predictable?", "Can errors guide next action?"],
        },
    ],
    "general_review": [
        {
            "id": "source_grounding",
            "name": "Source Grounding",
            "weight": 4,
            "expectations": ["Evidence that findings cite concrete local or user-provided sources."],
            "questions": ["Is each claim grounded?", "Are skipped scopes explicit?"],
        },
        {
            "id": "risk_priority",
            "name": "Risk Priority",
            "weight": 4,
            "expectations": ["Evidence that blockers, warnings, and observations are separated."],
            "questions": ["Are correctness risks first?", "Are preferences separate from defects?"],
        },
        {
            "id": "verification_readiness",
            "name": "Verification Readiness",
            "weight": 4,
            "expectations": ["Evidence that remediation can be verified by commands or checks."],
            "questions": ["Can the next worker know when a slice is done?"],
        },
        {
            "id": "scope_control",
            "name": "Scope Control",
            "weight": 3,
            "expectations": ["Evidence for reviewed scope, deferred scope, and explicit gaps."],
            "questions": ["Is the reviewed surface bounded?", "Are unreviewed areas named?"],
        },
    ],
}

TOOLS: dict[str, dict[str, Any]] = {
    "tmcp_status": {
        "description": "Report standalone TMCP capability and optional AIOS adapter availability.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tmcp_explain": {
        "description": (
            "Compile and explain a task-specific TMCP skill packet. Uses AIOS when available "
            "and requested, otherwise uses the plugin's standalone TMCP compiler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "project_path": {"type": "string", "default": "."},
                "phase": {"type": "string"},
                "domain": {"type": "string"},
                "adapter": {
                    "type": "string",
                    "enum": ["auto", "standalone", "aios"],
                    "default": "auto",
                },
            },
            "required": ["objective"],
        },
    },
    "tmcp_harvest_skills": {
        "description": (
            "Harvest local skills, agent instructions, rules, and process docs into TMCP source "
            "nodes and a packet seed without assuming a specific AIOS/Codex setup."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "default": "."},
                "source_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of roots to harvest. Overrides source_path when provided.",
                },
                "objective": {"type": "string", "default": "Harvest reusable skill behavior"},
                "glob": {
                    "type": "string",
                    "description": "Backward-compatible single include glob.",
                    "default": "**/*.md",
                },
                "include_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Portable include globs relative to each source root.",
                },
                "exclude_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Portable exclude globs relative to each source root.",
                },
                "limit": {"type": "integer", "default": 40},
                "max_file_bytes": {"type": "integer", "default": 262144},
                "max_excerpt_chars": {"type": "integer", "default": 1200},
                "follow_symlinks": {"type": "boolean", "default": False},
                "redact_sensitive": {"type": "boolean", "default": True},
                "write_artifacts": {"type": "boolean", "default": False},
                "output_dir": {"type": "string"},
            },
        },
    },
    "expert_rubric_review_plan": {
        "description": (
            "Run the TMCP expert rubric workflow: packet, scored rubric, evidence audit, "
            "ordered remediation plan, and optional implementation handoff."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "project_path": {"type": "string", "default": "."},
                "output_dir": {"type": "string"},
                "evidence_json": {
                    "description": "JSON object or array of evidence objects.",
                    "type": "string",
                    "default": "[]",
                },
                "selected_slice_id": {"type": "string"},
                "adapter": {
                    "type": "string",
                    "enum": ["auto", "standalone", "aios"],
                    "default": "auto",
                },
                "write_artifacts": {"type": "boolean", "default": True},
            },
            "required": ["objective"],
        },
    },
}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "general"


def _text_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", value.lower()))


def _estimate_tokens(value: str) -> int:
    return max(1, len(value) // 4)


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _aios_available() -> bool:
    return (AIOS_ROOT / "bin" / "aios.py").exists()


def _should_use_aios(adapter: str) -> bool:
    if adapter == "standalone":
        return False
    if adapter == "aios":
        return True
    return _aios_available()


def _run_aios(args: list[str]) -> dict[str, Any]:
    if not _aios_available():
        return {
            "ok": False,
            "adapter": "aios",
            "error": "AIOS adapter requested but AIOS_ROOT/bin/aios.py was not found.",
            "aios_root": str(AIOS_ROOT),
        }
    command = ["uv", "run", "python", "bin/aios.py", *args]
    completed = subprocess.run(
        command,
        cwd=AIOS_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "adapter": "aios",
            "returncode": completed.returncode,
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": completed.stdout, "stderr": completed.stderr}
    if isinstance(payload, dict):
        payload.setdefault("ok", True)
        payload.setdefault("adapter", "aios")
        return payload
    return {"ok": True, "adapter": "aios", "data": payload}


def _select_task(objective: str) -> tuple[str, dict[str, int]]:
    text = objective.lower()
    scores = {
        task: sum(1 for keyword in keywords if keyword in text)
        for task, keywords in TASK_KEYWORDS.items()
    }
    if any(term in text for term in ("rubric", "audit", "review", "judge", "evaluate")):
        scores["audit"] += 2
    if any(term in text for term in ("harvest", "skill packet", "skill-packet", "tmcp packet")):
        scores["agent_workflow"] += 2
    task_priority = {
        "audit": 8,
        "debugging": 7,
        "implementation": 6,
        "testing": 5,
        "planning": 4,
        "research": 3,
        "documentation": 2,
        "agent_workflow": 1,
    }
    best = max(scores, key=lambda task: (scores[task], task_priority[task]))
    if scores[best] == 0:
        best = "agent_workflow"
    return best, scores


def _select_profile(objective: str, packet: dict[str, Any]) -> str:
    haystack = " ".join(
        [
            objective,
            str(packet.get("task_id", "")),
            " ".join(_string_list(packet.get("selected_nodes"))),
            " ".join(_string_list(packet.get("behavior_atoms"))),
        ]
    ).lower()
    if any(term in haystack for term in ("ui", "ux", "frontend", "visual", "screen", "design")):
        return "visual_polish"
    if any(term in haystack for term in ("security", "privacy", "secret", "permission")):
        return "security_privacy"
    if any(term in haystack for term in ("developer", "docs", "cli", "command", "onboarding")):
        return "developer_experience"
    return "general_review"


def _select_branch(objective: str, task_id: str) -> tuple[str, str]:
    text = objective.lower()
    if any(term in text for term in ("implement", "edit", "fix", "patch")):
        return "approval_before_edit", "Implementation language present; audit workflows still require approval before edits."
    if any(term in text for term in ("maybe", "possibly", "not sure", "unclear")):
        return "ambiguous_task_resolution", "Ambiguity language present; preserve uncertainty and ask only when necessary."
    if task_id == "implementation":
        return "direct_implementation", "Implementation is the selected task path."
    return "evidence_first_review", "Default branch keeps TMCP as an audit-and-plan workflow."


def _packet_markdown(packet: dict[str, Any]) -> str:
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
    return "\n".join(lines).rstrip() + "\n"


def _compile_standalone_packet(
    *,
    objective: str,
    project_path: str | None,
    phase: str | None = None,
    domain: str | None = None,
    harvested_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    task_id, task_scores = _select_task(objective)
    modules = list(TASK_MODULES[task_id])
    if "tmcp" in objective.lower() and "provenance_policy" not in modules:
        modules.append("provenance_policy")
    branch_id, branch_reason = _select_branch(objective, task_id)
    source_nodes = [
        {
            "id": f"@source:{node['id']}",
            "path": node.get("path"),
            "title": node.get("title"),
            "behavior_atoms": node.get("behavior_atoms", []),
        }
        for node in (harvested_nodes or [])[:8]
    ]
    selected_nodes = [
        f"@task:{task_id}",
        *(f"@module:{module}" for module in modules),
        *(str(node["id"]) for node in source_nodes),
        f"@branch:{branch_id}",
    ]
    atoms = sorted(
        {
            atom
            for module in modules
            for atom in MODULE_BEHAVIOR_ATOMS.get(module, ())
        }
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
        json.dumps({"tasks": TASK_KEYWORDS, "modules": TASK_MODULES}, sort_keys=True).encode()
    ).hexdigest()
    fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()
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
        "selected_branches": [{"branch": f"@branch:{branch_id}", "reason": branch_reason}],
        "candidate_scores": {"tasks": task_scores},
        "source_skill_nodes": source_nodes,
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
        ],
        "created_at": _now_iso(),
    }
    packet["packet_markdown"] = _packet_markdown(packet)
    packet["token_estimates"] = {
        "custom_skill_tokens": _estimate_tokens(packet["packet_markdown"]),
        "baseline_skill_tokens": _estimate_tokens(json.dumps(TASK_MODULES, sort_keys=True)) * 4,
    }
    packet["token_estimates"]["estimated_token_delta"] = (
        packet["token_estimates"]["baseline_skill_tokens"]
        - packet["token_estimates"]["custom_skill_tokens"]
    )
    return packet


def _parse_evidence(raw: object) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        parsed = json.loads(raw)
    else:
        parsed = raw
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
        return parsed
    raise ValueError("evidence_json must be a JSON object or array of objects.")


def _dimension(
    *,
    dimension: dict[str, Any],
    source_nodes: list[str],
) -> dict[str, Any]:
    return {
        "id": dimension["id"],
        "name": dimension["name"],
        "weight": dimension["weight"],
        "scale": "0-4",
        "pass_threshold": 3,
        "evidence_expectations": dimension["expectations"],
        "review_questions": dimension["questions"],
        "source_nodes": source_nodes or ["@task:agent_workflow"],
    }


def _synthesize_rubric(packet: dict[str, Any], run_id: str, objective: str) -> dict[str, Any]:
    source_nodes = _string_list(packet.get("selected_nodes"))
    profile = _select_profile(objective, packet)
    return {
        "schema": RUBRIC_SCHEMA,
        "run_id": run_id,
        "objective": objective,
        "source_packet": "expertise-packet.json",
        "profile": profile,
        "selected_nodes": source_nodes,
        "skipped_nodes": packet.get("skipped_nodes", []),
        "dimensions": [
            _dimension(dimension=dimension, source_nodes=source_nodes)
            for dimension in PROFILE_DIMENSIONS[profile]
        ],
    }


def _severity_rank(severity: str) -> int:
    return {"blocker": 0, "warning": 1, "observation": 2}.get(severity, 1)


def _severity_score(severity: str) -> int:
    return {"blocker": 1, "warning": 2, "observation": 3}.get(severity, 2)


def _known_dimension_id(candidate: object, dimensions: list[dict[str, Any]]) -> str:
    ids = [str(dimension["id"]) for dimension in dimensions]
    value = str(candidate or "")
    if value in ids:
        return value
    return ids[0] if ids else "general_review"


def _build_audit_report(
    rubric: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    dimensions = [item for item in _json_list(rubric.get("dimensions")) if isinstance(item, dict)]
    findings: list[dict[str, Any]] = []
    evidence_by_dimension: dict[str, list[str]] = {}
    for index, item in sorted(
        enumerate(evidence_items, start=1),
        key=lambda indexed: _severity_rank(str(indexed[1].get("severity", "warning"))),
    ):
        dimension_id = _known_dimension_id(item.get("dimension_id"), dimensions)
        severity = str(item.get("severity", "warning"))
        if severity not in {"blocker", "warning", "observation"}:
            severity = "warning"
        evidence = _string_list(item.get("evidence"))
        evidence_by_dimension.setdefault(dimension_id, []).extend(evidence)
        findings.append(
            {
                "id": f"finding-{dimension_id}-{index}",
                "severity": severity,
                "dimension_id": dimension_id,
                "summary": str(item.get("summary", "Evidence item requires review.")),
                "evidence": evidence,
                "recommended_fix": str(item.get("recommended_fix", "Remediate the cited evidence.")),
            }
        )
    scores: list[dict[str, Any]] = []
    for dimension in dimensions:
        dimension_id = str(dimension["id"])
        matching = [finding for finding in findings if finding["dimension_id"] == dimension_id]
        evidence = evidence_by_dimension.get(dimension_id, [])
        if matching:
            score = min(_severity_score(str(finding["severity"])) for finding in matching)
            gaps: list[str] = []
            confidence = "high" if evidence else "low"
        else:
            score = 0
            gaps = [f"No evidence supplied for {dimension_id}."]
            confidence = "low"
        scores.append(
            {
                "dimension_id": dimension_id,
                "score": score,
                "confidence": confidence,
                "evidence": evidence,
                "gaps": gaps,
            }
        )
    return {
        "schema": AUDIT_REPORT_SCHEMA,
        "run_id": run_id,
        "rubric": "rubric.json",
        "scores": scores,
        "findings": findings,
        "deferred_scope": [
            gap for score in scores for gap in _string_list(score.get("gaps"))
        ],
    }


def _build_remediation_plan(audit_report: dict[str, Any], run_id: str) -> dict[str, Any]:
    slices: list[dict[str, Any]] = []
    for index, finding in enumerate(_json_list(audit_report.get("findings")), start=1):
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("id", f"finding-{index}"))
        evidence = _string_list(finding.get("evidence"))
        slices.append(
            {
                "id": f"slice-{index}",
                "title": str(finding.get("summary", finding_id))[:80],
                "scope": evidence,
                "rationale": str(finding.get("summary", "")),
                "expected_impact": str(finding.get("recommended_fix", "")),
                "risk": "Review scope is limited to cited evidence; inspect neighboring surfaces before editing.",
                "verification": ["Run targeted checks covering the cited evidence."],
                "follow_up_workflow": "implementation-delivery",
                "source_findings": [finding_id],
            }
        )
    if not slices and audit_report.get("deferred_scope"):
        slices.append(
            {
                "id": "slice-1",
                "title": "Collect missing evidence before remediation",
                "scope": [],
                "rationale": "The rubric could be synthesized, but no concrete evidence was supplied.",
                "expected_impact": "Enables evidence-backed scoring and a remediation plan that is not speculative.",
                "risk": "Do not implement from an evidence-free rubric.",
                "verification": [
                    "Capture screenshots, file references, runtime states, or command output for each low-confidence dimension."
                ],
                "follow_up_workflow": "expert-rubric-evidence-audit",
                "source_findings": [],
            }
        )
    return {
        "schema": REMEDIATION_PLAN_SCHEMA,
        "run_id": run_id,
        "slices": slices,
        "deferred_scope": _string_list(audit_report.get("deferred_scope")),
    }


def _build_implementation_handoff(
    remediation_plan: dict[str, Any],
    run_id: str,
    selected_slice_id: str | None,
) -> dict[str, Any]:
    slices = [item for item in _json_list(remediation_plan.get("slices")) if isinstance(item, dict)]
    selected = next(
        (item for item in slices if selected_slice_id and item.get("id") == selected_slice_id),
        slices[0] if slices else {},
    )
    return {
        "schema": IMPLEMENTATION_HANDOFF_SCHEMA,
        "run_id": run_id,
        "remediation_plan": "remediation-plan.json",
        "selected_slice_id": selected.get("id") if selected else selected_slice_id,
        "selected_slice": selected,
        "requires_user_approval": True,
        "follow_up_workflow": "implementation-delivery",
        "artifact_inputs": [
            "expertise-packet.json",
            "rubric.json",
            "audit-report.json",
            "remediation-plan.json",
        ],
        "target_files": _string_list(selected.get("scope")) if selected else [],
        "acceptance_criteria": _string_list(selected.get("verification")) if selected else [],
        "known_risks": [str(selected.get("risk"))] if selected and selected.get("risk") else [],
    }


def _validations(
    packet: dict[str, Any],
    rubric: dict[str, Any],
    audit_report: dict[str, Any],
    remediation_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "validation_key": "tmcp_packet_compiled",
            "passed": packet.get("schema") == TMCP_PACKET_SCHEMA and bool(packet.get("selected_nodes")),
            "issues": [],
        },
        {
            "validation_key": "rubric_dimensions_present",
            "passed": bool(rubric.get("dimensions")),
            "issues": [] if rubric.get("dimensions") else ["Rubric has no dimensions."],
        },
        {
            "validation_key": "findings_have_evidence",
            "passed": all(_string_list(item.get("evidence")) for item in _json_list(audit_report.get("findings"))),
            "issues": [
                str(item.get("id", "finding"))
                for item in _json_list(audit_report.get("findings"))
                if isinstance(item, dict) and not _string_list(item.get("evidence"))
            ],
        },
        {
            "validation_key": "remediation_has_verification",
            "passed": all(
                _string_list(item.get("verification"))
                for item in _json_list(remediation_plan.get("slices"))
                if isinstance(item, dict)
            ),
            "issues": [],
        },
    ]


def _markdown_rubric(rubric: dict[str, Any]) -> str:
    lines = [f"# Expert Rubric: {rubric['objective']}", "", f"Profile: `{rubric['profile']}`", ""]
    for dimension in rubric["dimensions"]:
        lines.extend(
            [
                f"## {dimension['name']}",
                "",
                f"- ID: `{dimension['id']}`",
                f"- Weight: {dimension['weight']}",
                f"- Pass threshold: {dimension['pass_threshold']}/4",
                f"- Source nodes: {', '.join(dimension['source_nodes'])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _markdown_audit(report: dict[str, Any]) -> str:
    lines = [f"# Expert Audit Report: {report['run_id']}", "", "## Scores"]
    for score in report.get("scores", []):
        lines.append(
            f"- `{score['dimension_id']}`: {score['score']}/4 ({score['confidence']} confidence)"
        )
    lines.extend(["", "## Findings"])
    if not report.get("findings"):
        lines.append("- No evidence-backed findings were supplied. See deferred scope.")
    for finding in report.get("findings", []):
        lines.append(
            f"- [{finding['severity']}] {finding['summary']} Evidence: {', '.join(_string_list(finding.get('evidence')))}"
        )
    if report.get("deferred_scope"):
        lines.extend(["", "## Deferred Scope"])
        for item in report["deferred_scope"]:
            lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def _markdown_plan(plan: dict[str, Any]) -> str:
    lines = [f"# Remediation Plan: {plan['run_id']}", ""]
    for item in plan.get("slices", []):
        lines.extend(
            [
                f"## {item['id']}: {item['title']}",
                "",
                f"- Scope: {', '.join(_string_list(item.get('scope')))}",
                f"- Rationale: {item['rationale']}",
                f"- Expected impact: {item['expected_impact']}",
                f"- Risk: {item['risk']}",
                f"- Verification: {', '.join(_string_list(item.get('verification')))}",
                f"- Follow-up workflow: `{item['follow_up_workflow']}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_review_artifacts(
    output_dir: Path,
    packet: dict[str, Any],
    rubric: dict[str, Any],
    audit_report: dict[str, Any],
    remediation_plan: dict[str, Any],
    handoff: dict[str, Any],
) -> dict[str, str]:
    paths = {
        "expertise_packet": output_dir / "expertise-packet.json",
        "rubric_json": output_dir / "rubric.json",
        "rubric_markdown": output_dir / "rubric.md",
        "audit_report_json": output_dir / "audit-report.json",
        "audit_report_markdown": output_dir / "audit-report.md",
        "remediation_plan_json": output_dir / "remediation-plan.json",
        "remediation_plan_markdown": output_dir / "remediation-plan.md",
        "implementation_handoff_json": output_dir / "implementation-handoff.json",
    }
    _write_json(paths["expertise_packet"], packet)
    _write_json(paths["rubric_json"], rubric)
    paths["rubric_markdown"].write_text(_markdown_rubric(rubric), encoding="utf-8")
    _write_json(paths["audit_report_json"], audit_report)
    paths["audit_report_markdown"].write_text(_markdown_audit(audit_report), encoding="utf-8")
    _write_json(paths["remediation_plan_json"], remediation_plan)
    paths["remediation_plan_markdown"].write_text(_markdown_plan(remediation_plan), encoding="utf-8")
    _write_json(paths["implementation_handoff_json"], handoff)
    return {key: str(path) for key, path in paths.items()}


def _default_output_dir(project_path: str) -> str:
    root = Path(project_path).expanduser()
    return str(root / ".aios" / "reviews" / f"tmcp-mcp-{uuid.uuid4().hex[:8]}")


def _standalone_review_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    objective = str(arguments["objective"])
    project_path = str(arguments.get("project_path") or ".")
    run_id = f"tmcp-review-plan-{uuid.uuid4().hex[:8]}"
    evidence_items = _parse_evidence(arguments.get("evidence_json") or "[]")
    packet = _compile_standalone_packet(
        objective=objective,
        project_path=str(Path(project_path).expanduser()),
        phase="planning",
    )
    rubric = _synthesize_rubric(packet, run_id, objective)
    audit_report = _build_audit_report(rubric, evidence_items, run_id)
    remediation_plan = _build_remediation_plan(audit_report, run_id)
    handoff = _build_implementation_handoff(
        remediation_plan,
        run_id,
        str(arguments.get("selected_slice_id") or "") or None,
    )
    artifact_paths: dict[str, str] = {}
    if bool(arguments.get("write_artifacts", True)):
        artifact_paths = _write_review_artifacts(
            Path(str(arguments.get("output_dir") or _default_output_dir(project_path))).expanduser(),
            packet,
            rubric,
            audit_report,
            remediation_plan,
            handoff,
        )
    return {
        "ok": True,
        "adapter": "standalone",
        "schema": "tmcp-review-plan-result-v0.1",
        "workflow_key": "expert_rubric_remediation_v1",
        "run_id": run_id,
        "status": "completed",
        "validations": _validations(packet, rubric, audit_report, remediation_plan),
        "expertise_packet": packet,
        "rubric": rubric,
        "audit_report": audit_report,
        "remediation_plan": remediation_plan,
        "remediation_slices": remediation_plan["slices"],
        "implementation_handoff": handoff,
        "artifact_paths": artifact_paths,
    }


def _normalize_string_list(value: object, fallback: tuple[str, ...] | list[str]) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or list(fallback)
    if isinstance(value, str) and value.strip():
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return [value.strip()]
    return list(fallback)


def _expand_brace_glob(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]+)\}", pattern)
    if not match:
        return [pattern]
    before = pattern[: match.start()]
    after = pattern[match.end() :]
    return [f"{before}{item.strip()}{after}" for item in match.group(1).split(",")]


def _matches_glob(rel_path: str, path: Path, pattern: str) -> bool:
    variants = [pattern]
    if pattern.startswith("**/"):
        variants.append(pattern[3:])
    return any(
        fnmatch.fnmatch(rel_path, variant)
        or fnmatch.fnmatch(path.name, variant)
        or fnmatch.fnmatch(f"/{rel_path}", f"/{variant}")
        for variant in variants
    )


def _matches_any(rel_path: str, path: Path, patterns: list[str]) -> bool:
    expanded = [item for pattern in patterns for item in _expand_brace_glob(pattern)]
    return any(_matches_glob(rel_path, path, pattern) for pattern in expanded)


def _harvest_source_paths(arguments: dict[str, Any]) -> tuple[list[Path], list[str]]:
    raw_paths = arguments.get("source_paths")
    if isinstance(raw_paths, list) and raw_paths:
        candidates = [str(item) for item in raw_paths]
    else:
        candidates = [str(arguments.get("source_path") or ".")]
    roots: list[Path] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        root = Path(candidate).expanduser().resolve()
        root_key = str(root)
        if root_key in seen:
            continue
        seen.add(root_key)
        if not root.exists():
            warnings.append(f"Source path does not exist: {root}")
            continue
        if root.is_file():
            roots.append(root)
            continue
        if root.is_dir():
            roots.append(root)
            continue
        warnings.append(f"Source path is not a regular file or directory: {root}")
    return roots, warnings


def _source_type_for(path: Path, rel_path: str, text: str) -> str:
    name = path.name.lower()
    rel = rel_path.lower()
    lower = text[:4000].lower()
    if name == "skill.md":
        return "skill_definition"
    if name in {"agents.md", "claude.md"}:
        return "agent_operating_contract"
    if ".cursor/" in rel or name == ".cursorrules":
        return "cursor_rule"
    if ".github/" in rel:
        return "github_process"
    if "workflow" in rel or "workflow" in lower:
        return "workflow_prompt"
    if name == "readme.md" or "/docs/" in f"/{rel}" or "/doc/" in f"/{rel}":
        return "project_documentation"
    return "markdown_process_doc"


def _harvest_priority(path: Path, rel_path: str, source_type: str) -> tuple[int, str]:
    name = path.name.lower()
    type_score = {
        "skill_definition": 0,
        "agent_operating_contract": 1,
        "cursor_rule": 2,
        "github_process": 3,
        "workflow_prompt": 4,
        "project_documentation": 5,
        "markdown_process_doc": 8,
    }.get(source_type, 9)
    if name in {"skill.md", "agents.md", "claude.md", "readme.md"}:
        type_score = min(type_score, 1)
    return type_score, rel_path


def _iter_harvest_candidates(
    roots: list[Path],
    include_globs: list[str],
    exclude_globs: list[str],
    *,
    follow_symlinks: bool,
) -> tuple[list[tuple[Path, Path, str]], list[str]]:
    candidates: list[tuple[Path, Path, str]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if root.is_file():
            rel_path = root.name
            if _matches_any(rel_path, root, include_globs) and not _matches_any(
                rel_path, root, exclude_globs
            ):
                candidates.append((root.parent, root, rel_path))
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
            current = Path(dirpath)
            rel_dir = current.relative_to(root).as_posix() if current != root else "."
            pruned: list[str] = []
            for dirname in list(dirnames):
                child = current / dirname
                child_rel = child.relative_to(root).as_posix()
                if dirname in DEFAULT_HARVEST_EXCLUDE_DIR_NAMES or _matches_any(
                    f"{child_rel}/", child, exclude_globs
                ):
                    dirnames.remove(dirname)
                    pruned.append(child_rel)
            if pruned and len(warnings) < 20:
                warnings.append(f"Skipped directory: {', '.join(pruned[:3])}")
            for filename in filenames:
                path = current / filename
                try:
                    resolved = str(path.resolve(strict=False))
                except OSError:
                    resolved = str(path)
                if resolved in seen:
                    continue
                seen.add(resolved)
                try:
                    rel_path = path.relative_to(root).as_posix()
                except ValueError:
                    rel_path = f"{rel_dir}/{filename}" if rel_dir != "." else filename
                if _matches_any(rel_path, path, exclude_globs):
                    continue
                if not _matches_any(rel_path, path, include_globs):
                    continue
                candidates.append((root, path, rel_path))
    return candidates, warnings


def _classify_atoms(text: str, source_type: str = "") -> list[str]:
    lower = text.lower()
    atoms: set[str] = set(HARVEST_SOURCE_TYPE_ATOMS.get(source_type, ()))
    for atom_source, atom_values in MODULE_BEHAVIOR_ATOMS.items():
        if atom_source.replace("_", " ") in lower or atom_source in lower:
            atoms.update(atom_values)
    if any(term in lower for term in ("test", "verify", "validate", "quality")):
        atoms.update(MODULE_BEHAVIOR_ATOMS["test_gate"])
    if any(term in lower for term in ("evidence", "source", "citation", "screenshot")):
        atoms.update(MODULE_BEHAVIOR_ATOMS["evidence_first"])
    if any(term in lower for term in ("approval", "ask before", "do not edit")):
        atoms.update(MODULE_BEHAVIOR_ATOMS["user_approval_gate"])
    if any(term in lower for term in ("routing", "workflow", "skill", "agent")):
        atoms.update(MODULE_BEHAVIOR_ATOMS["tool_use_policy"])
    if any(term in lower for term in ("conflict", "precedence", "override", "branch")):
        atoms.add("conflict-preservation")
    if any(term in lower for term in ("artifact", "output contract", "schema", "handoff")):
        atoms.add("artifact-contract")
    return sorted(atoms)[:10]


def _title_for(path: Path, text: str) -> str:
    frontmatter = _frontmatter_for(text)
    for key in ("name", "title", "description"):
        value = frontmatter.get(key)
        if value:
            return value[:100]
    for line in text.splitlines():
        clean = line.strip("# ").strip()
        if clean and not clean.startswith("---"):
            return clean[:100]
    return path.stem


def _frontmatter_for(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    frontmatter: dict[str, str] = {}
    for raw_line in text[3:end].splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        clean_key = key.strip().lower()
        clean_value = value.strip().strip("\"'")
        if clean_key and clean_value and len(clean_value) <= 300:
            frontmatter[clean_key] = clean_value
    return frontmatter


def _read_text_limited(path: Path, max_file_bytes: int) -> tuple[str | None, str | None]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, f"Could not stat {path}: {exc}"
    if size > max_file_bytes:
        return None, f"Skipped large file: {path} ({size} bytes > {max_file_bytes})"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, f"Could not read {path}: {exc}"
    if b"\x00" in data[:2048]:
        return None, f"Skipped likely binary file: {path}"
    return data.decode("utf-8", errors="replace"), None


def _write_harvest_artifacts(output_dir: Path, result: dict[str, Any]) -> dict[str, str]:
    paths = {
        "harvest_result": output_dir / "tmcp-harvest-result.json",
        "packet_seed": output_dir / "tmcp-packet-seed.json",
    }
    _write_json(paths["harvest_result"], result)
    packet = result.get("packet_seed")
    if isinstance(packet, dict):
        _write_json(paths["packet_seed"], packet)
    return {key: str(path) for key, path in paths.items() if path.exists()}


def _harvest_skills(arguments: dict[str, Any]) -> dict[str, Any]:
    objective = str(arguments.get("objective") or "Harvest reusable skill behavior")
    limit = max(1, int(arguments.get("limit") or 40))
    max_file_bytes = max(1024, int(arguments.get("max_file_bytes") or 262144))
    max_excerpt_chars = max(200, int(arguments.get("max_excerpt_chars") or 1200))
    follow_symlinks = bool(arguments.get("follow_symlinks", False))
    redact_sensitive = bool(arguments.get("redact_sensitive", True))
    source_roots, warnings = _harvest_source_paths(arguments)
    include_globs = _normalize_string_list(
        arguments.get("include_globs"),
        DEFAULT_HARVEST_INCLUDE_GLOBS,
    )
    if "glob" in arguments and not arguments.get("include_globs"):
        include_globs = _normalize_string_list(arguments.get("glob"), DEFAULT_HARVEST_INCLUDE_GLOBS)
    exclude_globs = _normalize_string_list(
        arguments.get("exclude_globs"),
        DEFAULT_HARVEST_EXCLUDE_GLOBS,
    )
    candidates, traversal_warnings = _iter_harvest_candidates(
        source_roots,
        include_globs,
        exclude_globs,
        follow_symlinks=follow_symlinks,
    )
    warnings.extend(traversal_warnings)
    nodes: list[dict[str, Any]] = []
    redaction_totals: dict[str, int] = {}
    for root, path, rel_path in candidates:
        text, warning = _read_text_limited(path, max_file_bytes)
        if warning:
            if len(warnings) < 50:
                warnings.append(warning)
            continue
        if text is None:
            continue
        safe_text, redactions = redact_sensitive_text(text, enabled=redact_sensitive)
        merge_redactions(redaction_totals, redactions)
        source_type = _source_type_for(path, rel_path, text)
        tokens = sorted(_text_tokens(safe_text))
        node_id = hashlib.sha256(f"{path}:{hashlib.sha256(text.encode()).hexdigest()}".encode()).hexdigest()[:12]
        frontmatter = _frontmatter_for(safe_text)
        nodes.append(
            {
                "id": node_id,
                "root_path": str(root),
                "path": str(path),
                "relative_path": rel_path,
                "title": _title_for(path, text),
                "source_type": source_type,
                "source_tier": source_type,
                "frontmatter": frontmatter,
                "token_estimate": _estimate_tokens(safe_text),
                "behavior_atoms": _classify_atoms(safe_text, source_type),
                "keywords": tokens[:20],
                "excerpt": safe_text[:max_excerpt_chars],
                "redactions": redactions,
            }
        )
    nodes.sort(key=lambda node: _harvest_priority(Path(str(node["path"])), str(node["relative_path"]), str(node["source_type"])))
    if len(nodes) > limit:
        warnings.append(f"Harvest limit reached: kept {limit} of {len(nodes)} matched source files.")
        nodes = nodes[:limit]
    project_path = str(source_roots[0]) if source_roots else str(Path(".").resolve())
    packet = _compile_standalone_packet(
        objective=objective,
        project_path=project_path,
        harvested_nodes=nodes,
    )
    result: dict[str, Any] = {
        "ok": True,
        "adapter": "standalone",
        "schema": "tmcp-harvest-result-v0.1",
        "source_paths": [str(root) for root in source_roots],
        "harvest_config": {
            "include_globs": include_globs,
            "exclude_globs": exclude_globs,
            "limit": limit,
            "max_file_bytes": max_file_bytes,
            "max_excerpt_chars": max_excerpt_chars,
            "follow_symlinks": follow_symlinks,
            "redact_sensitive": redact_sensitive,
        },
        "redaction_summary": redaction_totals,
        "warnings": warnings,
        "matched_source_count": len(candidates),
        "source_count": len(nodes),
        "source_nodes": nodes,
        "packet_seed": packet,
    }
    if bool(arguments.get("write_artifacts", False)):
        output_dir = Path(
            str(arguments.get("output_dir") or Path(project_path) / ".tmcp" / f"harvest-{uuid.uuid4().hex[:8]}")
        ).expanduser()
        result["artifact_paths"] = _write_harvest_artifacts(output_dir, result)
    return result


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "tmcp_status":
        return {
            "ok": True,
            "schema": "tmcp-status-v0.1",
            "standalone": {
                "available": True,
                "plugin_root": str(PLUGIN_ROOT),
                "capabilities": [
                    "packet_compile",
                    "portable_skill_harvest",
                    "multi_root_harvest",
                    "source_type_classification",
                    "expert_rubric_review_plan",
                    "artifact_write",
                ],
            },
            "aios_adapter": {
                "available": _aios_available(),
                "aios_root": str(AIOS_ROOT),
                "role": "optional acceleration and persistence layer",
            },
        }
    if name == "tmcp_explain":
        adapter = str(arguments.get("adapter") or "auto")
        if _should_use_aios(adapter):
            args = [
                "tmcp",
                "explain",
                str(arguments["objective"]),
                "--project-path",
                str(arguments.get("project_path") or "."),
                "--json",
            ]
            if arguments.get("phase"):
                args.extend(["--phase", str(arguments["phase"])])
            if arguments.get("domain"):
                args.extend(["--domain", str(arguments["domain"])])
            payload = _run_aios(args)
            if payload.get("ok") or adapter == "aios":
                return payload
        return {
            "ok": True,
            "adapter": "standalone",
            "command": "tmcp-explain",
            "data_status": "compiled",
            "packet": _compile_standalone_packet(
                objective=str(arguments["objective"]),
                project_path=str(arguments.get("project_path") or "."),
                phase=str(arguments.get("phase") or "") or None,
                domain=str(arguments.get("domain") or "") or None,
            ),
        }
    if name == "tmcp_harvest_skills":
        return _harvest_skills(arguments)
    if name == "expert_rubric_review_plan":
        adapter = str(arguments.get("adapter") or "auto")
        if _should_use_aios(adapter):
            project_path = str(arguments.get("project_path") or ".")
            args = [
                "tmcp",
                "review-plan",
                str(arguments["objective"]),
                "--project-path",
                project_path,
                "--output-dir",
                str(arguments.get("output_dir") or _default_output_dir(project_path)),
                "--evidence-json",
                str(arguments.get("evidence_json") or "[]"),
                "--json",
            ]
            if arguments.get("selected_slice_id"):
                args.extend(["--selected-slice-id", str(arguments["selected_slice_id"])])
            payload = _run_aios(args)
            if payload.get("ok") or adapter == "aios":
                return payload
        return _standalone_review_plan(arguments)
    raise ValueError(f"Unknown TMCP tool: {name}")


def _result(request_id: Any, result: dict[str, Any]) -> None:
    write_message(sys.stdout.buffer, {"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, code: int, message: str) -> None:
    write_message(
        sys.stdout.buffer,
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
    )


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}],
        "structuredContent": payload,
        "isError": not bool(payload.get("ok", True)),
    }


def _handle(request: dict[str, Any]) -> None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    if method == "initialize":
        _result(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "serverInfo": {"name": "tmcp", "version": "0.2.0"},
                "capabilities": {"tools": {}},
            },
        )
        return
    if method == "tools/list":
        _result(
            request_id,
            {"tools": [{"name": name, **definition} for name, definition in sorted(TOOLS.items())]},
        )
        return
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            _error(request_id, -32602, "Tool arguments must be an object.")
            return
        try:
            _result(request_id, _tool_result(_call_tool(name, arguments)))
        except Exception as exc:
            _error(request_id, -32000, str(exc))
        return
    if method in {"notifications/initialized", "ping"}:
        if request_id is not None:
            _result(request_id, {})
        return
    if method in {"resources/list", "prompts/list"}:
        key = "resources" if method == "resources/list" else "prompts"
        _result(request_id, {key: []})
        return
    if request_id is not None:
        _error(request_id, -32601, f"Unsupported method: {method}")


def main() -> None:
    while True:
        message = read_message(sys.stdin.buffer)
        if message is None:
            break
        _handle(message)


if __name__ == "__main__":
    main()
