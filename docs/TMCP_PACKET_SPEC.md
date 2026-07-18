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
| `task_identity` | Structured task classification: `primary`, `secondary`, `active_routes`, `validated_routes`, `intent_facets`, `facet_signals`, `routing_status`, `confidence`, and `signals`. |
| `compiled_from` | Provenance for the compile: `graph_version`, `route_catalog_version`, `seed_id`, `cache_policy`. |
| `packet_markdown` | Human-readable operating contract rendered from structured packet fields. |
| `shortcut_candidate` | Advisory compiled-route shortcut metadata with `compiled_from` provenance. |
| `family_context` | Optional skill-family orchestration context from scoped seeds or router skills. |
| `composition_plan` | Optional validated `tmcp-composition-plan-v0.1` with task model, skill roles, typed edges, ordered stages, coverage, diagnostics, and graph provenance. |
| `semantic_proposal_validation` | Acceptance, errors, and warnings for the host proposal; rejected proposals do not activate fallback behavior. |
| `composition_diagnostics` | Missing capabilities, uncovered criteria, conflicts, rejected elements, truncation, and process-only warnings. |
| `project_recipe` | Optional metadata for an explicitly named, reviewed project-local recipe revalidated against the current graph. |
| `session` | Optional reference to one explicitly persisted project-local latest-packet record. |

`tmcp_runtime_next` may also return `task_identity` for the current runtime state and `task_identity_delta` when `previous_task_identity` is supplied. With `output_mode: "full"` and `previous_packet`, TMCP returns `tmcp-recompiled-packet-v0.1` containing a full regenerated packet plus `packet_diff`.

Composition and runtime routing are stateless by default: `cache_policy` defaults
to `none`. `project` opts into explicitly reviewed project-local recipes;
`global` separately opts into advisory promoted graphs and receipts from
`TMCP_HOME`. No policy promotes a recipe automatically.

## Task Identity Safety

`task_identity` separates **what kind of work the prompt contains** from
**which catalog routes have been validated for activation**. `intent_facets`
is the ordered set of deterministic work modes found in the objective and
latest user message (for example `discovery`, `planning`, `implementation`,
`verification`, and `lifecycle`). `facet_signals` preserves the corresponding
prompt evidence. Facets describe the shape of a substantial task; they are not
instructions and never activate a skill or route by themselves.

`active_routes` contains threshold-validated catalog routes plus any explicit
route affinity supplied by a matched scoped family. `validated_routes` records
only the threshold-validated catalog routes (or later TMCP-validated route
proposals). A low-scoring catalog hint, a facet, and a source-name coincidence
are insufficient. `routing_status`
states which safe identity source won:

| Status | Meaning |
| --- | --- |
| `catalog_match` | One or more catalog routes cleared the deterministic activation threshold. |
| `family_match` | A scoped family/seed supplied the task identity and its explicit route affinity. |
| `compound_fallback` | No route or family was validated, but two or more intent facets establish a substantial composite task. |
| `unresolved` | Neither a validated route/family nor enough facets establish a safe nontrivial identity. |

For `compound_fallback`, `primary` is `compound_task` and `active_routes` is
empty. This preserves a useful structural identity without pretending that a
keyword match selected an instruction source. `unresolved` normally uses the
compatibility primary `general_task` with no active routes.

A shortcut candidate is eligible only when a scoped family is matched or an
active catalog route is validated for the current compile. `compound_task`,
`general_task`, low-confidence hints, and facets alone are ineligible for
shortcut reuse or promotion. Recompilation reports changes to routes, validated
routes, facets, and routing status so a prior shortcut cannot silently survive
an identity shift.

## Assisted Composition Contracts

For substantial work, `tmcp_prepare_composition` returns `tmcp-composition-preflight-v0.1`: a compact content-addressed behavior-manifest index, bounded hydrated source blocks, roles/digests, deterministic identity, diagnostics, and a `tmcp-semantic-proposal-v0.1` starter. TMCP ranks blocks before applying limits, selects governing sources first, and preserves active/supporting candidates only while the full index-plus-hydration budget stays within the target; the rest remain deferred. The host supplies semantic judgment, but every skill role and typed relationship must cite returned blocks.

The manifest index is deliberately metadata-only: it carries deterministic identity and block counts, while the selected source slices carry the content, source role, content-bound source digest, visible-content digest, behavior-manifest digest, and behavior-block digest needed for provenance. `diagnostics.context_cost` reports always-on index tokens, hydrated block tokens, naïve full-source tokens, total preflight context, target feasibility, and bounded/deferred block counts. The hard token boundary includes the index. Governing-source target exceptions and a single minimum-active-skill bootstrap are explicit in diagnostics; remaining non-governing blocks defer when the computable target has no room. Legacy source records without full-source token estimates retain their deterministic bounded path and report that the target was not computable. Supporting references remain evidence only; they never activate behavior.

TMCP validates the proposal before compiling it. Unknown nodes, unsupported relationships, cycles, active conflicts, missing citations, and attempts to override governing instructions are rejection conditions. The preflight's `relationship_type_semantics` makes direction explicit: `requires`, `consumes`, and `verifies` order `to` before `from`; `precedes`, `enables`, and `produces` order `from` before `to`; `complements` adds no order; and `conflicts_with` forbids same-phase activation. An accepted proposal becomes `tmcp-composition-plan-v0.1`; a rejected proposal produces diagnostics and no semantic activation. Omitting `semantic_proposal` preserves the existing deterministic composed-packet contract.

The plan activates the current phase and defers later stages with entry conditions and explicit handoffs. Its optional `tmcp-composition-runtime-capsule-v0.1` is a closed compiler-issued digest binding the semantic task identity, preparation controls, cited source slices, and phase binding without persisting source prose or runtime context. A capsule-only recompile restores omitted preparation controls from that binding; an explicitly different control cannot silently reuse the old graph and requires a fresh composition. Runtime recompile accepts only a fresh matching harvest; it inerts a retained graph after a redirect or material identity shift unless a fresh proposal or reviewed project recipe is supplied. Missing, partial, or invalid capsule provenance remains inert as `composition_provenance_status: runtime_capsule_invalid` across session reloads and retries until fresh composition replaces it. The agent executes the plan; TMCP does not run tools or mutations. Unmet gates remain obligations unless the user explicitly redirects the work.

The machine-readable definitions live in [behavior manifests](../schemas/tmcp-behavior-manifest-v0.1.schema.json), [composition preflight](../schemas/tmcp-composition-preflight-v0.1.schema.json), [semantic proposal](../schemas/tmcp-semantic-proposal-v0.1.schema.json), [composition plan](../schemas/tmcp-composition-plan-v0.1.schema.json), [runtime capsule](../schemas/tmcp-composition-runtime-capsule-v0.1.schema.json), and [project-local recipe](../schemas/tmcp-project-composition-recipe-v0.1.schema.json). Evaluation variants and observed-result summaries use [composition evaluation plan](../schemas/tmcp-composition-evaluation-plan-v0.1.schema.json) and [composition evaluation summary](../schemas/tmcp-composition-evaluation-summary-v0.1.schema.json).

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
Session persistence retains the closed plan, its runtime state, and safe receipt
binding fields, while omitting regenerated `composition_runtime` and expansive
composition diagnostics so recoverable packets remain within the bounded
project-local record budget.

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
- `source_role`
- `activation_eligible`
- `content_digest`
- `frontmatter`
- `token_estimate`
- `behavior_atoms`
- `guidance_labels`
- `keywords`
- `excerpt`
- `redactions`

Source types are descriptive, not vendor-specific. Examples include `skill_definition`, `agent_operating_contract`, `cursor_rule`, `github_process`, `workflow_prompt`, `project_documentation`, and `markdown_process_doc`.

Source roles govern activation. `governing_instruction` and `active_skill` may contribute behavior. `supporting_reference` may supply reads or evidence but never instructions. `evidence_only` remains inactive; test, fixture, and example paths receive this role unless explicitly scoped. Content digests, rather than path names alone, participate in graph provenance.

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
