# TMCP Packet Spec

Schema: `tmcp-skill-packet-v0.2`

A TMCP packet is the smallest task-specific skill bundle that preserves required behavior for the current objective. It is not a transcript and not a generic skill dump.

The compatibility policy is documented in [PACKET_STABILITY.md](PACKET_STABILITY.md). The JSON Schema draft lives at [schemas/tmcp-skill-packet-v0.2.schema.json](../schemas/tmcp-skill-packet-v0.2.schema.json).

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
- `keywords`
- `excerpt`
- `redactions`

Source types are descriptive, not vendor-specific. Examples include `skill_definition`, `agent_operating_contract`, `cursor_rule`, `github_process`, `workflow_prompt`, `project_documentation`, and `markdown_process_doc`.

## Privacy

Harvest output is redacted by default. Consumers should treat `redaction_summary` as evidence that sensitive material existed and was intentionally omitted. Turning redaction off is only appropriate for trusted local debugging.

## AIOS Adapter

AIOS can return a richer packet with persisted traversal receipts, graph overlays, and learning hooks. Consumers should still rely on the common packet concepts above and not require AIOS-specific fields.
