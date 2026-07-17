# Packet Stability

TMCP packets are intended to be stable enough for other tools to consume. The current public packet schema is `tmcp-skill-packet-v0.2`. Adaptive workflow-pack artifacts use `tmcp-adaptive-workflow-pack-v0.1`. Composable runtime artifacts use `tmcp-composed-packet-v0.1`, `tmcp-runtime-next-v0.1`, `tmcp-run-receipt-v0.1`, `tmcp-recompiled-packet-v0.1`, and the explicit project-local `tmcp-run-session-v0.1`. Experimental assisted composition adds `tmcp-composition-preflight-v0.1`, `tmcp-semantic-proposal-v0.1`, `tmcp-composition-plan-v0.1`, `tmcp-project-composition-recipe-v0.1`, and composition evaluation plan/summary v0.1 contracts. Promoted harvest graphs use `tmcp-promoted-harvest-graph-v0.1`. See [ADAPTIVE_PACKET_RUNTIME.md](ADAPTIVE_PACKET_RUNTIME.md).

## Compatibility Promise

For all `v0.x` packet schemas:

- Required fields documented in [TMCP_PACKET_SPEC.md](TMCP_PACKET_SPEC.md) remain present for that exact schema string.
- New optional fields may be added without changing the schema identifier.
- Existing field meanings will not be repurposed under the same schema identifier.
- Breaking changes require a new schema identifier, for example `tmcp-skill-packet-v0.3`.
- Consumers should ignore unknown fields.
- Consumers should treat `adapter: "aios"` packets as enriched packets, not a different core model.

## Stable Consumer Surface

External tools can rely on these fields for `tmcp-skill-packet-v0.2`:

- `schema`
- `receipt_schema`
- `status`
- `adapter`
- `task_id`
- `objective`
- `project_path`
- `selected_nodes`
- `skipped_nodes`
- `selected_branches`
- `source_skill_nodes`
- `behavior_atoms`
- `shortcut_candidate`
- `shortcut_governance`
- `transition_trace`
- `traversal_fingerprint`
- `token_estimates`
- `output_contract`
- `packet_markdown`

External tools can rely on these fields for composition/runtime schemas:

- `tmcp-composed-packet-v0.1`: `packet_id`, `active_instructions`, `required_reads`, `tool_script_prompts`, `verification_gates`, `stop_conditions`, `active_atoms`, `deferred_atoms`, `ignored_sources`, `conflicts`, `evidence_citations`, `receipt_template`, and `safety`; assisted packets add `composition_plan`, `semantic_proposal_validation`, `composition_diagnostics`, and optional `project_recipe`.
- `tmcp-runtime-next-v0.1`: `packet_delta`, `next_verification_gate`, `warnings`, `task_identity`, optional `task_identity_delta`, and `safety`.
- `tmcp-recompiled-packet-v0.1`: `packet`, `packet_diff`, `recompile_reason`, `recompile_detail`, `validated_changes`, and `warnings`.
- `tmcp-run-receipt-v0.1`: `packet_id`, `activated_atoms`, `ignored_atoms`, `commands_run`, `verification_results`, `user_overrides`, `outcome`, and `trust`; composition receipts may add `recipe_id`, `task_identity`, `graph_digest`, `content_digests`, `selected_skill_ids`, `phase_trace`, `gate_results`, `quality_metrics`, `cost_metrics`, and `composition_fixture_id`. Project-recipe promotion requires every matching receipt to contain an explicitly passing structured safety gate; generic verification prose is not safety evidence.
- `tmcp-composition-preflight-v0.1`: deterministic `preflight_id`, bounded candidate slices, source roles/digests, scoped-seed graph hints, proposal starter, diagnostics, and precedence policy.
- `tmcp-semantic-proposal-v0.1`: task model, cited typed skill roles, cited relationships, phase, and coverage proposed by the host but not trusted as authority.
- `tmcp-composition-plan-v0.1`: validated task model, roles, typed edges, ordered stages/bridges, gates, coverage, scoped-seed semantics, graph provenance, and diagnostics.
- `tmcp-project-composition-recipe-v0.1`: one explicit create-only reviewed project recipe, promotion evidence, graph identity, and explicit-load policy.
- `tmcp-project-recipe-promotion-v0.1`: the public promotion acknowledgement containing the validated project recipe and storage metadata.
- Composition evaluation plan/summary v0.1: complete ablation variants and scored lift, safety, and context results from caller-supplied observations.
- `tmcp-run-session-v0.1`: a redacted project-local latest-packet record; composed and recompiled responses may add a `session` reference when explicitly requested.
- `tmcp-promoted-harvest-graph-v0.1`: `source_nodes`, `behavior_atoms`, `workflow_nodes`, `edges`, and `trust`.

## Machine-Readable Schema

The packet JSON Schema draft lives at [schemas/tmcp-skill-packet-v0.2.schema.json](../schemas/tmcp-skill-packet-v0.2.schema.json). The adaptive workflow-pack schema lives at [schemas/tmcp-adaptive-workflow-pack-v0.1.schema.json](../schemas/tmcp-adaptive-workflow-pack-v0.1.schema.json). Composition schemas live at [composed packet](../schemas/tmcp-composed-packet-v0.1.schema.json), [preflight](../schemas/tmcp-composition-preflight-v0.1.schema.json), [semantic proposal](../schemas/tmcp-semantic-proposal-v0.1.schema.json), [composition plan](../schemas/tmcp-composition-plan-v0.1.schema.json), [project recipe](../schemas/tmcp-project-composition-recipe-v0.1.schema.json), [project recipe promotion](../schemas/tmcp-project-recipe-promotion-v0.1.schema.json), [evaluation plan](../schemas/tmcp-composition-evaluation-plan-v0.1.schema.json), [evaluation summary](../schemas/tmcp-composition-evaluation-summary-v0.1.schema.json), [runtime next](../schemas/tmcp-runtime-next-v0.1.schema.json), [recompiled packet](../schemas/tmcp-recompiled-packet-v0.1.schema.json), [run receipt](../schemas/tmcp-run-receipt-v0.1.schema.json), [run session](../schemas/tmcp-run-session-v0.1.schema.json), and [promoted harvest graph](../schemas/tmcp-promoted-harvest-graph-v0.1.schema.json). These schemas are strict about their required fields and permit only documented additive surfaces where indicated.

## Migration Rules

When the packet schema changes:

- Keep the old schema document in `schemas/`.
- Add a migration note to this file.
- Add or update golden packet fixtures.
- Keep MCP tool responses explicit about the packet schema they return.
