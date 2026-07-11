# TMCP Modernization Progress

## Current state

**Phase:** Milestone 2 in progress; safe harvest/storage slice complete.

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
- Own harvest root policy, traversal, bounded reads, redaction, and safe
  provenance display in `tmcp_runtime/safety`; own harvest bundle persistence
  in `tmcp_runtime/storage`.

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
- The committed tree passes reproducible archive creation and extracted-package
  verification (153 tests, with one source-metadata check intentionally skipped
  in the excluded-registry package context).
- CLI/launcher contract tests now have a dedicated module; the retained server
  test module is below the repository source-size warning threshold.
- `3abe21c` moves harvest onto root-contained, symlink-aware reads; it redacts
  text, decoded JSON, and path metadata before derivation or serialization.
  Harvest artifacts now use a staged atomic bundle with restrictive file modes
  and descriptor-relative writes.
- Adversarial coverage now includes external/ancestor/cyclic links, in-root
  opt-in links, resolved exclusion bypasses, path metadata redaction,
  intermediate-directory swaps, output-directory swaps, and failed bundle
  commits. The full suite has 166 passing tests.
- `8c7f498` splits the safe reader and extracted-package compile list into
  focused modules; the repository commit gate is clean with no size exception.

## Blockers and risks

- The primary checkout contains user-owned uncommitted work that is not included
  in this audit branch. Integrate or supersede it deliberately during approved
  implementation.
- Evaluation, promotion, recommendation, review, cache, and receipt paths still
  need migration onto the new safety/storage services.

## Next step

Move evaluation and the remaining artifact writers onto the shared safety and
storage services.
