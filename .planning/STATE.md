# Planning State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-11)

**Core value:** Deliver a trustworthy, portable packet compiler with safe local
file boundaries and a coherent agent-facing workflow.
**Current focus:** Milestone 2 safe input and storage foundation

## Milestone

**Name:** TMCP Modernization
**Status:** Milestone 2 in progress; POSIX safety slice complete, Windows artifact persistence pending
**Started:** 2026-07-10

## Active Phase

- **Phase:** Safe input and storage foundation
- **Slug:** `tmcp-modernization`
- **Status:** Evaluation migrated; remaining writers and Windows-safe persistence next
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

## Workflow Notes

- Release packages must use the Git-tree archive policy and pass the
  reproducibility check before publication.
- Quality Runner remains advisory-only; the prior QR plan is parked.
- Preserve public MCP/CLI contracts through a versioned compatibility adapter.
- The safe reader and release-package compile surface are split into focused
  modules; the commit gate is clean again.
- Artifact bundles accept only absent or empty destinations; reused artifact
  directories must use the verified per-file store rather than a bundle swap.
- Evaluation never re-reads a persisted plan's skill path while scoring; it
  composes the plan's redacted variant attachment through preharvested nodes.
- Artifact persistence is intentionally fail-closed without descriptor-relative
  no-follow primitives; a race-safe Windows implementation is required before
  cross-platform release claims can remain unconditional.

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
  review, recommendation, promotion, cache, and receipt writers remain.
- 2026-07-11: Adversarial review removed a plan-path probe and surfaced the
  Windows secure-persistence gap; both are explicit M2 release conditions.
- 2026-07-04: QR remediation planning initialized; preserved as parked context.

## Next Command

```bash
# Continue Phase 2: close Windows-safe persistence, then migrate review,
# recommendation, promotion, cache, and receipt writers onto shared boundaries.
```
