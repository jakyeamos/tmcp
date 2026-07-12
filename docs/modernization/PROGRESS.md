# TMCP Modernization Progress

## Current state

**Phase:** Milestone 3 composition/recompile session slice, release-check
cleanup, pure recompile policy, contextual/selection composition policy,
task-family routing/runtime transitions, declared-read selection, and final
packet construction/presentation, standalone compiler, review-profile catalog,
review-policy, workflow catalog/scoring, adaptive workflow-pack, promotion-graph,
global workflow-activation, stateless cache-default, evaluator composition-service,
stability-taxonomy, domain-size-budget, and harvest/source-graph splits complete;
verify the post-harvest adapter boundary before selecting the next cutover.

**Branch:** `codex/tmcp-modernization-v2`

**Baseline:** `72baf609a519bebdabc4287b2671f04554ef6c23` (`0.4.0`)

**Implementation status:** Release safety, public compatibility, and the safe
input/storage boundary are implemented in the isolated modernization worktree.
The public runtime surface retains its aliases and output shapes while its
documented cache behavior is intentionally safer: composition and runtime routing
default to `cache_policy=none`, with global graphs and receipts available only by
explicit opt-in. The first vertical journey now supports
explicit project-local session persistence without changing the legacy inline
packet path; pure recompile transformations, task-family routing/runtime
transitions, declared-read selection, node ranking, and final packet
construction/presentation are domain-owned. The legacy standalone compiler is
also domain-owned. Review profiles now have a shared domain owner for standalone
review and workflow recommendation. Evidence, audit, remediation, validation,
and Markdown review policy are also domain-owned while public MCP/CLI behavior
remains stable. Curated workflow definitions and stability labels now have one
domain owner shared by recommendation, promotion, and cache selection. Workflow
recommendation scoring receives harvested-node text and guidance labels explicitly
from the adapter, preserving dependency direction. Adaptive workflow-pack
construction, scoped seed projection, custom-idea derivation, overlap/process-gap
policy, and recommendation Markdown rendering now share one pure domain owner;
the adapter still owns redaction and artifact persistence. Promotion target
selection, scoped-seed precedence, graph construction, canonical catalog edges,
and promotion Markdown rendering also share one pure domain owner; the adapter
still owns persistence and global-cache activation. Global activation now owns
objective scoring, canonical workflow rehydration, activation projection, and
specialized instructions while the adapter retains cache validation and packet
orchestration. Evaluation scoring now receives a data-only composition callback
from the MCP adapter; it no longer imports or introspects private server helpers.
Stability documentation now separates stable skill packages, stable curated
templates, and stable MCP tool contracts, rather than conflating their labels.
Harvest labels and source-node policy are now pure domain modules, while the
runtime service owns safe traversal, redaction, scoped-seed projection, packet
seeding, and artifact writes. The adapter injects only the evaluator-specific
advisory callback and retains compatibility facades used by existing callers.

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
- Default composition and runtime routing to no global cache. Any publication of
  this material behavior change must use the planned `0.5.0` compatibility
  release process rather than relabeling the already-published `0.4.0` release.
- Treat skill-package, curated-template, and MCP-tool stability as distinct
  contracts with distinct owners: frontmatter/package validation, the workflow
  catalog, and the public tool registry.
- Treat evaluator advisories as an explicit adapter-injected dependency of
  harvest-node construction; pure runtime modules must not import the MCP adapter.

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
- `7ed60d4` moves review dimensions, coverage requirements, selection precedence,
  and fallback behavior into `tmcp_runtime/domain/review_profiles.py`. Standalone
  review and workflow recommendation consume that one catalog; 260 local tests
  pass with three expected platform skips.
- `516a497` completes the review-policy split: `review_evidence.py` owns evidence
  contracts, rubric synthesis, and audit scoring, while `review_results.py` owns
  remediation, handoff, validation, and Markdown rendering. The adapter retains
  side effects and transport; 262 local tests pass with three expected platform
  skips.
- `55ddb54` moves the curated workflow catalog, candidate filtering, stability
  labels, and ID lookup into `tmcp_runtime/domain/workflow_catalog.py`. Promotion
  and global-cache activation share this owner; 265 local tests pass with three
  expected platform skips.
- `f6f50f3` moves workflow scoring, reasons, rubric/template and candidate-instance
  construction, required-evidence guidance, and source-scope policy into
  `tmcp_runtime/domain/workflow_recommendations.py`. The adapter injects source
  text and label mapping; 267 local tests pass with three expected platform skips.
- `03009f9` moves scoped-seed projection, custom workflow ideas, adaptive-pack
  construction, duplicate-label analysis, process-gap policy, and recommendation
  Markdown rendering into `tmcp_runtime/domain/workflow_adaptive.py`. Exact
  old/new parity, focused domain coverage, and the full local suite pass with
  270 tests and three expected platform skips.
- `5ac3e2a` moves promotion target selection, scoped-seed precedence, graph
  construction, canonical catalog edges, and promotion Markdown rendering into
  `tmcp_runtime/domain/workflow_promotion.py`. Exact old/new parity, focused
  domain coverage, and the full local suite pass with 273 tests and three
  expected platform skips.
- `52ad06b` moves global workflow objective scoring, canonical catalog
  rehydration, activation projection, and specialized workflow instructions into
  `tmcp_runtime/domain/workflow_activation.py`. Exact old/new parity, focused
  domain coverage, and the full local suite pass with 276 tests and three
  expected platform skips.
- `80835ef` restores the target's stateless cache default across MCP schemas,
  runtime fallbacks, recommendation/explain compose paths, docs, and frozen
  contract metadata. A cache-hardening regression proves global graph activation
  happens only after explicit `cache_policy=global`; the full local suite has
  277 passing tests with three expected platform skips.
- `2299f88` replaces evaluator reverse imports and private-function
  introspection with an explicit adapter-injected composition callback. MCP
  score-mode, no-filesystem-read, and static dependency tests cover the new
  boundary; the full local suite has 279 passing tests with three expected
  platform skips.
- `47f056c` removes a stale adapter helper and adds a 600-nonblank-line test
  budget for every domain module. Documentation now labels stability by scope
  and records shortcut candidates as provenance-only metadata; the full local
  suite has 280 passing tests with three expected platform skips.
- 28b06ff extracts harvest labels and source-node construction into
  harvest_labels.py and harvest_nodes.py, with safe harvest orchestration in
  services/harvest.py. Compatibility wrappers preserve existing server callers,
  and the evaluator hook is injected through a keyword-aware adapter. The full
  local suite has 283 passing tests with three expected platform skips.

## Blockers and risks

- The primary checkout contains user-owned uncommitted work that is not included
  in this audit branch. Integrate or supersede it deliberately during approved
  implementation.
- Hosted matrix evidence is pending because this branch has no pull request or
  tag-triggered run; local package and contract checks are current.
- The branch intentionally retains `0.4.0` release metadata while unpublished;
  before release, use the target's planned `0.5.0` compatibility/version process
  because the stateless default is a material behavior change.
- The legacy server and evaluator scripts remain broader than the target's thin
  transport adapter. Review, recommendation, promotion, cache, and dispatch
  orchestration require a fresh post-harvest architecture review before the next
  extraction.

## Next step

Run an adversarial architecture review against the post-harvest boundary, then
select the next bounded thin-adapter extraction.
