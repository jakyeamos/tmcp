# TMCP Packet Spec

Schema: `tmcp-skill-packet-v0.2`

A TMCP packet is the smallest task-specific skill bundle that preserves required behavior for the current objective. It is not a transcript and not a generic skill dump.

The compatibility policy is documented in [PACKET_STABILITY.md](PACKET_STABILITY.md). The JSON Schema draft lives at [schemas/tmcp-skill-packet-v0.2.schema.json](../schemas/tmcp-skill-packet-v0.2.schema.json).

Adaptive workflow-pack artifacts are separate from compiled task packets. They use schema `tmcp-adaptive-workflow-pack-v0.1` and are emitted by `tmcp_recommend_workflows` to capture harvested source maps, operating profile, default templates, custom workflow ideas, routing triggers, process gaps, and approval-gated next workflow selection.

Composable runtime packets (`tmcp-composed-packet-v0.1`) and the Adaptive Packet Runtime design are documented in [ADAPTIVE_PACKET_RUNTIME.md](ADAPTIVE_PACKET_RUNTIME.md).

## Composed Packet Fields (`tmcp-composed-packet-v0.1`)

`tmcp_compose_packet` returns a composed runtime packet. In addition to the required v0.1 fields, composed packets now include:

| Field | Meaning |
| --- | --- |
| `task_identity` | Structured task classification: `primary`, `secondary`, `active_routes`, `confidence`, `signals`. |
| `compiled_from` | Provenance for the compile: `graph_version`, `route_catalog_version`, `seed_id`, `cache_policy`. |
| `packet_markdown` | Human-readable operating contract rendered from structured packet fields. |
| `shortcut_candidate` | Advisory compiled-route shortcut metadata with `compiled_from` provenance. |
| `family_context` | Optional skill-family orchestration context from scoped seeds or router skills. |
| `session` | Optional reference to one explicitly persisted project-local latest-packet record. |

`tmcp_runtime_next` may also return `task_identity` for the current runtime state and `task_identity_delta` when `previous_task_identity` is supplied. With `output_mode: "full"` and `previous_packet`, TMCP returns `tmcp-recompiled-packet-v0.1` containing a full regenerated packet plus `packet_diff`.

Composition and runtime routing are stateless by default: `cache_policy` defaults
to `none`. Pass `cache_policy: "global"` only when the caller explicitly wants
to read advisory promoted graphs and receipts from `TMCP_HOME`.

## Packet Sessions

`tmcp-run-session-v0.1` is a redacted, project-local record for the latest
packet in one explicitly named run. It is not a public tool response schema:
the composed or recompiled response carries a `session` reference instead. That
reference identifies the record schema, opaque key, redacted path, revision, and
current packet id without persisting the supplied raw session identifier. Session
identifiers are labels, not secret material.

Sessions require a secure-persistence host and an explicit absolute project path. Creation
does not replace an existing record, and a full recompile serializes its update
against the current revision. There is intentionally no automatic session,
global lookup, history, rollback, or concurrent-agent protocol. Consumers that
need a portable full recompile should pass `previous_packet` inline.

## Required Fields

| Field | Meaning |
| --- | --- |
| `schema` | Packet schema identifier. |
| `receipt_schema` | Traversal receipt schema expected for later learning or shortcut promotion. |
| `status` | Compilation status. |
| `adapter` | `standalone` or `aios`. |
| `task_id` | Selected task route, such as `audit`, `implementation`, `testing`, or `agent_workflow`. |
| `objective` | User objective used for routing. |
| `project_path` | Project or source scope. |
| `source_graph_version` | Hash of the packet graph inputs. |
| `entry_node` | First loaded route node. |
| `selected_nodes` | Ordered task, module, source, and branch nodes used by the packet. |
| `skipped_nodes` | Plausible nodes skipped because they did not add useful behavior. |
| `selected_branches` | Active branch decisions and reasons. |
| `source_skill_nodes` | Harvested or selected source nodes. |
| `substance_check` | Assessment of whether selected nodes contain concrete playbook guidance or only broad process scaffolding. |
| `behavior_atoms` | Small behavior units preserved by the packet. |
| `shortcut_candidate` | Shortcut status and fallback. |
| `transition_trace` | Router transitions and reasons. |
| `traversal_fingerprint` | Stable hash for repeated route comparison. |
| `token_estimates` | Custom packet and broad-baseline token estimates. |
| `output_contract` | Obligations the agent must preserve when using the packet. |
| `packet_markdown` | Human-readable packet rendering. |

## Harvest Source Node

Harvested source nodes include:

- `id`
- `root_path`
- `path`
- `relative_path`
- `title`
- `source_type`
- `source_tier`
- `frontmatter`
- `token_estimate`
- `behavior_atoms`
- `guidance_labels`
- `keywords`
- `excerpt`
- `redactions`

Source types are descriptive, not vendor-specific. Examples include `skill_definition`, `agent_operating_contract`, `cursor_rule`, `github_process`, `workflow_prompt`, `project_documentation`, and `markdown_process_doc`.

## Substance Check

`substance_check` prevents TMCP from overstating what it knows. It reports:

- `level`: `process_only`, `thin_domain_signals`, or `source_backed_playbook`
- `has_domain_playbook`: whether harvested sources contain actionable task guidance
- `issues`: why the packet is thin
- `fallback_policy`: how the agent should proceed

When a packet is `process_only` or `thin_domain_signals`, TMCP should keep the routing, evidence, and output-contract behavior, but derive rubric substance from target repo evidence.

## Privacy

Harvest output is redacted by default. Consumers should treat `redaction_summary` as evidence that sensitive material existed and was intentionally omitted. Turning redaction off is only appropriate for trusted local debugging.

## AIOS Adapter

AIOS can return a richer packet with persisted traversal receipts, graph overlays, and learning hooks. Consumers should still rely on the common packet concepts above and not require AIOS-specific fields.
