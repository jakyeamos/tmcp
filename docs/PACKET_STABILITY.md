# Packet Stability

TMCP packets are intended to be stable enough for other tools to consume. The current public packet schema is `tmcp-skill-packet-v0.2`. Adaptive workflow-pack artifacts use `tmcp-adaptive-workflow-pack-v0.1`. Composable runtime artifacts use `tmcp-composed-packet-v0.1`, `tmcp-runtime-next-v0.1`, `tmcp-run-receipt-v0.1`, and `tmcp-recompiled-packet-v0.1`. Promoted harvest graphs use `tmcp-promoted-harvest-graph-v0.1`. See [ADAPTIVE_PACKET_RUNTIME.md](ADAPTIVE_PACKET_RUNTIME.md).

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

- `tmcp-composed-packet-v0.1`: `packet_id`, `active_instructions`, `required_reads`, `tool_script_prompts`, `verification_gates`, `stop_conditions`, `active_atoms`, `deferred_atoms`, `ignored_sources`, `conflicts`, `evidence_citations`, `receipt_template`, and `safety`.
- `tmcp-runtime-next-v0.1`: `packet_delta`, `next_verification_gate`, `warnings`, `task_identity`, optional `task_identity_delta`, and `safety`.
- `tmcp-recompiled-packet-v0.1`: `packet`, `packet_diff`, `recompile_reason`, `recompile_detail`, `validated_changes`, and `warnings`.
- `tmcp-run-receipt-v0.1`: `packet_id`, `activated_atoms`, `ignored_atoms`, `commands_run`, `verification_results`, `user_overrides`, `outcome`, and `trust`.
- `tmcp-promoted-harvest-graph-v0.1`: `source_nodes`, `behavior_atoms`, `workflow_nodes`, `edges`, and `trust`.

## Machine-Readable Schema

The packet JSON Schema draft lives at [schemas/tmcp-skill-packet-v0.2.schema.json](../schemas/tmcp-skill-packet-v0.2.schema.json). The adaptive workflow-pack schema lives at [schemas/tmcp-adaptive-workflow-pack-v0.1.schema.json](../schemas/tmcp-adaptive-workflow-pack-v0.1.schema.json). Composition schemas live at [schemas/tmcp-composed-packet-v0.1.schema.json](../schemas/tmcp-composed-packet-v0.1.schema.json), [schemas/tmcp-runtime-next-v0.1.schema.json](../schemas/tmcp-runtime-next-v0.1.schema.json), [schemas/tmcp-recompiled-packet-v0.1.schema.json](../schemas/tmcp-recompiled-packet-v0.1.schema.json), [schemas/tmcp-run-receipt-v0.1.schema.json](../schemas/tmcp-run-receipt-v0.1.schema.json), and [schemas/tmcp-promoted-harvest-graph-v0.1.schema.json](../schemas/tmcp-promoted-harvest-graph-v0.1.schema.json). These schemas are intentionally strict about required fields and permissive about additive fields.

## Migration Rules

When the packet schema changes:

- Keep the old schema document in `schemas/`.
- Add a migration note to this file.
- Add or update golden packet fixtures.
- Keep MCP tool responses explicit about the packet schema they return.
