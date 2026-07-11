# Planning State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-11)

**Core value:** Deliver a trustworthy, portable packet compiler with safe local
file boundaries and a coherent agent-facing workflow.
**Current focus:** Milestone 1 contract freeze

## Milestone

**Name:** TMCP Modernization
**Status:** Milestone 0 complete; implementation continues
**Started:** 2026-07-10

## Active Phase

- **Phase:** Contract freeze and target baseline
- **Slug:** `tmcp-modernization`
- **Status:** Ready to begin after release-safety verification
- **Plan:** `docs/modernization/EXEC_PLAN.md`

## Completed Scope

- Modernization baseline, parallel audit, target architecture, and executable
  milestone plan recorded under `docs/modernization/`.
- Isolated audit branch created from the 0.4.0 release baseline.
- Milestone 0 release safety completed on `codex/tmcp-modernization-v2`:
  Git-tree allowlist packaging, archive manifest verification, reproducibility,
  hermetic fixtures, and pre-merge release-evidence enforcement.

## Workflow Notes

- Release packages must use the Git-tree archive policy and pass the
  reproducibility check before publication.
- Quality Runner remains advisory-only; the prior QR plan is parked.
- Preserve public MCP/CLI contracts through a versioned compatibility adapter.

## Accumulated Context

### Roadmap Evolution
- 2026-07-10: Modernization audit identifies P0 package disclosure risk and
  proposes a parallel v2 runtime behind stable entrypoints.
- 2026-07-11: Milestone 0 closes the package-disclosure blocker; next work
  freezes public contracts before core migration.
- 2026-07-04: QR remediation planning initialized; preserved as parked context.

## Next Command

```bash
# Begin Phase 1: freeze public MCP/CLI contracts and canonical metadata.
```
