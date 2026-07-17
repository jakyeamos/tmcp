# TMCP Adaptive Packet Runtime — Design & Implementation

Status: Phases 1–4 implemented (2026-07-07).

Related: [TMCP_PACKET_SPEC.md](TMCP_PACKET_SPEC.md), [PACKET_STABILITY.md](PACKET_STABILITY.md)

## Product thesis

Slash commands are manual imports. TMCP is the compiler.

Skill names are provenance, not user interface. The user describes work in natural language. TMCP compiles the strongest operating packet for the current phase, recompiles when evidence changes, and leaves an audit trail.

The agent-facing loop:

```text
user prompt
  -> substantiality gate (trivial/status work bypasses)
  -> tmcp_prepare_composition (bounded source slices)
  -> host semantic proposal (source-backed judgment)
  -> tmcp_compose_packet (validated typed graph and staged packet)
  -> agent executes the active stage under gates
  -> tmcp_runtime_next / tmcp_recompile_packet (mid-run recompile)
  -> tmcp_record_receipt (outcome)
```

The assisted path is for substantial multi-step, tool-using, high-stakes, or skill-relevant work and stays invisible to ordinary users. The host supplies semantic judgment; TMCP deterministically validates citations, relationships, ordering, conflicts, and precedence. Calling compose without a proposal preserves the original deterministic path.

Only governing instructions and active skills can activate behavior. Supporting references and evidence-only sources may inform provenance but cannot become instructions. TMCP compiles; the agent executes. Cache use, receipt recording, and promotion remain separate explicit choices, with `cache_policy=none` as the default.

The remainder documents the adaptive runtime foundations that the compositional layer builds on.

## Current architecture (baseline)

| Primitive | Tool / function | Role today |
| --- | --- | --- |
| Semantic preparation | `tmcp_prepare_composition` | Bound and rank source slices; publish the host proposal contract |
| Intake compile | `tmcp_compose_packet` → `_compose_packet()` | Harvest sources, score nodes, emit composed JSON packet |
| Route compile | `tmcp_explain` → `standalone_packets.compile_standalone_packet()` | Task routing to `@task:*` nodes with `packet_markdown` |
| Runtime delta | `tmcp_runtime_next` → `_runtime_next()` | Phase-aware atom/read/gate deltas; family seed transitions |
| Explicit session | `tmcp_compose_packet` / `tmcp_runtime_next` with `session_id` | Protected project-local latest packet for one serialized run |
| Receipts | `tmcp_record_receipt` → `_record_receipt()` | Advisory run receipts under `~/.tmcp/receipts/` |
| Family orchestration | `_compose_family_context()`, scoped seeds | Suppress sibling skills, chain phases, declared loads |
| Cached shortcuts | Promoted harvest graphs, scoped packet seeds | Curated compile recipes; not yet full provenance chain |

Schemas in play: `tmcp-composed-packet-v0.1`, `tmcp-runtime-next-v0.1`, `tmcp-recompiled-packet-v0.1`, `tmcp-run-session-v0.1`, `tmcp-skill-packet-v0.2`, `tmcp-scoped-packet-seeds-v0.1`.

What works well and should be preserved:

- Deterministic server functions with no hidden agent state; session persistence is explicit and project-local
- `ignored_sources`, `deferred_atoms`, `evidence_citations` as provenance hooks
- `family_context` + `phase_transitions` for mid-run skill-family chains
- Advisory trust model: packets never override system/developer/user instructions

---

## Gap 1 — Task identity is implicit, not first-class

### Problem

Today a composed packet exposes `objective`, `phase`, `active_atoms`, and optional `family_context`. Task type is inferred indirectly from keyword scoring (`_node_composition_score`), workflow catalog matches, and a separate `task_id` on routed packets (`audit`, `implementation`, etc.).

Agents and users cannot read a stable answer to: **"What task is this really?"** Multi-faceted work (e.g. redesign + motion + implementation + QA) collapses into atom lists without a semantic summary.

### Design

Add `task_identity` as a structured, first-class field on composed and recompiled packets.

```json
{
  "task_identity": {
    "primary": "frontend_product_redesign",
    "secondary": [
      "visual_design",
      "motion_interaction",
      "implementation",
      "accessibility_validation"
    ],
    "active_routes": [
      "ui_ux_redesign",
      "frontend_implementation",
      "motion_interaction",
      "freshness_research"
    ],
    "confidence": 0.82,
    "signals": [
      {
        "route": "ui_ux_redesign",
        "score": 4.5,
        "evidence": ["objective: redesign", "objective: visually striking"]
      }
    ]
  }
}
```

**Derivation rules (deterministic, no LLM inside TMCP):**

1. Run a **route catalog scorer** over `objective` + `latest_user_message` + runtime context (`files_changed`, `failures`, `browser_evidence`).
2. Map top-scoring routes to `primary` (highest) and `secondary` (score ≥ threshold, max 6).
3. When a scoped packet seed matches, seed `primary` from seed `id` / `name` and merge seed `behavior_atoms` into routes.
4. On recompile, compare new `task_identity` to `previous_task_identity`; emit `task_identity_delta` when primary or secondary sets change.

**Route catalog** (initial set, extensible in `tmcp_runtime/domain/routes.py`):

| Route ID | Trigger signals (objective / context) |
| --- | --- |
| `ui_ux_redesign` | redesign, visually striking, modern, polish, landing |
| `frontend_implementation` | implement, component, react, page, build |
| `motion_interaction` | motion, animation, interactive, micro-interaction |
| `freshness_research` | trend, current, modern, research |
| `accessibility_validation` | a11y, accessibility, contrast, reduced motion, WCAG |
| `performance_validation` | performance, bundle, latency, lighthouse |
| `debugging_regression` | bug, failing, failure, debug |
| `release_readiness` | release, ship, deploy, changelog |

Routes are not skills. They are compile-time labels that drive selection, gates, and markdown rendering.

### Schema change

Additive fields on `tmcp-composed-packet-v0.1` (per [PACKET_STABILITY.md](PACKET_STABILITY.md)):

- `task_identity` (object, optional in v0.1; recommended always present from implementation onward)
- `compiled_from` (object: `graph_version`, `seed_id`, `receipt_ids`, `cache_policy`)

Additive fields on `tmcp-runtime-next-v0.1`:

- `task_identity_delta` (object: `previous`, `current`, `changed_routes`, `reason`)

### Implementation

| Step | Location | Work |
| --- | --- | --- |
| 1 | `tmcp_runtime/domain/routes.py` | Route definitions, `_score_routes(objective, context) -> list[RouteScore]` |
| 2 | `scripts/tmcp_mcp_server.py` | `_derive_task_identity()` called from `_compose_packet()` and `_runtime_next()` |
| 3 | `scripts/tmcp_mcp_server.py` | Include `task_identity` in `packet_id` hash inputs when identity changes materially |
| 4 | `schemas/tmcp-composed-packet-v0.1.schema.json` | Document optional `task_identity`, `compiled_from` |
| 5 | `tests/test_tmcp_task_identity.py` (new) | Golden cases for redesign prompt, debug pivot, explicit skill override |

### Acceptance criteria

- Given *"Redesign these pages. Make them visually striking, interactive, modern, motion-rich, and production-ready"*, `task_identity.primary` is `frontend_product_redesign` or `ui_ux_redesign` and secondary includes motion + implementation + accessibility.
- `task_identity` appears in composed packet markdown (Gap 3).
- Recompile with only `files_changed: ["app/page.tsx"]` does not drop implementation route from secondary set.

---

## Gap 2 — Recompile is delta-only, not full packet regeneration

### Problem

`tmcp_runtime_next` returns `packet_delta` (activated/deactivated atoms, new reads, suggested phase). The agent must mentally merge delta into the previous packet. There is no:

- Explicit **Drop / Add / Reason** audit section
- Full regenerated operating contract
- Stable `recompile_reason` field for receipts

This makes mid-run alignment fragile and hard to inspect.

### Design

Introduce **full recompile mode** without breaking existing delta consumers.

**Option A (recommended):** extend `tmcp_runtime_next` with `output_mode`:

- `delta` (default) — current behavior
- `full` — return complete composed packet plus structured diff

**Option B:** new tool `tmcp_recompile_packet` — thin wrapper calling shared `_recompile_packet()`.

Both expose the same payload shape. Prefer Option A to avoid tool-surface sprawl; document `tmcp_recompile_packet` as a CLI alias only.

### New artifact: recompiled packet response

Schema: `tmcp-recompiled-packet-v0.1` (new file under `schemas/`)

```json
{
  "schema": "tmcp-recompiled-packet-v0.1",
  "previous_packet_id": "packet-abc123",
  "recompile_reason": "implementation_phase_detected",
  "recompile_detail": "Work moved from visual exploration into production implementation.",
  "packet": { "...": "full tmcp-composed-packet-v0.1 shape" },
  "packet_diff": {
    "dropped": [
      { "kind": "atom", "id": "freshness-research", "reason": "Implementation files changed." }
    ],
    "added": [
      { "kind": "skill", "id": "ui-implementation", "reason": "phase_transitions.runtime.activate_skills" }
    ],
    "unchanged": ["source-traceability"],
    "phase_change": { "from": "runtime", "to": "implementation" }
  },
  "agent_proposals": [],
  "validated_changes": []
}
```

**Recompile reason enum** (extensible):

| Reason | Detection |
| --- | --- |
| `user_redirect` | `latest_user_message` contains redirect terms (existing logic) |
| `phase_transition` | `family_context` + `phase_transitions` |
| `implementation_phase_detected` | UI files in `files_changed` after runtime/exploration phase |
| `verification_failure` | non-empty `failures` |
| `browser_evidence_available` | non-empty `browser_evidence` |
| `task_identity_shift` | `task_identity_delta` primary change |

**Agent proposal validation (safety):**

Agents may pass optional `proposed_changes` into recompile:

```json
{
  "proposed_changes": [
    { "action": "add_route", "route": "accessibility_validation", "reason": "Found missing aria labels" }
  ]
}
```

TMCP validates each proposal against the route catalog and harvested skill graph. Accepted proposals appear in `validated_changes`; rejected ones in `warnings` with graph reason. TMCP never applies proposals that reference unknown skills or routes.

### Implementation

| Step | Location | Work |
| --- | --- | --- |
| 1 | `tmcp_runtime/domain/recompile.py` | Parse compatibility input; resolve recompile reason; merge deltas; apply validated proposals; compute diff; render the recompile section |
| 2 | `scripts/tmcp_mcp_server.py` | `_recompile_packet(arguments)`: preserve source/session selection, re-compose and enrich from harvested nodes, then delegate pure recompile policy |
| 3 | `tmcp_runtime/domain/recompile.py` | `packet_diff(previous, current) -> packet_diff` |
| 4 | `scripts/tmcp_mcp_server.py` | Wire `_runtime_next()` `output_mode=full` to `_recompile_packet()` |
| 5 | `scripts/tmcp_launcher.mjs` | `runtime-next --output-mode full`; alias `recompile-packet` |
| 6 | `schemas/tmcp-recompiled-packet-v0.1.schema.json` | New schema |
| 7 | `tests/test_tmcp_recompile_domain.py` | Direct policy coverage for parsing, reason priority, merge, diff, proposals, and rendering |
| 8 | `tests/test_tmcp_recompile_packet.py` | Product-design family: runtime → implementation → polish-verify adapter path |

**State note:** The default remains stateless: an agent passes `previous_packet`
inline for a portable full recompile. When a caller explicitly supplies
`session_id` and an absolute `project_path`, TMCP stores one redacted latest-packet record
under that project and reloads it for a full recompile. This is a serialized
single-run convenience, not a global cache, history, rollback mechanism, or
automatic write path.

### Acceptance criteria

- `runtime-next --output-mode full` after implementation file changes returns a complete packet whose `active_instructions` reference implementation skills, not exploration-only atoms.
- `packet_diff.dropped` explicitly lists deferred research/trend atoms with reasons.
- `recompile_reason` is always a machine enum; `recompile_detail` is human-readable.

---

## Gap 3 — Composed packets are JSON-first; audit markdown is secondary

### Problem

`tmcp_explain` produces `packet_markdown` through `tmcp_runtime.domain.standalone_packets.render_standalone_packet_markdown()` for routed skill packets. `tmcp_compose_packet` returns JSON only. Agents and users lack a single inspectable markdown operating contract for composed/recompiled runs.

### Design

Add `packet_markdown` to composed and recompiled packets, rendered from structured fields — not hand-authored in parallel.

### Markdown template

Rendered by `tmcp_runtime.domain.packets.render_composed_packet_markdown(packet)`:

```markdown
# TMCP Packet

## Task Identity
Primary: frontend product redesign
Secondary: visual design, motion, UX polish, implementation QA

## Active Routes
- ui_ux_redesign
- frontend_implementation
- motion_interaction

## Loaded Skill Sources
- ui-ux-pro-max: visual redesign heuristics
- frontend-design: component implementation
- motion-system: interaction polish

## Selection Rationale
The user requested a redesign with production implementation, so design and frontend execution layers are both required.

## Excluded Skills
- backend-api: no backend change detected

## Operating Instructions
1. Inspect existing pages before designing.
2. ...

## Recompile Triggers
- New task phase detected
- Codebase reveals design-system constraints
- Implementation exposes accessibility risk

## Required Receipts
- Pages changed
- Skills/routes used
- Validation performed
```

Section mapping:

| Section | Source fields |
| --- | --- |
| Task Identity | `task_identity` (Gap 1) |
| Active Routes | `task_identity.active_routes` |
| Loaded Skill Sources | `evidence_citations` + selected node titles |
| Selection Rationale | `selection_rationale(packet)` from route scores + family context |
| Excluded Skills | `ignored_sources` + `deferred_atoms` |
| Operating Instructions | `active_instructions` |
| Recompile Triggers | static catalog + `family_context.phase_transitions` keys |
| Required Receipts | `receipt_template` + `verification_gates` |

For recompiled packets, prepend:

```markdown
## Recompile
Reason: implementation_phase_detected
Detail: Work moved from visual exploration into production implementation.

### Dropped
- broad trend ideation (no longer matches phase)

### Added
- component architecture rules
- accessibility validation
```

### Implementation

| Step | Location | Work |
| --- | --- | --- |
| 1 | `tmcp_runtime/domain/packets.py` | `render_composed_packet_markdown(packet) -> str` |
| 2 | `tmcp_runtime/domain/packets.py` | `selection_rationale(packet) -> str` (deterministic template from scores) |
| 3 | `scripts/tmcp_mcp_server.py` | Set `packet["packet_markdown"]` from the domain renderer |
| 4 | `tmcp_runtime/domain/recompile.py` | Prepend recompile diff to the injected composition renderer |
| 5 | `schemas/tmcp-composed-packet-v0.1.schema.json` | Optional `packet_markdown` property |
| 6 | `skills/tmcp/SKILL.md` | Require agents to surface `packet_markdown` in handoffs |
| 7 | `tests/test_tmcp_composed_markdown.py` (new) | Snapshot tests for markdown sections |

### Acceptance criteria

- Every `tmcp_compose_packet` response includes non-empty `packet_markdown`.
- Markdown includes Task Identity and Excluded Skills when `ignored_sources` is non-empty.
- Recompiled full mode appends Drop/Add sections matching `packet_diff`.

---

## Gap 4 — Resolved by hybrid compositional inference

### Legacy compatibility-path limitation

Direct compose without `semantic_proposal` still scores individual source nodes and intentionally retains these limitations:

- Decompose a rich prompt into concurrent routes with per-route rationale
- Select **scoped packet seeds** from natural language without near-explicit seed naming
- Roll up repeated patterns into cached shortcut routes while preserving graph provenance

The 0.6 assisted path resolves this for substantial work with prepare → host semantic proposal → deterministic graph validation/compilation. The legacy path remains for compatibility and trivial work.

### Design

Three layers, built in order.

#### Layer 4a — Route-aware compose selection

Use Gap 1 `task_identity.active_routes` to bias node scoring:

```python
def _node_composition_score(..., active_routes: list[str]) -> float:
    base = ...  # existing score
    route_boost = sum(
        ROUTE_CATALOG[route].source_boost(node)
        for route in active_routes
    )
    return base + route_boost
```

Each route defines:

- `objective_terms` — keyword/phrase hits
- `source_type_boosts` — e.g. `skill_definition` with slug patterns
- `file_context_boosts` — e.g. `.tsx` changes boost `frontend_implementation`
- `preferred_seeds` — scoped seed IDs

#### Layer 4b — Scoped seed auto-matching

Extend `_compose_family_context()`:

1. Score all harvested `scoped_packet_seed` nodes with `_scoped_seed_objective_score()` (exists) **plus** route-catalog alignment.
2. If top seed score ≥ `SEED_MATCH_THRESHOLD` (default 5.0), activate family context even when the user did not name the seed.
3. Emit `compiled_from.seed_id` on the packet.

Add seed fields (backward compatible):

```json
{
  "id": "frontend_redesign_runtime_v1",
  "name": "Frontend redesign runtime",
  "route_affinity": ["ui_ux_redesign", "frontend_implementation", "motion_interaction"],
  "objective_patterns": [
    "redesign",
    "visually striking",
    "motion-rich",
    "production-ready"
  ],
  "sources": [".agents/skills/ui-ux-pro-max/SKILL.md", "..."],
  "phase_transitions": { "...": "..." }
}
```

Ship a reference seed at `examples/seeds/frontend-redesign-runtime.json` (not auto-installed; copy-paste template).

#### Layer 4c — Cached shortcut packets (compiled views)

Shortcut candidates are **not** source of truth. They are advisory compile metadata; the current runtime emits them for provenance but does not reuse them as a memoized execution path.

```json
{
  "shortcut_candidate": {
    "status": "eligible",
    "shortcut_id": "frontend_redesign_runtime_v1",
    "compiled_from": {
      "graph_version": "sha256:...",
      "seed_id": "frontend_redesign_runtime_v1",
      "route_catalog_version": "2026-07-07",
      "receipt_count": 12
    },
    "regenerate_when": [
      "graph_version changes",
      "seed_id unpublished",
      "user_override present"
    ]
  }
}
```

Promotion path:

1. Repeated successful runs record receipts (`tmcp_record_receipt`).
2. `tmcp_promote_harvest` can promote a scoped seed + route pattern into global graph (existing).
3. Compose currently emits `shortcut_candidate` provenance only. It does not read a prior candidate or pre-seed `task_identity` or `family_context`; full selection runs on every composition. A future explicit-opt-in reuse path must validate current graph provenance before it can influence selection.

### Implementation

| Step | Location | Work |
| --- | --- | --- |
| 1 | `tmcp_runtime/domain/routes.py` | Route definitions with `source_boost()` |
| 2 | `scripts/tmcp_mcp_server.py` | Thread `active_routes` into `_node_composition_score()` |
| 3 | `scripts/tmcp_mcp_server.py` | Lower seed match threshold when route affinity overlaps ≥ 2 routes |
| 4 | `examples/seeds/frontend-redesign-runtime.json` | Reference scoped seed |
| 5 | `tmcp_runtime/domain/packets.py` | `shortcut_candidate_for_composed_packet(...)` with `compiled_from` |
| 6 | `tests/test_tmcp_route_inference.py` (new) | NL redesign prompt selects correct routes + seed |
| 7 | `tests/test_tmcp_skill_family_compose.py` | Extend with frontend redesign seed fixture |

### Acceptance criteria

- Natural-language redesign prompt activates a matching scoped seed when `route_affinity` aligns, without naming the seed.
- `selection_rationale` in markdown cites route scores, not only keyword luck.
- Shortcut candidate includes `compiled_from.graph_version`; changing a harvested skill changes the provenance that any future reuse path must validate.

---

## Rollout plan

### Phase 1 — Identity + markdown (Gaps 1 + 3)

Low risk, additive schema fields, immediate inspectability win.

1. `tmcp_runtime/domain/routes.py` + `_derive_task_identity()`
2. `render_composed_packet_markdown()` on every compose response
3. Tests + update `TMCP_PACKET_SPEC.md`

### Phase 2 — Full recompile (Gap 2)

1. `_recompile_packet()`, `packet_diff`, `output_mode=full`
2. `tmcp-recompiled-packet-v0.1` schema
3. Agent proposal validation (optional input)
4. CLI alias `recompile-packet`

### Phase 3 — Route-aware inference + seeds (Gap 4)

1. Route-biased scoring in compose
2. Seed `route_affinity` / `objective_patterns`
3. Reference `frontend-redesign-runtime` seed example
4. `compiled_from` + shortcut candidate provenance

### Phase 4 — Docs + agent contract

1. README lead: "Slash commands are manual imports. TMCP is the compiler."
2. `skills/tmcp/SKILL.md` happy path: compose → execute → recompile (full) → receipt
3. Golden packet fixtures for redesign flow in `tests/fixtures/`

---

## Compatibility and versioning

Per [PACKET_STABILITY.md](PACKET_STABILITY.md):

- Add optional fields to `tmcp-composed-packet-v0.1` and `tmcp-runtime-next-v0.1` — no schema bump required.
- New `tmcp-recompiled-packet-v0.1` is a wrapper schema; does not change composed packet v0.1.
- If required fields are added later, bump to `tmcp-composed-packet-v0.2` with migration note.
- Consumers must ignore unknown fields.

Tool names remain stable:

| User concept | Stable tool |
| --- | --- |
| `tmcp.compile()` | `tmcp_compose_packet` |
| `tmcp.recompile()` | `tmcp_runtime_next` with `output_mode: "full"` |
| Receipt | `tmcp_record_receipt` |

---

## End-to-end example: frontend redesign

**User:** Redesign these pages. Make them visually striking, interactive, modern, motion-rich, and production-ready.

### 1. Intake compile

```bash
node scripts/tmcp_launcher.mjs compose-packet \
  "Redesign these pages. Make them visually striking, interactive, modern, motion-rich, and production-ready." \
  --project-path "$PWD" --phase start --session-id redesign-run
```

Expected packet highlights:

- `task_identity.primary`: `ui_ux_redesign`
- `task_identity.secondary`: motion, implementation, accessibility, research
- `family_context.kind`: `scoped_packet_seed` (when seed present)
- `deferred_atoms`: implementation/polish skills until phase transition
- `packet_markdown`: full audit contract

### 2. Agent explores codebase

Agent reads pages, finds React + design system.

### 3. Mid-run recompile

```bash
node scripts/tmcp_launcher.mjs runtime-next \
  "Redesign these pages..." \
  --project-path "$PWD" \
  --current-phase runtime \
  --session-id redesign-run \
  --files-changed "app/page.tsx,components/Hero.tsx" \
  --output-mode full
```

Expected:

- `recompile_reason`: `implementation_phase_detected`
- `packet_diff.dropped`: trend research atoms
- `packet_diff.added`: `ui-implementation`, design-system reads, a11y gates
- `suggested_phase`: `implementation`

### 4. Receipt

```bash
node scripts/tmcp_launcher.mjs record-receipt packet-def456 \
  --activated-atoms "ui-implementation,ui-browser-verification" \
  --outcome passed
```

---

## Open questions

1. **Packet persistence:** Is inline `previous_packet` sufficient for v1, or should compose always write `.tmcp/runs/<id>.json` when `write_artifacts: true`?
2. **Route catalog ownership:** Ship catalog in-repo only, or allow project-local `.tmcp/route-catalog.json` overlays?
3. **LLM-assisted identity (resolved):** substantial work uses hybrid host-assisted semantics; TMCP deterministically validates citations, authority, conflicts, graph structure, ordering, and gates. Direct compose remains deterministic.
4. **Naming in public docs:** Product name "Adaptive Packet Runtime" vs internal "Context Packet Recompiler" — use both (product / implementation) per audience.

---

## File checklist (implementation)

| File | Action |
| --- | --- |
| `docs/ADAPTIVE_PACKET_RUNTIME.md` | This document |
| `tmcp_runtime/domain/composition.py` | Contextual gates, node scoring/selection, selected-node merging, source verification-gate filtering, and reference-read selection |
| `tmcp_runtime/domain/declared_loads.py` | Declared-read parsing, path normalization/matching, objective narrowing, and selected-source enrichment |
| `tmcp_runtime/domain/families.py` | Scoped-seed/router family resolution, primary-source matching, sibling deferral, and runtime phase-transition policy |
| `tmcp_runtime/domain/packets.py` | Final packet assembly, provenance, shortcut eligibility, and composed Markdown rendering |
| `tmcp_runtime/domain/recompile.py` | Pure recompile policy and Markdown diff rendering |
| `tmcp_runtime/domain/review_evidence.py` | Evidence parsing/contracts, rubric synthesis, and audit scoring/coverage policy |
| `tmcp_runtime/domain/review_profiles.py` | Review dimensions, coverage requirements, profile classification, and fallback vocabulary shared by standalone review and workflow recommendation |
| `tmcp_runtime/domain/review_results.py` | Remediation plans, implementation handoffs, review validations, and review-artifact Markdown rendering |
| `tmcp_runtime/domain/routes.py` | Route definitions and scoring |
| `tmcp_runtime/domain/standalone_packets.py` | Legacy standalone task/playbook packet compilation and Markdown rendering |
| `tmcp_runtime/domain/workflow_activation.py` | Objective scoring, canonical workflow rehydration, activation projection, and specialized workflow instructions for validated promoted graphs |
| `tmcp_runtime/domain/workflow_adaptive.py` | Scoped-seed projection, adaptive workflow-pack construction, custom-idea/overlap/process-gap policy, and recommendation Markdown rendering |
| `tmcp_runtime/domain/workflow_catalog.py` | Curated workflow definitions, candidate filtering, stability labels, and ID lookup shared by recommendation, promotion, and cache selection |
| `tmcp_runtime/domain/workflow_promotion.py` | Promotion target selection, scoped-seed precedence, canonical graph construction, and promotion Markdown rendering |
| `tmcp_runtime/domain/workflow_recommendations.py` | Workflow signal scoring, reasons, rubric/template and candidate-instance construction, required-evidence guidance, and source-scope policy |
| `scripts/tmcp_mcp_server.py` | Extend compose, runtime, markdown renderers |
| `schemas/tmcp-recompiled-packet-v0.1.schema.json` | New |
| `schemas/tmcp-composed-packet-v0.1.schema.json` | Add optional fields |
| `schemas/tmcp-runtime-next-v0.1.schema.json` | Add optional `task_identity_delta`, `output_mode` response shape |
| `examples/seeds/frontend-redesign-runtime.json` | New reference seed |
| `tests/test_tmcp_task_identity.py` | New |
| `tests/test_tmcp_recompile_domain.py` | Pure recompile policy coverage |
| `tests/test_tmcp_recompile_packet.py` | New |
| `tests/test_tmcp_composed_markdown.py` | New |
| `tests/test_tmcp_route_inference.py` | New |
| `docs/TMCP_PACKET_SPEC.md` | Cross-link + `task_identity` field table |
| `docs/PACKET_STABILITY.md` | Note `tmcp-recompiled-packet-v0.1` |
| `CHANGELOG.md` | Per-phase entries on ship |
