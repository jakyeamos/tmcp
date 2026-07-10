# TMCP Modernization Progress

## Current state

**Phase:** Audit and target design complete.

**Branch:** `codex/tmcp-modernization-audit`

**Baseline:** `72baf609a519bebdabc4287b2671f04554ef6c23` (`0.4.0`)

**Implementation status:** Not started. This branch contains planning artifacts
only; no product code, dependency, release, cache, or primary-checkout changes
have been made.

## Decisions recorded

- Use a parallel v2 core behind stable Node/Python entrypoints.
- Treat the release package disclosure defect as a P0 gate before any future
  publication.
- Treat TMCP's MCP/CLI/Markdown interaction as the UX surface, not a web UI.
- Require explicit, visible state effects in the target flow.

## Verified baseline

- Python compile and Node launcher syntax pass.
- The isolated test suite passes: 120 tests.
- Install shape, release evidence, release package, and standalone smoke checks
  pass with an isolated `TMCP_HOME`.

## Blockers and risks

- **P0:** release package currently can include untracked/ignored sensitive
  files. Do not release before Milestone 0 is complete.
- The primary checkout contains user-owned uncommitted work that is not included
  in this audit branch. Integrate or supersede it deliberately during approved
  implementation.
- The modernization changes storage defaults and compatibility semantics; the
  five recommendations in `TARGET.md` need confirmation before implementation.

## Next step

Review and approve `TARGET.md` and `EXEC_PLAN.md`, then begin Milestone 0 in
an isolated implementation worktree.
