"""Raw MCP input schemas owned by the canonical TMCP contract registry."""

from __future__ import annotations

from .composition_tool_schemas import COMPOSITION_TOOLS


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
            "Compile and explain a task-specific TMCP skill packet for inspection or "
            "compatibility. Substantial host work should use prepare → cited proposal → "
            "compose; AIOS runs only when adapter=aios is explicitly requested."
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
                    "description": (
                        "Also return a deterministic compatibility composed packet; this "
                        "preview cannot carry a host semantic proposal."
                    ),
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
                    "enum": [
                        "auto",
                        "plan",
                        "score",
                        "composition-plan",
                        "composition-score",
                    ],
                    "default": "auto",
                    "description": (
                        "Singleton evaluation plan/scoring, composition ablation plan/scoring, "
                        "or auto-detection from inputs."
                    ),
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
                "composition_skill_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Ordered participating skill ids for no-skill, naïve-union, singleton, "
                        "full-composition, leave-one-out, and wrong-order variants."
                    ),
                },
                "composition_results": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Observed quality, safety, and context results for every composition "
                        "evaluation variant."
                    ),
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
    **COMPOSITION_TOOLS,
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
