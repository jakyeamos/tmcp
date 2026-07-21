# Planning State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-11)

**Core value:** Deliver a trustworthy, portable packet compiler with safe local
file boundaries and a coherent agent-facing workflow.
**Current focus:** Verify the clean release package, then execute the
preregistered composition-lift campaign only with explicit host/evaluator authority.

## Milestone

**Name:** TMCP Compositional Intelligence 0.6
**Status:** `a0ee07c` hardens the five behavioral fixtures with observable,
provenance-friendly output contracts and rejects expected skills that omit
them. The full 939-test readiness command completed in 493.197s (8:13.8
wall), so the isolated scoped Pre-CR policy is set to 600s. 0.6.0 still
requires real host/evaluator outcomes and the stronger real-task corpus.
**Started:** 2026-07-17

## Active Phase

- **Phase:** Compositional Intelligence 0.6
- **Slug:** `compositional-intelligence-0.6`
- **Status:** `a0ee07c` adds a deterministic corpus-readiness gate and explicit
  output contracts to every expected behavioral skill, keeping role and handoff
  claims inside the bounded cited slice. The direct readiness command ran 939
  tests in 493.197s (8:13.8 wall); the isolated 600s policy covers the observed
  runtime while the global 90s hook remains unchanged. This run produced no
  model call, receipt, promotion, or release evidence.
  Next: reproducible package verification, then explicitly authorized host and
  external-evaluator evidence.
- **Plan:** `.planning/ROADMAP.md` and `docs/COMPOSITION_BENCHMARK.md`

## Completed Scope

- `a0ee07c` strengthens all five behavioral fixtures with domain-specific,
  observable `Output contract:` handoffs and adds a preparation-time validator
  plus focused preflight tests. A separate Markdown contract section was
  rejected during dogfood because bounded hydration could select it without
  the role's inputs/outputs; keeping the contract inline preserves grounding.
  No model call, receipt, promotion, lift, or release claim was made.

_(1 older entries trimmed)_

_(truncated for length)_

## Workflow Notes

- Release packages must use the Git-tree archive policy and pass the
  reproducibility check before publication.
- Quality Runner remains advisory-only; the prior QR plan is parked.
- Preserve public MCP/CLI contracts through a versioned compatibility adapter.
- Keep the CLI parser pure and API-owned; reject options outside the selected
  schema and do not move filesystem, environment, process, redaction, storage,
  or transport authority into `tmcp_runtime/api/cli.py`.
- Keep harvest argument projection read-only and service-owned, with bounded
  scan/read budgets; roots, writes, redaction, sessions, and transport remain
  adapter authority.
- Keep doctor/status report assembly pure and data-only; the adapter retains
  environment probes, path redaction, capability checks, and transport.
- Keep harvest service orchestration read-only; the adapter owns output roots,
  atomic persistence, artifact aliases, and final path redaction.
- Keep evaluator planning/scoring free of storage/output-root authority; the
  adapter owns input budgets, manifests, persistence, and aliases.
- Keep packet-inclusion expectations and composed-packet diffing pure; the
  evaluator injects only the adapter's data-only compose callback.
- Keep evaluator decomposition, static review, variant generation, and
  observable-contract policy pure over supplied text and pattern catalogs.
- Keep trace normalization, dimension scoring, aggregation, guidebook feedback,
  and report assembly pure; the facade retains input loading/redaction.
- Keep guidebook rendering, pattern-catalog merging, and advisory formatting
  runtime-owned over safe source text; legacy script aliases must not become
  server dependencies.
- Keep redaction primitives in `tmcp_runtime/safety`; the historical script
  module is a compatibility facade and must not be imported by runtime safety.
- Keep MCP framing/JSON-RPC, CLI output/error translation, and typed registry
  dispatch in `tmcp_runtime/adapters`; generic artifact-bundle persistence is
  runtime-owned while producer-specific output selection and capability checks
  remain adapter-owned.
- Keep optional AIOS execution in a redaction-aware runtime adapter; the legacy
  server may retain only compatibility wrappers and mutable test seams.
- Keep runtime-state/recompile orchestration in `tmcp_runtime.services.runtime`;
  inject source, cache-warning, and packet-composition callbacks from the
  adapter without moving filesystem or persistence authority into the service.
- Keep project-local session lifecycle orchestration in
  `tmcp_runtime.services.sessions`; inject the validated store factory and keep
  final response redaction at the adapter boundary.
- Keep generic artifact-bundle persistence in
  `tmcp_runtime.services.artifact_persistence`; inject redaction, path
  presentation, and verified storage callbacks without moving output-root
  selection or capability checks into the service.
- Keep receipt recording in `tmcp_runtime.services.receipts`; inject the clock,
  redaction, opaque identity, path creation, verified write, and public result
  callbacks while preserving adapter-owned seams.
- Keep global-promotion manifest assembly in
  `tmcp_runtime.services.global_promotion`; inject graph normalization,
  redaction, timestamp, and plan-building callbacks while retaining global-root
  selection, persistence gating, and cache authority in the adapter.
- Keep explain packet assembly and review-evidence parsing in runtime services;
  the adapter owns AIOS selection, source/cache access, persistence, and final
  response redaction.
- Treat legacy artifact migration as a read-only storage projection: normalize
  known old summaries into current contracts, prefer current files, never delete
  or rewrite source artifacts, and skip malformed inputs.
- Release composition/runtime/session dogfood lives in focused helpers; the
  main release checker remains an orchestration boundary and its size gate is clean.
- Artifact bundles accept only absent or empty destinations; reused artifact
  directories must use the verified per-file store rather than a bundle swap.
- Evaluation never re-reads a persisted plan's skill path while scoring; it
  composes the plan's redacted variant attachment through preharvested nodes.
- Artifact persistence is intentionally fail-closed without descriptor-relative
  no-follow primitives; a race-safe Windows implementation is required before
  cross-platform release claims can remain unconditional.
- Windows runs read-only and explicit fail-closed checks; the release-package
  smoke runs on every platform and verifies receipt denial where persistence is
  unavailable.
- MCP adapter/status safety coverage has a focused test module, keeping the
  server-domain test module below the repository source-size threshold.
- Packet sessions are explicit-only and latest-only: they require an absolute
  project root, do not replace an existing run, retain no global registry or
  history, and use a verified per-session lock for cooperative writers.
- Recompile policy is domain-owned and directly tested; source harvesting,
  composition, enrichment, and session persistence remain adapter/service work.
- Contextual composition policy, task-family routing, node ranking, and final
  packet construction/presentation are domain-owned and directly tested. Both
  composition owners are below the source-size limit.
- Family runtime transitions are domain-owned and directly tested; declared-read
  resolution and compose-node merging are now direct domain dependencies.
- The legacy standalone packet compiler is domain-owned; harvest classification
  consumes its behavior-atom catalog rather than maintaining a second copy.
- Review-profile vocabulary is domain-owned; standalone review and workflow
  recommendation consume its canonical selection and fallback policy.
- Review evidence, audit, remediation, validation, and rendering policy are
  domain-owned; the review adapter only orchestrates side effects and transport.
- Curated workflow catalog policy is domain-owned; recommendation, promotion,
  and global-cache selection no longer maintain adapter-local catalog copies.
- Workflow recommendation scoring is domain-owned and receives harvested-node
  text plus guidance-label mapping explicitly from the adapter.
- Adaptive workflow-pack construction and recommendation Markdown rendering are
  domain-owned; the adapter redacts results before persisting rendered artifacts.
- Promotion target selection and graph construction are domain-owned; graph
  edges derive workflow atoms from the canonical catalog, not harvested payloads.
- Global workflow activation is domain-owned; untrusted cache graphs contribute
  only validated canonical workflow IDs and retain advisory provenance.
- Composition provenance, shortcut eligibility, and rendering are domain-owned;
  recompile injects the domain renderer so both packet forms share one layout.
- Global promoted graphs and receipts are explicit opt-ins; no compose or runtime
  route reads them under the default `cache_policy=none`.
- Receipt construction and public acknowledgement are domain-owned. The adapter
  retains raw-to-redacted opaque identity, one UTC clock for receipt/path month,
  full nonce/path creation, persistence, cache ingress, and final redaction.
- Only literal `cache_policy=global` enables shared-cache reads; every other
  value is normalized to `none` before adapter, runtime, or compose use.
- Evaluation scoring receives a data-only composition callback from the adapter;
  it has no reverse import or introspection dependency on server internals.
- Skill-package, curated-template, and MCP-tool stability are separate scopes;
  their owners are frontmatter/package validation, the workflow catalog, and the
  public registry respectively.
- The domain-module size budget is test-enforced. Harvest, recommendation,
  promotion-planning, and review-plan policy are runtime-owned; the adapter
  retains source acquisition, redaction, and all durable-write authority.
- Optional-cache policy is runtime-owned and direct-tested. The adapter controls
  roots, catalog/schema injection, and persistence;…

_(truncated for length)_

## Accumulated Context

### Roadmap Evolution
- 2026-07-17: `d70b4e7` makes replay graph identity match compiler provenance
  across fixture-root relocation and same-path content edits; observation
  assembly and phase-capsule context accounting remain blockers.
- 2026-07-10: Modernization audit identifies P0 package disclosure risk and
  proposes a parallel v2 runtime behind stable entrypoints.
- 2026-07-11: Milestone 0 closes the package-disclosure blocker; next work
  freezes public contracts before core migration.
- 2026-07-11: Milestone 1 freezes all public contracts and removes the stale
  `0.3.0` MCP initialize response; safe IO/storage extraction is next.
- 2026-07-11: M2 adds contained harvest reads, decoded-JSON/path redaction,
  exact evaluation input boundaries, and descriptor-safe artifacts; evaluation
  and remaining writers are pending migration.
- 2026-07-11: Evaluation now uses data-only composition and safe artifacts;
  review, recommendation, promotion, cache, and receipt writers remained.
- 2026-07-11: Adversarial review removed a plan-path probe and surfaced the
  Windows secure-persistence gap; both are explicit M2 release conditions.
- 2026-07-11: GitHub Actions validation was restored after a job-level
  `runner.temp` context reference prevented every matrix job from scheduling.
- 2026-07-11: All remaining durable writers and global cache reads use the safe
  storage boundary; compatibility docs now distinguish portable analysis from
  secure persistence, with Windows intentionally failing write requests closed.
- 2026-07-11: Adversarial hardening makes auto review standalone, rejects
  symlink-derived default writes, bounds and canonicalizes cache input, treats
  Windows junctions as links, and runs portable package verification on Windows.
- 2026-07-12: M3 adds an explicit project-local compose → full-recompile
  session path while retaining inline previous-packet compatibility; a fresh
  adversarial pass closes relative-root and forged-lineage findings, then…
_(truncated)_

## Next Command

```bash
python3 -m unittest tests.test_tmcp_composition_preflight tests.test_tmcp_composition_source_activation
```
