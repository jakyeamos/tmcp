# TMCP Modernization Progress

## Current state

**Phase:** Milestone 3 composition/recompile session slice, release-check
cleanup, pure recompile policy, contextual/selection composition policy,
task-family routing/runtime transitions, declared-read selection, and final
packet construction/presentation and standalone compiler splits complete; map
the next adapter boundary.

**Branch:** `codex/tmcp-modernization-v2`

**Baseline:** `72baf609a519bebdabc4287b2671f04554ef6c23` (`0.4.0`)

**Implementation status:** Release safety, public compatibility, and the safe
input/storage boundary are implemented in the isolated modernization worktree.
The public runtime surface remains stable while the next slice moves composition
and recompilation behind that boundary. The first vertical journey now supports
explicit project-local session persistence without changing the legacy inline
packet path; pure recompile transformations, task-family routing/runtime
transitions, declared-read selection, node ranking, and final packet
construction/presentation are domain-owned. The legacy standalone compiler is
also domain-owned while public MCP/CLI behavior remains stable.

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
- `06defa0` moves scoped-seed/router family selection into
  `tmcp_runtime/domain/families.py`, including family context, sibling deferral,
  and declared-load normalization. The adapter retains source-signal text and
  runtime state; direct edge cases and existing integration paths pass with 242
  local tests and three expected platform skips.
- `9b6c47f` moves composition node scoring and selection into
  `tmcp_runtime/domain/composition.py`; the adapter now only injects source text
  and enriches selected nodes. Direct policy tests plus the full suite pass with
  247 local tests and three expected platform skips. The commit gate reports
  that `composition.py` exceeds the 600-line production source limit, so its
  responsibilities must be split before new feature work.
- `6cc0769` closes that gate by moving final composed-packet assembly,
  provenance, shortcut eligibility, and Markdown rendering into
  `tmcp_runtime/domain/packets.py`. The server keeps callback-based recompile
  rendering; composition and packets are both below the source limit.
- `32d6a9f` moves family phase aliases, transition-only seed fallback, phase
  selection, skill activation/deactivation, and transition deltas into
  `tmcp_runtime/domain/families.py`. It initially injects declared-read
  selection, avoiding a domain-to-adapter dependency; 251 local tests pass with
  three expected platform skips.
- `6a3acc8` completes that dependency split: declared-read parsing, matching,
  objective narrowing, and selected-node enrichment now live in
  `tmcp_runtime/domain/declared_loads.py`; `families.py` imports that sibling
  directly, while `composition.py` owns generic selection merging. The full
  local suite has 254 passing tests with three expected platform skips.
- `775782e` moves the legacy standalone task/playbook catalog, source projection,
  substance evaluation, packet assembly, and Markdown rendering into
  `tmcp_runtime/domain/standalone_packets.py`. Harvest classification consumes
  its shared atom catalog; 258 local tests pass with three expected platform
  skips.

## Blockers and risks

- The primary checkout contains user-owned uncommitted work that is not included
  in this audit branch. Integrate or supersede it deliberately during approved
  implementation.
- Hosted matrix evidence is pending because this branch has no pull request or
  tag-triggered run; local package and contract checks are current.

## Next step

Map the next deterministic policy boundary remaining in the MCP adapter, retain
stable imports/behavior, then repeat package and adversarial validation.
