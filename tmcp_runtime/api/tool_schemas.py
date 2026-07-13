"""Raw MCP input schemas owned by the canonical TMCP contract registry."""

from __future__ import annotations


TOOLS: dict[str, dict[str, object]] = {
    "tmcp_doctor": {
        "description": (
            "Run a first-run readiness check for TMCP across Codex, Claude Code, "
            "Claude Desktop, and plain MCP client usage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "client": {
                    "type": "string",
                    "enum": [
                        "auto",
                        "codex",
                        "claude_code",
                        "claude_desktop",
                        "plain_mcp",
                    ],
                    "default": "auto",
                },
                "project_path": {"type": "string", "default": "."},
            },
        },
    },
    "tmcp_status": {
        "description": "Report standalone TMCP capability and optional AIOS adapter availability.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "tmcp_explain": {
        "description": (
            "Compile and explain a task-specific TMCP skill packet. Uses the standalone compiler "
            "by default; AIOS runs only when adapter=aios is explicitly requested."
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
                "compose": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also return a deterministic composed packet for the objective.",
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
                "objective": {
                    "type": "string",
                    "default": "Harvest reusable skill behavior",
                },
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
    "tmcp_evaluate_skills": {
        "description": (
            "Experimental skill evaluation: static review, behavioral A/B plan generation, "
            "and evidence scoring for full SKILL.md files with atom-level internals."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["auto", "plan", "score"],
                    "default": "auto",
                    "description": "Plan generation, evidence scoring, or auto-detect from inputs.",
                },
                "skill_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Full skill files to evaluate (for plan mode).",
                },
                "task_fixtures": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Behavioral task fixtures with expected observables.",
                },
                "variants": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Variant ids for the behavioral A/B matrix.",
                },
                "evaluation_plan": {
                    "description": "Evaluation plan object or path (for score mode).",
                },
                "run_evidence_json": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Structured trace evidence for score mode.",
                },
                "compose_packet": {
                    "type": "boolean",
                    "default": True,
                    "description": "Score packet inclusion from tmcp_compose_packet diffs.",
                },
                "project_path": {
                    "type": "string",
                    "description": "Project root used when composing packets during scoring.",
                },
                "write_artifacts": {"type": "boolean", "default": False},
                "output_dir": {"type": "string"},
            },
        },
    },
    "tmcp_recommend_workflows": {
        "description": (
            "Harvest local skill and instruction sources, infer coding-quality priority signals, "
            "and recommend custom TMCP expert workflows with evidence."
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
                "objective": {
                    "type": "string",
                    "default": "Recommend custom TMCP workflows from harvested skill signals.",
                },
                "include_globs": {"type": "array", "items": {"type": "string"}},
                "exclude_globs": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 40},
                "max_file_bytes": {"type": "integer", "default": 262144},
                "max_excerpt_chars": {"type": "integer", "default": 1200},
                "follow_symlinks": {"type": "boolean", "default": False},
                "redact_sensitive": {"type": "boolean", "default": True},
                "candidate_workflows": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional workflow ids or signal families to score.",
                },
                "min_confidence": {"type": "number", "default": 0.25},
                "write_artifacts": {"type": "boolean", "default": False},
                "output_dir": {"type": "string"},
                "compose": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also return a deterministic composed packet for the objective.",
                },
            },
        },
    },
    "tmcp_compose_packet": {
        "description": (
            "Compose a small task-specific packet from harvested skills, promoted global "
            "routing knowledge, and optional runtime context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "project_path": {"type": "string", "default": "."},
                "source_path": {"type": "string", "default": "."},
                "source_paths": {"type": "array", "items": {"type": "string"}},
                "phase": {"type": "string", "default": "start"},
                "cache_policy": {
                    "type": "string",
                    "enum": ["global", "none"],
                    "default": "none",
                    "description": (
                        "Read no global cache by default. Set global only to opt into "
                        "advisory promoted graphs and receipts from TMCP_HOME."
                    ),
                },
                "runtime_context": {"type": "object"},
                "include_globs": {"type": "array", "items": {"type": "string"}},
                "exclude_globs": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 40},
                "max_file_bytes": {"type": "integer", "default": 262144},
                "max_excerpt_chars": {"type": "integer", "default": 1200},
                "follow_symlinks": {"type": "boolean", "default": False},
                "redact_sensitive": {"type": "boolean", "default": True},
                "session_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80,
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$",
                    "description": (
                        "Optional explicit project-local packet session identifier. "
                        "Requires an absolute project_path and enables a protected local "
                        "session write."
                    ),
                },
            },
            "required": ["objective"],
            "allOf": [
                {
                    "if": {"required": ["session_id"]},
                    "then": {"required": ["project_path"]},
                }
            ],
        },
    },
    "tmcp_runtime_next": {
        "description": (
            "Recompose packet deltas for the next agent step from runtime evidence such as "
            "changed files, failures, browser evidence, and latest user message."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "project_path": {"type": "string", "default": "."},
                "source_path": {
                    "type": "string",
                    "description": "Optional harvest root for family phase transitions.",
                },
                "source_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional harvest roots for family phase transitions.",
                },
                "current_phase": {"type": "string", "default": "start"},
                "previous_packet_id": {"type": "string"},
                "files_read": {"type": "array", "items": {"type": "string"}},
                "files_changed": {"type": "array", "items": {"type": "string"}},
                "commands_run": {"type": "array", "items": {"type": "string"}},
                "failures": {"type": "array", "items": {"type": "string"}},
                "browser_evidence": {"type": "array", "items": {"type": "string"}},
                "latest_user_message": {"type": "string"},
                "previous_task_identity": {"type": "object"},
                "previous_packet": {
                    "type": "object",
                    "description": "Full previous composed packet required for output_mode=full.",
                },
                "session_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80,
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$",
                    "description": (
                        "Optional project-local packet session identifier for a full "
                        "recompile. Requires an absolute project_path and cannot be combined with "
                        "previous_packet."
                    ),
                },
                "proposed_changes": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Agent-proposed packet changes validated against the route catalog.",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["delta", "full"],
                    "default": "delta",
                    "description": "Return packet deltas or a full recompiled packet.",
                },
                "cache_policy": {
                    "type": "string",
                    "enum": ["global", "none"],
                    "default": "none",
                    "description": (
                        "Read no global cache by default. Set global only to opt into "
                        "advisory promoted graphs and receipts from TMCP_HOME."
                    ),
                },
            },
            "required": ["objective"],
            "allOf": [
                {
                    "if": {"required": ["session_id"]},
                    "then": {
                        "required": ["project_path", "output_mode"],
                        "properties": {"output_mode": {"const": "full"}},
                        "not": {"required": ["previous_packet"]},
                    },
                }
            ],
        },
    },
    "tmcp_record_receipt": {
        "description": (
            "Record an advisory TMCP run receipt in the global cache. Receipts can improve "
            "future ranking but never override higher-priority instructions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "packet_id": {"type": "string"},
                "activated_atoms": {"type": "array", "items": {"type": "string"}},
                "ignored_atoms": {"type": "array", "items": {"type": "string"}},
                "commands_run": {"type": "array", "items": {"type": "string"}},
                "verification_results": {"type": "array", "items": {"type": "string"}},
                "user_overrides": {"type": "array", "items": {"type": "string"}},
                "outcome": {"type": "string"},
            },
            "required": ["packet_id"],
        },
    },
    "tmcp_promote_harvest": {
        "description": (
            "Promote reviewed harvest/recommendation evidence into durable TMCP routing artifacts "
            "with source-to-atom and atom-to-workflow graph edges. Promotion is explicit and does "
            "not run automatically after harvest."
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
                "objective": {
                    "type": "string",
                    "default": "Promote harvested skill signals into durable TMCP routing knowledge.",
                },
                "selected_workflows": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional workflow ids or signal families to promote. Defaults to all recommended workflows.",
                },
                "selected_scoped_packet_seeds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional scoped packet seed ids to promote. Defaults to all recommended scoped seeds when present.",
                },
                "candidate_workflows": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional workflow ids or signal families to score before promotion.",
                },
                "include_globs": {"type": "array", "items": {"type": "string"}},
                "exclude_globs": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 40},
                "max_file_bytes": {"type": "integer", "default": 262144},
                "max_excerpt_chars": {"type": "integer", "default": 1200},
                "follow_symlinks": {"type": "boolean", "default": False},
                "redact_sensitive": {"type": "boolean", "default": True},
                "min_confidence": {"type": "number", "default": 0.25},
                "promotion_name": {"type": "string"},
                "persist_global": {"type": "boolean", "default": True},
                "write_artifacts": {"type": "boolean", "default": True},
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
                    "description": (
                        "JSON object or array of evidence objects. Each actionable item should include "
                        "dimension_id, severity, summary, non-empty evidence citations, and optional "
                        "recommended_fix. Generic kind/status records are accepted as JSON but reported "
                        "as diagnostics until mapped to rubric dimensions. Empty evidence returns a "
                        "dimension-mapped starter template instead of findings."
                    ),
                    "type": "string",
                    "default": "[]",
                },
                "harvest_sources": {
                    "description": "Harvest target project docs/process files for packet substance before synthesizing the rubric.",
                    "type": "boolean",
                    "default": True,
                },
                "source_limit": {"type": "integer", "default": 24},
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
