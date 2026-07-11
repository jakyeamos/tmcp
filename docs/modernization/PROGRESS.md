# TMCP Modernization Progress

## Current state

**Phase:** Milestone 0 complete; Milestone 1 ready.

**Branch:** `codex/tmcp-modernization-v2`

**Baseline:** `72baf609a519bebdabc4287b2671f04554ef6c23` (`0.4.0`)

**Implementation status:** Release safety is implemented and verified in the
isolated modernization worktree. Public runtime contracts remain unchanged.

## Decisions recorded

- Use a parallel v2 core behind stable Node/Python entrypoints.
- Treat the release package disclosure defect as a P0 gate before any future
  publication.
- Treat TMCP's MCP/CLI/Markdown interaction as the UX surface, not a web UI.
- Require explicit, visible state effects in the target flow.
- Package from a clean Git tree, not from filesystem traversal; archive policy
  owns containment, manifest validation, and deterministic output.
- Release evidence is a pre-merge two-run gate for version bumps: record a
  successful release-PR run, then pass the evidence check before merge.

## Verified baseline

- Full unit, compile, launcher, install, release-evidence, and package checks
  pass with an isolated `TMCP_HOME`.
- The real committed tree packages twice with matching archive and manifest
  digests; the extracted package passes its verification suite.

## Blockers and risks

- The primary checkout contains user-owned uncommitted work that is not included
  in this audit branch. Integrate or supersede it deliberately during approved
  implementation.
- The remaining milestones change storage defaults and compatibility semantics;
  retain the documented compatibility boundary while migrating the runtime.

## Next step

Begin Milestone 1 by freezing MCP/CLI compatibility contracts and extracting a
canonical tool/version registry.
