# Planning State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-11)

**Core value:** Deliver a trustworthy, portable packet compiler with safe local
file boundaries and a coherent agent-facing workflow.
**Current focus:** Milestone 3 review policy is domain-owned; map the next
deterministic adapter boundary, beginning with workflow recommendation.

## Milestone

**Name:** TMCP Modernization
**Status:** Milestone 3 session slice, release-check cleanup, pure recompile,
contextual/selection composition policy, task-family routing/runtime transitions,
declared-read selection, standalone packet compilation, final packet-policy
split, and complete review policy extraction; map workflow recommendation.
**Started:** 2026-07-10

## Active Phase

- **Phase:** Compose and recompile vertical slice
- **Slug:** `tmcp-modernization`
- **Status:** Project-local session journey, focused release checks, pure
  recompile/contextual/selection policy, task-family routing/runtime transitions,
  declared-read selection, standalone packet compilation, final packet
  construction/presentation, and complete review-policy split complete; map
  workflow recommendation.
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
  suite now has 165 passing tests.
- `42b922f` adds redacted, bounded exact-file inputs for evaluation and a single
  text/JSON artifact store with descriptor-relative writes, directory identity
  checks, and fail-closed behavior when those primitives are unavailable. The
  full suite now has 171 passing tests.
- `587b8c1` moves skill evaluation onto those boundaries: data-only variant
  composition, bounded/redacted plan and evidence inputs, safe artifact writes,
  and one-read score persistence. The full suite now has 177 passing tests.
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
  the full local suite now has 184 passing tests (the unsupported-platform
  denial test is skipped locally because this host supports secure persistence).
- `3f4b74b` closes the adversarial boundary findings: review auto mode stays
  standalone; explicit AIOS review is preview-only; default writes reject
  symlink-derived roots; cache reads are bounded, schema-gated, and canonical;
  Windows junctions are link-like; artifact identities retain opaque collision
  resistance; and Windows runs the portable package smoke instead of skipping it.
- `c31a9ee` moves MCP adapter/status safety coverage into its own test module,
  restoring the repository test-source size gate; the full local suite has 203
  passing tests with three expected platform skips.
- Clean package reproducibility passes at `1b3697f`; the extracted package
  verifies portable receipt denial as well as persistence-capable receipt flow.
- `2d04122` moves deterministic route inference into `tmcp_runtime/domain`,
  removing the first packet-domain owner from the legacy adapter.
- `31a1d47` adds explicit, redacted project-local packet sessions with absolute
  project roots, opaque keys, revision-locked latest records, pinned recompile
  lineage, portable denial, and CLI/MCP/package coverage. The local suite has
  218 passing tests with three expected platform skips.
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

## Workflow Notes

- Release packages must use the Git-tree archive policy and pass the
  reproducibility check before publication.
- Quality Runner remains advisory-only; the prior QR plan is parked.
- Preserve public MCP/CLI contracts through a versioned compatibility adapter.
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
- Composition provenance, shortcut eligibility, and rendering are domain-owned;
  recompile injects the domain renderer so both packet forms share one layout.

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
  adapter; `516a497` completes review evidence, results, and rendering extraction.
- 2026-07-04: QR remediation planning initialized; preserved as parked context.

## Next Command

```bash
# Map workflow-recommendation policy still owned by the MCP adapter.
```
