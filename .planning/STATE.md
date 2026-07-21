# Planning State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-11)

**Core value:** Deliver a trustworthy, portable packet compiler with safe local
file boundaries and a coherent agent-facing workflow.
**Current focus:** Verify the clean release package, then execute the
preregistered composition-lift campaign only with explicit host/evaluator
authority and a real external-run adapter.

## Milestone

**Name:** TMCP Compositional Intelligence 0.6
**Status:** `44911f0` pins the current no-call campaign handoff after
`4c634e4` recorded the proposal-activation delta diagnostic and the
held dogfooded guidebook pattern. The branch also carries the independent-rejudge
envelope and non-mutating manual-review promotion candidate command. Focused
composition/guidebook checks are green.
0.6.0 still requires real host/evaluator/rejudge outcomes and the stronger
real-task corpus. An authorized one-cell external runner plus independent judge
pilot now proves launchability only; it is not a campaign result, receipt, lift,
promotion, or release claim. The pilot also exposed missing rendered-browser
verification and incomplete clean-room skill isolation.
**Started:** 2026-07-17

## Active Phase

- **Phase:** Compositional Intelligence 0.6
- **Slug:** `compositional-intelligence-0.6`
- **Status:** The branch now carries `tmcp-composition-lift-rejudge-envelope-v0.1`
  and `tmcp-guidebook-promotion-candidate-v0.1`. The promotion command validates
  campaign binding, distinct evaluator identities, all 540 cell dimensions, and
  agreement tolerance, then emits `eligible_for_manual_review` with
  `auto_apply:false`; it never mutates the guidebook. Focused checks and the
  documentation audit pass. No model call, receipt, lift, promotion, or release
  claim was made. The exact feature tip `53e7d47a29f3907dd952ddbea5ca4e476e142520`
  passed the reproducible package gate: 952 tests in 378.921s (4 skips),
  archive digest
  `c5508866118833a1cd6c0f72394d0fc926fde05daaf652ed5a612cfd99101e4c`, and
  manifest digest `ec7d09ab2f7f35ab5c08802eef1fbcb016c81d594103e26edfafb93cfcbdcbd8`.
  `1d4591d` also makes the static audit fail closed on eligible entries missing
  the non-auto-apply policy, evidence references, or primary/independent-rejudge
  replication markers. `4c634e4` records a deterministic compatibility-vs-
  proposal source-activation delta, preserves the one-skill bootstrap cap, and
  adds the held `composition.proposal-activation-delta` guidebook/catalog entry;
  its diagnostic explicitly carries `causal_claim: none`. Focused verification
  is green (26 composition/guidebook tests plus Ruff and audit). The current
  static dogfood packet receipt is recorded at
  `/private/tmp/tmcp-receipt-home-20260721/receipts/2026-07/packet-a7fa53ed6280-7c843241353794bcf2afb6f0dd6db2f9-76d289fcbe-815d7ec4a63a4a2884ab480bcc5ccd27.json`.
  `44911f0` records the reproducibility anchor for the no-call handoff:
  campaign `composition-lift-campaign-01696e55d67fa8ecb6e5`, digest
  `01696e55d67fa8ecb6e5b48ce5a919bdc8c68a2c239bdafd8a4389cf7514799a`, with
  180 baseline and 360 causal cells. Opaque runner and blind-judge bundles
  were prepared and inspected without execution or receipt persistence; their
  digests are recorded in `docs/COMPOSITION_BENCHMARK.md`. The authorized
  external pilot is recorded there with raw artifact digests and a 0.738
  independent judge score, but no campaign evidence was assembled. Next: add a
  bounded external-run adapter, provision rendered verification for UI fixtures
  (or keep that gate blocked), and only then schedule the full 540 runner plus
  540 judge cells.
- **Plan:** `.planning/ROADMAP.md` and `docs/COMPOSITION_BENCHMARK.md`

## Completed Scope

- `a0ee07c` strengthens all five behavioral fixtures with domain-specific,
  observable `Output contract:` handoffs and adds a preparation-time validator
  plus focused preflight tests. A separate Markdown contract section was
  rejected during dogfood because bounded hydration could select it without
  the role's inputs/outputs; keeping the contract inline preserves grounding.
  No model call, receipt, promotion, lift, or release claim was made.

- `af42a44` adds `scripts/audit_skill_guidebook.py`, the initial held catalog entries,
  projection metadata parity, and regression tests. The audit is documentation
  integrity only: controlled claims need an experiment ID found in source-only
  evidence, and campaign plans or synthetic traces cannot promote guidance.

- The rejudge/promotion slice adds versioned schemas, pure validation/scoring,
  CLI coverage, and package/install manifests. It creates a manual-review
  candidate only after replicated trusted evidence; catalog entries remain held
  until a human decision.

- `1d4591d` adds negative audit coverage for policy weakening and records the
  durable-entry invariant in the guidebook. The checked-in catalog still has
  five held entries and zero controlled claims.

- `4c634e4` adds a non-authoritative `proposal_activation_delta` packet
  diagnostic comparing compatibility selection with validated semantic roles;
  active and deferred sources remain separate, and no quality or causal claim is
  inferred from routing expansion.

- `44911f0` pins the current fixture-bound no-call campaign identity and source
  digests in `docs/COMPOSITION_BENCHMARK.md`; the handoff remains unevaluated
  and cannot support promotion.

- The prepared runner and blind-judge bundles are transport-only artifacts;
  their opaque field boundary was inspected and no controller fields leaked.

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
- Keep the checked-in guidebook and pattern catalog synchronized through the
  read-only guidebook audit; preserve evidence/status/promotion metadata and
  fail closed on unsupported controlled claims.
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
python3 scripts/audit_skill_guidebook.py
python3 scripts/check_release_package.py . --verify-reproducible
```
