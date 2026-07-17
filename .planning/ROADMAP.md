# Roadmap: TMCP Modernization

**Created:** 2026-07-10
**Mode:** modernization
**Plan Format:** Vertical, independently verifiable milestones from
`docs/modernization/EXEC_PLAN.md`.

### Phase 0: Release safety emergency gate

**Goal:** Eliminate release-archive disclosure risk.
**Requirements:** MOD-SAFE, MOD-OPS
**Depends on:** None
**Plans:** Complete 2026-07-11

### Phase 1: Contract freeze and target baseline

**Goal:** Establish canonical tool/version metadata and hermetic compatibility
fixtures.
**Requirements:** MOD-CONTRACTS, MOD-OPS
**Depends on:** Phase 0
**Plans:** Complete 2026-07-11

### Phase 2: Safe input and storage foundation

**Goal:** Centralize path, redaction, and persistence safety.
**Requirements:** MOD-SAFE, MOD-STATE, MOD-ARCH
**Depends on:** Phase 1
**Plans:** Complete in the 0.5.x runtime baseline

### Phase 3: Compose/recompile vertical slice

**Goal:** Deliver the primary task journey with explicit sessions and readable
output.
**Requirements:** MOD-FLOW, MOD-CONTRACTS, MOD-ARCH
**Depends on:** Phase 2
**Plans:** Complete in the 0.5.x runtime baseline

### Phase 4: Advanced discovery migration

**Goal:** Migrate harvest, recommendation, promotion, and evaluation to the
safe core.
**Requirements:** MOD-SAFE, MOD-CONTRACTS, MOD-ARCH
**Depends on:** Phase 2
**Plans:** Complete in the 0.5.x runtime baseline

### Phase 5: Evidence-review vertical slice

**Goal:** Make review evidence, artifact writes, and AIOS choices explicit.
**Requirements:** MOD-STATE, MOD-FLOW
**Depends on:** Phase 2
**Plans:** Complete in the 0.5.x runtime baseline

### Phase 6: Thin-adapter cutover and deletion

**Goal:** Complete the modular migration and remove old implementations.
**Requirements:** MOD-ARCH, MOD-CONTRACTS
**Depends on:** Phases 3–5
**Plans:** Complete in the 0.5.x runtime baseline

### Phase 7: Release hardening and adversarial review

**Goal:** Complete validation, cleanup, and release readiness.
**Requirements:** MOD-OPS, MOD-SAFE
**Depends on:** Phase 6
**Plans:** Complete for release 0.5.7

### Phase 8: Compositional Intelligence 0.6

**Goal:** Compile substantial prompts into source-backed typed skill graphs,
ordered execution recipes, graph-aware runtime updates, and evaluated compound
outcomes while preserving deterministic compatibility.
**Requirements:** MOD-FLOW, MOD-CONTRACTS, MOD-STATE, MOD-SAFE, MOD-OPS
**Depends on:** Phases 2–7
**Plans:**

- Composition foundation: hardening in progress — `280fbb6` closes reference
  authority, multi-root identity, and phase-local read gaps; `a70fd04` adds
  provenance-bound manifest-first indexing, lazy block hydration, compact
  always-on context, and compatibility-safe preflight extensions. `9b4d72e`
  closes lexical task-identity safety; `5fcefab` adds compound-task facets,
  validated route identity, safe shortcut gating, and graph-aware facet diffs.
  `271ed29` closes broad default activation with source-role hardening, a
  one-skill compatibility bootstrap, and rejection diagnostics; `df3c8e2`
  preserves exact route phrases. `f190a82` completes typed artifact handoffs:
  source-cited contracts, staged exact-evidence gates, tamper rejection,
  same-graph runtime continuity, recipe/receipt persistence, and handoff diffs.
  `9f13813` adds safe, root-independent fixture materialization and a
  content-addressed, no-oracle host-intake plan with bounded preflights for all
  routing and behavioral requests. `5745420` replays every proposal with those
  exact limits, emits full compiler recipe/gate/context evidence, and labels
  wrong-order and ablation cases as counterfactual controls rather than valid
  composition. `d70b4e7` normalizes benchmark graph provenance to compiler
  content-and-edge identity across source-root relocation and same-path content
  edits. `7f72822` adds bounded host/evaluator fact bundles, exact replay
  assembly, per-rubric evidence bindings, safe receipt projection, runtime
  phase/gate/handoff lineage checks, and direct-domain artifact caps. `6fdf9de`
  separates benchmark assembly/replay and behavior-manifest responsibilities
  behind compatibility facades, restoring the hard module-size gate. A canonical
  committed release bundle and honest phase-capsule context accounting are next.
  `9f26520` keeps preflight coverage below the test-size gate.
- Semantic compiler: complete — validated task model, typed graph, dependency
  closure, phase ordering, bridges, diagnostics, and content-derived provenance.
- Runtime integration: complete — evidence-driven gates, graph-bound typed
  handoffs, same-graph continuity, phase trace, obligations, and graph-aware
  diffs.
- Proof and learning: hardening required — executable workspaces, exact host
  intake manifests, compiler replay, root-independent graph identity, and
  bounded replay-assembled observations now exist; a canonical release bundle
  and tamper-resistant phase-capsule context accounting remain.
- Release proof: pending — version 0.6.0 remains blocked until the executable
  harness and real host-run observations meet every routing, safety, lift,
  ordering, provenance, and context threshold.

---
*Last updated: 2026-07-17 for benchmark domain-size refactoring*
