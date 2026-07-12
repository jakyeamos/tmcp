# TMCP Modernization Progress

## Current state

**Phase:** Milestone 3 composition/recompile session slice, release-check
cleanup, pure recompile policy, and contextual/presentation/assembly composition
policy complete; composition selection extraction next.

**Branch:** `codex/tmcp-modernization-v2`

**Baseline:** `72baf609a519bebdabc4287b2671f04554ef6c23` (`0.4.0`)

**Implementation status:** Release safety, public compatibility, and the safe
input/storage boundary are implemented in the isolated modernization worktree.
The public runtime surface remains stable while the next slice moves composition
and recompilation behind that boundary. The first vertical journey now supports
explicit project-local session persistence without changing the legacy inline
packet path, and pure recompile transformations are domain-owned.

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
- Keep optional AIOS review explicit and read-only; automatic review stays in
  the standalone protected path.
- Treat durable global cache content as bounded, schema-gated advisory input;
  only canonical workflow identifiers can influence a composed packet.
- Keep packet sessions opt-in, project-local, latest-only, and fail-closed:
  callers provide an absolute project root and opaque run label, no global run
  registry or automatic retention exists, and full recompiles pin their lineage
  to the stored packet.

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
- Milestone 2 has 203 passing local tests with three expected platform skips;
  the clean Git-tree package check and reproducibility check pass. It covers
  portable receipt denial on hosts without secure artifact persistence.
- `31a1d47` completes the first M3 vertical path: compose → protected session
  record → full recompile → revision update. It covers CLI and MCP transport,
  strict path/lineage rules, redaction, symlink denial, cooperative locking, and
  package smoke behavior. The local suite has 218 passing tests with three
  expected platform skips; the clean committed tree at `fcbae5e` also passes
  reproducible package verification, including the packaged session smoke.
- `6864350` moves composition, runtime, receipt, and session release dogfood
  into focused helpers. The main release checker is below the repository source
  size threshold, and its package/install/CI/local-validation surfaces are synchronized.
- `401e125` moves deterministic recompile behavior into
  `tmcp_runtime/domain/recompile.py`: previous-packet compatibility parsing,
  reason/detail selection, delta merge, diffing, proposal application, and
  Markdown diff rendering. The adapter retains source-aware composition,
  enrichment, session persistence, and transport responsibilities; the local
  suite has 224 passing tests with three expected platform skips.
- `2eedd09` moves UI/contextual gates, source verification-gate filtering, and
  reference-read selection into `tmcp_runtime/domain/composition.py`. The local
  suite has 229 passing tests with three expected platform skips.
- `8b2cdb5` moves provenance, shortcut eligibility, selection rationale, and
  composed Markdown rendering into `tmcp_runtime/domain/composition.py`; full
  recompile injects that renderer. The local suite has 234 passing tests with
  three expected platform skips.
- `9cb3c8b` moves final composed-packet assembly into the same domain: caps,
  deferred/ignored items, packet identity, receipt template, safety metadata,
  and rendering. The local suite has 235 passing tests with three expected
  platform skips.

## Blockers and risks

- The primary checkout contains user-owned uncommitted work that is not included
  in this audit branch. Integrate or supersede it deliberately during approved
  implementation.
- Hosted matrix evidence is pending because this branch has no pull request or
  tag-triggered run; local package and contract checks are current.

## Next step

Extract composition node scoring and family selection into `tmcp_runtime`, keep
source and session I/O at the adapter boundary, then repeat package and
adversarial validation.
