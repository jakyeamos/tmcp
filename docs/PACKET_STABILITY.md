# Packet Stability

TMCP packets are intended to be stable enough for other tools to consume. The current public packet schema is `tmcp-skill-packet-v0.2`.

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

## Machine-Readable Schema

The JSON Schema draft lives at [schemas/tmcp-skill-packet-v0.2.schema.json](../schemas/tmcp-skill-packet-v0.2.schema.json). It is intentionally strict about required fields and permissive about additive fields.

## Migration Rules

When the packet schema changes:

- Keep the old schema document in `schemas/`.
- Add a migration note to this file.
- Add or update golden packet fixtures.
- Keep MCP tool responses explicit about the packet schema they return.

