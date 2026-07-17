"""Composition-specific raw MCP input schemas."""

from __future__ import annotations


COMPOSITION_TOOLS: dict[str, dict[str, object]] = {
    "tmcp_prepare_composition": {
        "description": (
            "Prepare a bounded, source-backed semantic composition request for a substantial "
            "task. The host proposes relationships using the returned contract; TMCP remains "
            "the deterministic validator and compiler."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "project_path": {"type": "string", "default": "."},
                "source_path": {"type": "string", "default": "."},
                "source_paths": {"type": "array", "items": {"type": "string"}},
                "phase": {"type": "string", "default": "start"},
                "runtime_context": {"type": "object"},
                "explicitly_scoped_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Exact harvested relative paths that may opt tests, fixtures, or "
                        "examples into candidate consideration."
                    ),
                },
                "include_globs": {"type": "array", "items": {"type": "string"}},
                "exclude_globs": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 40},
                "candidate_limit": {
                    "type": "integer",
                    "default": 12,
                    "minimum": 1,
                    "maximum": 24,
                },
                "max_file_bytes": {"type": "integer", "default": 262144},
                "max_excerpt_chars": {"type": "integer", "default": 1200},
                "max_total_chars": {
                    "type": "integer",
                    "default": 12000,
                    "minimum": 1000,
                    "maximum": 48000,
                },
                "max_total_tokens": {
                    "type": "integer",
                    "default": 3000,
                    "minimum": 250,
                    "maximum": 12000,
                    "description": "Hard estimated-token boundary for returned source slices.",
                },
                "follow_symlinks": {"type": "boolean", "default": False},
                "redact_sensitive": {"type": "boolean", "default": True},
            },
            "required": ["objective"],
        },
    },
    "tmcp_promote_composition_recipe": {
        "description": (
            "Explicitly promote an evaluated semantic composition into one reviewed, "
            "project-local recipe. Promotion is create-only and requires three verified "
            "receipts across two fixtures with matching graph provenance and lift gates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Absolute project root that will own the reviewed recipe.",
                },
                "recipe_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80,
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$",
                },
                "composition_plan": {
                    "type": "object",
                    "description": "Accepted tmcp-composition-plan-v0.1 to review and promote.",
                },
                "receipts": {
                    "type": "array",
                    "items": {"type": "object"},
                    "minItems": 3,
                    "description": "Verified composition receipts used for fixed promotion gates.",
                },
                "graph_digest": {
                    "type": "string",
                    "pattern": "^[a-f0-9]{32}$",
                    "description": "Optional explicit digest cross-check for the supplied plan.",
                },
                "explicit_promotion": {
                    "const": True,
                    "description": "Required acknowledgement; recipes never auto-promote.",
                },
            },
            "required": [
                "project_path",
                "recipe_id",
                "composition_plan",
                "receipts",
                "explicit_promotion",
            ],
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
                    "enum": ["global", "project", "none"],
                    "default": "none",
                    "description": (
                        "Read no cache by default. Set project to use explicitly reviewed "
                        "project-local recipes, or global to opt into advisory promoted "
                        "graphs and receipts from TMCP_HOME."
                    ),
                },
                "semantic_proposal": {
                    "type": "object",
                    "description": (
                        "Optional tmcp-semantic-proposal-v0.1 object proposed by a host from "
                        "tmcp_prepare_composition. TMCP validates every cited relationship."
                    ),
                },
                "project_recipe_id": {
                    "type": "string",
                    "description": (
                        "Explicit reviewed project-local recipe id to load when "
                        "cache_policy=project."
                    ),
                },
                "explicitly_scoped_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Exact harvested relative paths explicitly scoped for this composition."
                    ),
                },
                "candidate_limit": {
                    "type": "integer",
                    "default": 12,
                    "minimum": 1,
                    "maximum": 24,
                },
                "max_total_chars": {
                    "type": "integer",
                    "default": 12000,
                    "minimum": 1000,
                    "maximum": 48000,
                },
                "max_total_tokens": {
                    "type": "integer",
                    "default": 3000,
                    "minimum": 250,
                    "maximum": 12000,
                    "description": "Hard estimated-token boundary for semantic source slices.",
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
                "requested_phase": {
                    "type": "string",
                    "description": "Explicit requested composition phase; advancement remains gate-checked.",
                },
                "previous_packet_id": {"type": "string"},
                "files_read": {"type": "array", "items": {"type": "string"}},
                "files_changed": {"type": "array", "items": {"type": "string"}},
                "commands_run": {"type": "array", "items": {"type": "string"}},
                "verification_results": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Structured named verification outcomes observed by the host.",
                },
                "gate_results": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Explicit named composition gate pass/fail results.",
                },
                "handoff_results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "handoff_id",
                            "producer_node_id",
                            "consumer_node_id",
                            "status",
                        ],
                        "properties": {
                            "handoff_id": {"type": "string", "minLength": 1},
                            "producer_node_id": {"type": "string", "minLength": 1},
                            "consumer_node_id": {"type": "string", "minLength": 1},
                            "status": {"type": "string"},
                            "consumed_inputs": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                            "produced_outputs": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                            "evidence_refs": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                    "description": "Typed producer-to-consumer handoff evidence tied to a compiled handoff contract.",
                },
                "failures": {"type": "array", "items": {"type": "string"}},
                "browser_evidence": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object"}]},
                },
                "latest_user_message": {"type": "string"},
                "user_overrides": {
                    "type": "array",
                    "items": {"oneOf": [{"type": "string"}, {"type": "object"}]},
                },
                "user_redirect": {
                    "oneOf": [{"type": "string"}, {"type": "object"}],
                    "description": "Explicit host-observed redirect that causes the task identity to be re-evaluated.",
                },
                "previous_task_identity": {"type": "object"},
                "semantic_proposal": {
                    "type": "object",
                    "description": (
                        "Optional refreshed tmcp-semantic-proposal-v0.1 for a full graph-aware "
                        "recompile."
                    ),
                },
                "project_recipe_id": {
                    "type": "string",
                    "description": "Explicit reviewed project-local recipe id for full recompile.",
                },
                "candidate_limit": {
                    "type": "integer",
                    "default": 12,
                    "minimum": 1,
                    "maximum": 24,
                },
                "max_total_chars": {
                    "type": "integer",
                    "default": 12000,
                    "minimum": 1000,
                    "maximum": 48000,
                },
                "max_total_tokens": {
                    "type": "integer",
                    "default": 3000,
                    "minimum": 250,
                    "maximum": 12000,
                },
                "explicitly_scoped_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                },
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
                    "enum": ["global", "project", "none"],
                    "default": "none",
                    "description": (
                        "Read no cache by default. Set project to use explicitly reviewed "
                        "project-local recipes, or global to opt into advisory promoted "
                        "graphs and receipts from TMCP_HOME."
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
                "recipe_id": {"type": "string"},
                "task_identity": {"type": "object"},
                "graph_digest": {"type": "string"},
                "content_digests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Normalized source-content digests for the compiled graph.",
                },
                "selected_skill_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "phase_trace": {"type": "array", "items": {"type": "object"}},
                "gate_results": {"type": "array", "items": {"type": "object"}},
                "handoff_results": {"type": "array", "items": {"type": "object"}},
                "quality_metrics": {"type": "object"},
                "cost_metrics": {"type": "object"},
                "composition_fixture_id": {"type": "string"},
                "outcome": {"type": "string"},
            },
            "required": ["packet_id"],
        },
    },
}
