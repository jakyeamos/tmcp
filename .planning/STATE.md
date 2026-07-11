# Planning State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-11)

**Core value:** Deliver a trustworthy, portable packet compiler with safe local
file boundaries and a coherent agent-facing workflow.
**Current focus:** Milestone 2 safe input and storage foundation

## Milestone

**Name:** TMCP Modernization
**Status:** Milestone 2 in progress; safe harvest/storage slice complete
**Started:** 2026-07-10

## Active Phase

- **Phase:** Safe input and storage foundation
- **Slug:** `tmcp-modernization`
- **Status:** Harvest safety complete; evaluation and remaining artifact paths next
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

## Workflow Notes

- Release packages must use the Git-tree archive policy and pass the
  reproducibility check before publication.
- Quality Runner remains advisory-only; the prior QR plan is parked.
- Preserve public MCP/CLI contracts through a versioned compatibility adapter.
- The safe reader and release-package compile surface are split into focused
  modules; the commit gate is clean again.

## Accumulated Context

### Roadmap Evolution
- 2026-07-10: Modernization audit identifies P0 package disclosure risk and
  proposes a parallel v2 runtime behind stable entrypoints.
- 2026-07-11: Milestone 0 closes the package-disclosure blocker; next work
  freezes public contracts before core migration.
- 2026-07-11: Milestone 1 freezes all public contracts and removes the stale
  `0.3.0` MCP initialize response; safe IO/storage extraction is next.
- 2026-07-11: M2 begins with contained harvest reads, decoded-JSON/path
  redaction, and atomic artifact bundles; evaluation and remaining writers are
  pending migration.
- 2026-07-04: QR remediation planning initialized; preserved as parked context.

## Next Command

```bash
# Continue Phase 2: migrate evaluation and remaining artifact writers onto the
# shared safety and storage boundaries.
```
