# TMCP Modernization Progress

## Current state

**Phase:** Milestone 1 complete; Milestone 2 ready.

**Branch:** `codex/tmcp-modernization-v2`

**Baseline:** `72baf609a519bebdabc4287b2671f04554ef6c23` (`0.4.0`)

**Implementation status:** Release safety and the compatibility boundary are
implemented in the isolated modernization worktree. The public runtime surface
is now owned by a canonical registry while legacy entrypoints remain unchanged.

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
- Own public version metadata, MCP initialize data, tool schemas, CLI aliases,
  defaults, and help aliases in `tmcp_runtime/api/registry.py`.

## Verified baseline

- Milestone 1: 151 unit tests, compile, launcher syntax, install, release
  evidence, and the live contract check pass with an isolated `TMCP_HOME`.
- A frozen fixture covers all 11 MCP tools, 47 CLI aliases, defaults, help/list
  pseudo-commands, schemas, output labels, and declared state effects.
- Contract-fixture digests use explicit `sha256:` labels so release scanning
  distinguishes deterministic checksums from secret-like values.
- The redaction classifier recognizes code identifier assignments without
  weakening opaque-token detection, so the extracted registry can ship.
- Secret-like regression fixtures are assembled from short literals so package
  scanning stays strict against the committed source tree.

## Blockers and risks

- The primary checkout contains user-owned uncommitted work that is not included
  in this audit branch. Integrate or supersede it deliberately during approved
  implementation.
- The remaining milestones change storage defaults and compatibility semantics;
  retain the documented compatibility boundary while migrating the runtime.

## Next step

Begin Milestone 2 by extracting bounded safe-reader, redaction, and storage
services behind the frozen compatibility adapter.
