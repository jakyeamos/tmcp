# Planning State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-11)

**Core value:** Deliver a trustworthy, portable packet compiler with safe local
file boundaries and a coherent agent-facing workflow.
**Current focus:** Map the next authority-limited adapter extraction after the
CLI parser, harvest-argument, global-cache reader, adversarial safety
hardening, diagnostic-report, harvest-persistence, evaluator-persistence, and
packet-scoring cutovers.

## Milestone

**Name:** TMCP Modernization
**Status:** Milestone 3 adapter thinning and security hardening: pure domain,
service, artifact-manifest, receipt-cache, storage-ingress, CLI-parser, and
harvest-argument cutovers; explicit-only AIOS, receipt, and cache-opt-in
  boundaries plus CLI/harvest safety hardening, diagnostic-report assembly, and
  read-only harvest/evaluator persistence plus packet-scoring policy, report,
  rendering/advisory, input, compose-failure, mode-orchestration, and
  plan-construction, server renderer, and policy-catalog cutovers complete;
  map the next evaluator boundary.
**Started:** 2026-07-10

## Active Phase

- **Phase:** Compose and recompile vertical slice
- **Slug:** `tmcp-modernization`
- **Status:** Receipt/artifact construction and cache policy are pure-owned;
  storage owns bounded redacted cache reads, while adapter-owned roots, writes,
  identity, clock, output selection, redaction, and transport remain intact.
- **Plan:** `docs/modernization/EXEC_PLAN.md`

## Completed Scope

- Modernization baseline, parallel audit, target architecture, and executable
  milestone plan recorded under `docs/modernization/`.
- Isolated audit branch created from the 0.4.0 release baseline.
- Milestone 0 release safety completed on `codex/tmcp-modernization-v2`:
  Git-tree allowlist packaging, archive manifest verification, reproducibility,
  hermetic fixtures, and pre-merge release-evidence enforcement.
- Milestone 1 contract freeze completed in `5981dcd`: canonical version/tool
  registry, all alias/default fixtures, hermetic transport clients, live MCP
  metadata validation, and CI enforcement.
- Release fixture checksums are explicitly labelled in `0299ca4`, preserving
  the archive secret scanner while allowing deterministic contract fixtures.
- `b251e8e` preserves the strict scanner while excluding only lower-snake to
  upper-snake code assignments from high-entropy token detection.
- `65a1bfe` keeps the opaque-token regression test archive-safe by assembling
  its test value from short source literals.
- The committed M1 tree passes archive reproducibility and the extracted
  package verification suite (153 tests; source-only metadata check skipped).
- `49a87c9` separates CLI/launcher contract coverage from server-domain tests,
  removing the test-size quality warning without changing behavior.
- `3abe21c` moves harvest through `tmcp_runtime/safety` and its artifact output
  through descriptor-safe staged bundles. It adds 13 boundary tests; the full
  suite passes.
- `42b922f` adds redacted, bounded exact-file inputs for evaluation and a single
  text/JSON artifact store with descriptor-relative writes, directory identity
  checks, and fail-closed behavior when those primitives are unavailable. The
  evaluation/artifact boundary is covered.
- `587b8c1` moves skill evaluation onto those boundaries: data-only variant
  composition, bounded/redacted plan and evidence inputs, safe artifact writes,
  and one-read score persistence.
- `c31641a` removes the last plan-path filesystem probe from advisory analysis;
  evaluation variants are now composed from redacted in-memory node data only.
- `1e43ed0` restores the hosted verification matrix: job-level environment
  values now use the permitted `github.workspace` context instead of
  `runner.temp`, which GitHub rejected before scheduling any jobs.
- `32fb08d` moves review, recommendation, promotion, global cache, and receipt
  artifacts through the shared safe store; redacts direct user inputs before
  return/persistence; slugs implicit promotion directories; and publishes the
  storage capability through `doctor` and `status`.
- `4c5877f` keeps the new artifact-safety coverage in a focused test module;
  unsupported-platform denial remains an expected local skip.
- `3f4b74b` closes the adversarial boundary findings: review auto mode stays
  standalone; explicit AIOS review is preview-only; default writes reject
  symlink-derived roots; cache reads are bounded, schema-gated, and canonical;
  Windows junctions are link-like; artifact identities retain opaque collision
  resistance; and Windows runs the portable package smoke instead of skipping it.
- `c31a9ee` moves MCP adapter/status safety coverage into its own test module,
  restoring the repository test-source size gate.
- Clean package reproducibility passes at `1b3697f`; the extracted package
  verifies portable receipt denial as well as persistence-capable receipt flow.
- `2d04122` moves deterministic route inference into `tmcp_runtime/domain`,
  removing the first packet-domain owner from the legacy adapter.
- `31a1d47` adds explicit, redacted project-local packet sessions with absolute
  project roots, opaque keys, revision-locked latest records, pinned recompile
  lineage, portable denial, and CLI/MCP/package coverage.
- The clean committed tree at `fcbae5e` passes reproducible package verification,
  including the packaged session compose → recompile smoke.
- `6864350` moves composition/runtime/session release dogfood into focused
  helpers, preserves the main release checker as an orchestrator, and makes the
  shared release compile helper the documented local source-validation command.
- `401e125` moves compatibility parsing, reason/diff/merge policy, validated
  proposal application, and recompile Markdown rendering into
  `tmcp_runtime/domain/recompile.py`; the server retains only runtime state,
  source enrichment, composition/session selection, and transport assembly.
- `2eedd09` moves UI/contextual gates, source-gate filtering, and reference-read
  selection into `tmcp_runtime/domain/composition.py`, shared by compose and
  runtime without changing MCP/CLI behavior.
- `8b2cdb5` moves composed-packet provenance, shortcut eligibility, rationale,
  and Markdown rendering into the same composition domain; package smoke now
  asserts those public packet fields in extracted releases.
- `9cb3c8b` moves final composed-packet assembly into the composition domain:
  normalization/caps, deferred and ignored items, stable packet IDs, receipts,
  safety metadata, and Markdown all derive from one deterministic builder.
- `06defa0` moves scoped-seed and router task-family policy into
  `tmcp_runtime/domain/families.py`: family-context construction, primary and
  sibling decisions, and declared-load/slug normalization. The adapter retains
  source-text interpretation and runtime state; direct and integration tests
  cover threshold/tie, router, support-doc, and transition-only fallback paths.
- `9b6c47f` moves node scoring, ordering/caps, route/family interactions, and
  lexical selection helpers into `tmcp_runtime/domain/composition.py`; direct
  tests cover guardrails, metadata, fallback, and tie behavior. The commit gate
  reports that this owner is now above the 600-line source limit, so split it
  before the next feature change.
- `6cc0769` resolves that source-size gate by separating final packet
  construction, provenance, shortcut selection, and Markdown rendering into
  `tmcp_runtime/domain/packets.py`. Both domain owners are below the 600-line
  limit; the server keeps recompile renderer injection as a dependency-free
  callback.
- `32d6a9f` moves family-phase aliases, seed transition fallback, phase choice,
  skill activation/deactivation, and transition-only seed lookup into
  `tmcp_runtime/domain/families.py`, initially keeping declared-read resolution
  adapter-injected to preserve the domain dependency direction.
- `6a3acc8` moves declared-read parsing, path matching/narrowing, and selected
  source enrichment into `tmcp_runtime/domain/declared_loads.py`; runtime-family
  transitions now call that sibling domain directly, while composition owns the
  generic selected-node merge.
- `775782e` moves standalone task routing, source projection, substance checks,
  packet assembly, and Markdown rendering into
  `tmcp_runtime/domain/standalone_packets.py`; the adapter now only orchestrates
  its three existing public call paths.
- `7ed60d4` moves review profile dimensions, coverage requirements, profile
  selection precedence, and fallback behavior into
  `tmcp_runtime/domain/review_profiles.py`; standalone review and workflow
  recommendation now consume one canonical catalog.
- `516a497` moves review evidence parsing/contracts, rubric synthesis, audit
  scoring, remediation planning, handoff construction, validations, and Markdown
  rendering into `review_evidence.py` and `review_results.py`; the adapter now
  retains only harvest, redaction, artifact persistence, status, and MCP dispatch.
- `55ddb54` moves curated workflow definitions, candidate filtering, stability
  classification, and ID lookup into `tmcp_runtime/domain/workflow_catalog.py`;
  recommendation, promotion, and global-cache selection share one catalog owner.
- `f6f50f3` moves workflow signal scoring, recommendation reasons, rubric/template
  construction, required-evidence guidance, source-scope policy, and candidate
  instance construction into `tmcp_runtime/domain/workflow_recommendations.py`.
- `03009f9` moves scoped-seed projection, custom workflow ideas, adaptive-pack
  construction, duplicate-label analysis, process-gap policy, and recommendation
  Markdown rendering into `tmcp_runtime/domain/workflow_adaptive.py`; the adapter
  retains harvest, redaction, artifact persistence, and tool dispatch.
- `5ac3e2a` moves promotion target selection, scoped-seed precedence, graph
  construction, canonical catalog edges, and promotion Markdown rendering into
  `tmcp_runtime/domain/workflow_promotion.py`; the adapter retains harvest,
  redaction, artifact persistence, and global-cache activation.
- `52ad06b` moves global workflow objective scoring, canonical catalog
  rehydration, activation projection, and specialized workflow instructions into
  `tmcp_runtime/domain/workflow_activation.py`; cache validation and packet
  orchestration remain in the adapter.
- `80835ef` changes composition and runtime routing to `cache_policy=none` by
  default, with global promoted graphs and receipts available only through an
  explicit opt-in. The public fixture and CLI/MCP docs now record that behavior.
- `2299f88` removes evaluation's dynamic import and `__globals__` traversal of
  private server helpers. The MCP adapter injects a data-only composition
  callback, with direct dependency, transport, and no-filesystem-read regression
  coverage.
- `47f056c` removes the stale server `_string_sequence` helper and enforces the
  600-nonblank-line architecture budget for every domain module. Stability docs
  now distinguish stable skill packages, curated templates, and MCP tool
  contracts; shortcut candidates are documented as provenance-only metadata.
- 28b06ff moves harvest labels and source-node policy into pure domain modules
  and safe traversal, redaction, seed projection, and artifact orchestration into
  tmcp_runtime/services/harvest.py. The compatibility adapter now supplies only
  the evaluator-specific advisory callback and retained compatibility facades.
- d9422dc moves workflow recommendation assembly into a read-only runtime
  service. The adapter injects harvest advisories and compose preview, then
  retains redaction, artifact writes, and promotion/global-cache authority.
- b167af6 moves promotion target selection, graph construction, and result/status
  assembly into a read-only service. The adapter retains redaction, opaque
  storage keys, output-root validation, all artifact writes, and global-cache
  projection.
- e164875 moves in-memory standalone review-plan assembly into a pure service.
  The adapter retains source harvest, evidence parsing, redaction, output-root
  approval, artifact persistence, and AIOS dispatch.
- 0e84678 moves bounded cache limits, JSON-depth checks, normalized global graph
  construction, and cache-record projections into a pure storage policy module.
  The adapter retains cache roots, safe reads, TOCTOU checks, redaction callbacks,
  and all writes.
- 7112349 closes AIOS adapter output leaks: explain payloads are redacted after
  optional composition, doctor/status redact configured paths, and execution
  failures return safe structured errors.
- 22c0edf redacts both delta and full runtime-next responses only after internal
  recompile/session work. Inline recompiles of a redacted packet now require an
  explicit real source or project path.
- 377bbdd moves runtime context normalization, family deltas, task identity,
  proposal validation, and state shaping into a pure domain reducer. The adapter
  retains root checks, safe harvest, cache reads, sessions, recompile, and
  transport.
- cb9ad0f redacts public compose and standalone/auto explain responses after
  internal session work, closing project/source path leaks.
- 278a470 moves packet composition and source-node enrichment into an in-memory
  service over adapter-supplied safe inputs. Cache reads, redaction, harvest,
  sessions, and transport remain adapter-owned.
- 57d3731 moves full recompile finalization into an in-memory service and fixes
  validated route proposals being overwritten by the runtime identity. Raw-path
  validation, composition, sessions, and final redaction remain adapter-owned.
- 1476d21 makes AIOS execution explicit-only and denies known sensitive values
  before they reach subprocess arguments, including JSON-escaped review evidence.
  Public schema/docs/contract fixture now describe the boundary.
- `679de6e` moves receipt construction/templates/acknowledgement into
  `domain/receipts.py`; `082bb3a` moves artifact manifests/aliases into a pure
  service; `f34862c` validates cached receipt metadata; `390a2ec` moves bounded,
  redacted, TOCTOU-safe cache reads into storage. Adapter roots/writes remain
  authority boundaries; 350 local tests pass with three expected skips.
- `a375cc0` and `8a0707c` extract pure CLI parsing and shared read-only
  harvest-argument projection. `f1e1d4f` adds schema-aware unknown-option
  rejection, bounded scan/read budgets, and fail-closed safe reads; `ed9df02`
  extracts pure doctor/status report assembly; `09857db` makes harvest services
  read-only and keeps artifact output-root selection, persistence, and aliases
  in the adapter; `d1f517e`–`e2f1005` complete evaluator artifact, packet,
  policy, scoring, rendering, advisory, input, failure, mode, plan, server
  renderer, and catalog cutovers. The full suite has 399 tests with three
  expected skips.

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
- Keep guidebook rendering, pattern-catalog merging, and advisory formatting pure;
  fixed catalog file reads remain at the compatibility boundary.
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
  roots, catalog/schema injection, and persistence; storage owns bounded,
  redacted, TOCTOU-safe advisory cache ingestion.
- Optional AIOS execution remains adapter-only. Its child output, configured
  paths, optional composed packet, and execution errors are redacted before any
  MCP or CLI response is returned.
- `adapter=auto` never starts AIOS. Explicit AIOS requests reject known sensitive
  argument values until AIOS offers protected request input; decoded review
  evidence is checked before subprocess execution.
- Runtime state remains raw only inside the adapter until recompile/session work
  completes. Public runtime responses redact paths; callers must supply a real
  path instead of reusing a redacted packet location for an inline recompile.
- Runtime-state reduction is pure and receives only preharvested source nodes and
  cache warnings. The adapter retains cache-policy gating and all filesystem
  authority.
- Packet composition/source enrichment and recompile finalization are pure
  service work over adapter-supplied safe data. cache_policy=none discards
  injected cache inputs defensively; storage cache snapshots, TMCP_HOME redaction,
  raw-path checks, sessions, and final response redaction preserve their boundaries.
- Public compose and explain results redact complete response trees after internal
  session work, while the protected session record retains its existing redaction
  guarantees.

## Accumulated Context

### Roadmap Evolution
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
  adversarial pass closes relative-root and forged-lineage findings, then
  `6864350` separates its release dogfood into focused composition/session helpers;
  `401e125` moves deterministic recompile policy and `2eedd09` moves contextual
  composition policy behind domain boundaries; `8b2cdb5` centralizes packet
  provenance and presentation in that composition domain; `9cb3c8b` centralizes
  final packet assembly there as well; `06defa0` extracts task-family routing
  into a pure domain module; `9b6c47f` adds node ranking; `6cc0769` separates
  final packet construction/presentation to close the required source-size gate;
  `32d6a9f` adds family runtime transition policy, and `6a3acc8` moves its
  declared-read dependency plus selected-node merging into sibling domains;
  `775782e` moves standalone packet compilation into its own deterministic domain;
  `7ed60d4` moves shared review-profile vocabulary and classification out of the
  adapter; `516a497` completes review evidence, results, and rendering extraction;
  `55ddb54` moves workflow catalog and stability policy into its own domain owner;
  `f6f50f3` moves recommendation scoring and candidate construction behind an
  explicit harvested-text boundary; `03009f9` moves adaptive workflow-pack
  construction and recommendation Markdown rendering into a sibling pure domain;
  `5ac3e2a` moves promotion graph policy behind the canonical workflow catalog;
  `52ad06b` moves global activation behind the same canonical catalog boundary.
- 2026-07-12: Final review confirmed the cache default contradicted the target;
  `80835ef` restores the stateless default and adds an explicit-opt-in regression
  test. The next confirmed issue is evaluator reverse-import coupling to the
  transport adapter.
- 2026-07-12: `2299f88` replaces evaluator reverse imports with an explicit
  adapter-injected composition boundary. The remaining architecture work is the
  broader thin-adapter cutover and workflow-stability taxonomy reconciliation.
- 2026-07-12: `47f056c` removes a dead adapter helper and turns the former
  domain-size claim into an executable budget. Docs now separate package,
  template, and transport stability; shortcut candidates are provenance-only.
- 2026-07-12: `0e84678` moves pure global-cache bounds and safe projections into
  storage policy while retaining all cache I/O, redaction, and persistence in
  the adapter; the next cutover must preserve that authority split.
- 2026-07-12: `7112349` closes the AIOS response boundary so child output, path
  diagnostics, compose output, and timeout failures cannot bypass redaction.
- 2026-07-12: `22c0edf` redacts public runtime-next paths after internal state
  work and turns a redacted inline-recompile fallback into a clear explicit-path
  requirement.
- 2026-07-12: `377bbdd` moves runtime-state derivation into a data-only domain
  reducer, leaving source/cache acquisition and all persistent/transport state in
  the compatibility adapter.
- 2026-07-12: `cb9ad0f` closes public compose/explain path leaks by applying final
  response redaction after any internal packet/session work.
- 2026-07-12: `1476d21` makes `adapter=auto` reliably standalone and checks every
  explicit-AIOS argument before launch, decoding review evidence first so escaped
  secret values cannot reach process metadata. A protected AIOS request-input
  protocol remains the prerequisite for confidential explicit requests.
- 2026-07-12: `679de6e` centralizes receipt record/template/result construction,
  keeps receipt identity and persistence adapter-owned, and makes invalid cache
  policy values fail closed before shared artifacts can be read; `082bb3a` moves
  redacted artifact manifests, Markdown rendering, and response aliases into a
  pure service without moving output-root, redaction, or write authority;
  `f34862c` rejects ambiguous cached receipt metadata without changing the public
  receipt schema or cache mtime ordering; `390a2ec` moves all safe global-cache
  traversal, redaction, and projection into a read-only storage ingress.
- 2026-07-13: `a375cc0` extracts pure CLI parsing into `tmcp_runtime/api/cli.py`,
  preserving aliases and argument semantics while leaving output, dispatch, and
  all side-effect authority in the adapter; `8a0707c` centralizes shared
  read-only harvest-argument projection while preserving adapter authority;
  `f1e1d4f` adds schema-aware unknown-option rejection, bounded harvest scan/read
  budgets, and fail-closed safe-reader behavior for platforms without no-follow
  open support; `ed9df02` extracts doctor/status report assembly into a pure
  diagnostics service while keeping environment probes and redaction adapter-owned;
  `09857db` makes harvest services read-only and moves harvest artifact persistence
  back to the adapter boundary; `d1f517e` moves evaluator artifact manifests and
  persistence behind the same adapter-owned write boundary; `68fb7c4` extracts
  packet-inclusion scoring policy into a pure service over that callback;
  `78081c4` extracts decomposition/static-review policy into a pure service;
  `931b9bb` extracts evaluator scoring/report assembly into a pure service;
  `a05a6aa` extracts evaluator rendering/advisory formatting; `4f68872` hardens
  advisory assembly and the fixed catalog boundary; `6945416` bounds evaluator
  inputs and validates nested traces/plans; `d954658` surfaces compose failures;
  `2c36f53` extracts mode orchestration; `e2f1005` extracts plan construction;
  `2cc955f` decouples server renderer imports; `f222f0c` centralizes policy
  catalog ownership.

## Next Command

```bash
# Move the evaluator entrypoint behind runtime service callbacks; keep adapter authority.
```
