# TMCP Modernization Progress

## Current state

**Phase:** Milestone 3 adapter thinning and security hardening. Domain,
service, storage, safety, evaluator, and transport cutovers are complete; the
server retains only the compatibility seams that still own source, cache,
storage, and output authority. Typed dispatch/public selection are
registry-owned; the private CLI parser, AIOS subprocess, harvest-constant, and
unused schema seams were deleted and their tests now target runtime owners.
Remaining work is advanced-capability migration completion and Horizon 4 release
hardening. The workflow now invokes the same complete runtime compile inventory
used by extracted-package checks, and install verification requires every
shipped runtime module.

**Branch:** `codex/tmcp-modernization-v2`

**Baseline:** `72baf609a519bebdabc4287b2671f04554ef6c23` (`0.4.0`)

**Implementation status:** Release safety, public compatibility, safe
input/storage, domain policy, evaluator, harvest/recommendation/review/promotion,
and transport cutovers are implemented. Public aliases and output shapes remain
stable; composition/runtime default to `cache_policy=none`, with global graphs
and receipts explicit-only. Runtime owns pure domain reducers and services for
composition, recompile finalization, evaluation, review, recommendations,
promotion, redaction, diagnostics, and optional AIOS execution. Adapters retain
source/cache/artifact acquisition, persistence, final redaction, and
compatibility wiring; runtime session services coordinate project-local
lifecycles through injected storage protocols. Typed registry dispatch lives in
`tmcp_runtime.adapters`; runtime-state/recompile orchestration lives in
`tmcp_runtime.services.runtime` with source, cache-warning, and composition
callbacks supplied by the compatibility adapter. Generic artifact-bundle
persistence now lives in `tmcp_runtime.services.artifact_persistence`; the
adapter supplies redaction, path presentation, and verified storage callbacks
while retaining output-root selection and capability checks. Receipt recording
now lives in `tmcp_runtime.services.receipts` with adapter callbacks for the
clock, opaque identity, path creation, redaction, and verified write.
Global-promotion manifest assembly now lives in
`tmcp_runtime.services.global_promotion`; the adapter retains global roots,
persistence gating, opaque identity, and cache authority.
Standalone explain packet assembly and review-evidence parsing now live in
runtime services; the server retains transport, AIOS selection, safe roots,
persistence callbacks, and compatibility seams.
The storage reader now projects legacy promoted summaries into the current graph
contract in memory, with current graph files preferred and no source mutation.

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
- Keep CLI token parsing in `tmcp_runtime/api/cli.py` as a pure API boundary;
  reject options outside the selected tool schema, and keep the adapter from
  regaining argument-decoding or schema-coercion ownership.
- Own harvest root policy, bounded traversal/read budgets, redaction, and safe
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
- Treat harvest advisory classification and fixed catalog lookup as a runtime
  service over safe source text; the adapter retains source acquisition/redaction.
- Treat redaction primitives as runtime safety ownership. Keep the historical
  script module as a facade so package and caller aliases remain stable.
- Treat the evaluator runtime API and harvest-advisory service as safe runtime
  entrypoints. Keep legacy script aliases while adapters supply only safe source
  text and metadata.
- Treat workflow recommendation as a read-only service. Compose preview remains
  adapter-injected, and result redaction plus all durable-write behavior remains
  adapter-owned.
- Treat promotion planning and artifact manifest/alias assembly as service work.
  Preserve adapter-owned global-cache, output-root, redaction, and persistence
  authority.
- Treat standalone review planning as a pure in-memory service. Source acquisition,
  evidence parsing, redaction, artifacts, and AIOS remain adapter-owned.
- Treat global-cache policy as pure storage policy and cache ingestion as a
  bounded, redacted, TOCTOU-safe storage reader. Inject roots, schemas, and the
  canonical catalog from the adapter; keep cache-root selection and persistence
  adapter-owned. Cached receipts need nonblank IDs and unambiguous timestamps.
- Treat optional AIOS subprocess output as untrusted adapter data: redact the
  complete response only after optional composition, redact status/doctor paths,
  and map launch/timeout failures to structured errors.
- Treat AIOS invocation as an explicit data-forwarding decision: `auto` is always
  standalone, and explicit subprocess arguments—including decoded review
  evidence—must fail closed on known sensitive values until protected input exists.
- Redact `tmcp_runtime_next` only after internal compose/recompile/session work.
  A redacted packet cannot be an implicit filesystem locator for later inline
  recompiles; callers must supply an explicit real source or project path.
- Treat runtime-state construction as a pure reducer over already-safe source
  nodes and cache warnings. Keep all root checks, harvest/cache I/O, sessions,
  recompile, and transport in the adapter.
- Redact public compose and standalone/auto explain responses at their final
  adapter return boundary, after any internal session creation or packet work.
- Treat packet composition and source-node enrichment as an in-memory service
  over adapter-supplied safe data. Cache reads, TMCP_HOME redaction, harvest,
  session persistence, and transport remain adapter authority; stateless policy
  rejects injected cache graphs, receipts, and warnings.
- Treat full recompile finalization as an in-memory service over a prior packet,
  runtime state, and a fresh adapter-composed packet. Keep path fallback checks,
  composition, session persistence, and final redaction in the adapter; apply
  the runtime identity before validated proposals so accepted route changes are
  not discarded.
- Treat run-receipt construction, receipt templates, and public receipt
  acknowledgements as pure domain data. Preserve raw-to-redacted identity,
  timestamps, nonce/path creation, persistence, cache projection, and final
  redaction in the adapter.
- Treat only literal `cache_policy=global` as shared-cache consent. All other
  values normalize to `none` before adapter reads, runtime warnings, or service
  composition can consume cache data.

## Verified baseline

- Milestones 0–2 established reproducible release packaging, frozen MCP/CLI
  contracts, safe file/storage boundaries, and portable fail-closed writes. The
  detailed historical evidence remains in the execution plan and Git history.
- `3abe21c` moves harvest onto root-contained, symlink-aware reads; it redacts
  text, decoded JSON, and path metadata before derivation or serialization.
  Harvest artifacts now use a staged atomic bundle with restrictive file modes
  and descriptor-relative writes.
- Adversarial coverage now includes external/ancestor/cyclic links, in-root
  opt-in links, resolved exclusion bypasses, path metadata redaction,
  intermediate-directory swaps, output-directory swaps, and failed bundle
  commits. The full suite has 166 passing tests.
- `31a1d47` completes the first M3 vertical path: compose → protected session
  record → full recompile → revision update. It covers CLI and MCP transport,
  strict path/lineage rules, redaction, symlink denial, cooperative locking, and
  package smoke behavior. The local suite has 218 passing tests with three
  expected platform skips; the clean committed tree at `fcbae5e` also passes
  reproducible package verification, including the packaged session smoke.
- `6864350` moves composition, runtime, receipt, and session release dogfood
  into focused helpers while keeping the release checker as an orchestrator.
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
- d9422dc extracts catalog scoring, profile construction, adaptive-pack
  construction, result assembly, and optional compose-preview invocation into
  services/recommendations.py. The full local suite has 286 passing tests with
  three expected platform skips.
- b167af6 extracts promotion target selection, graph construction, and
  status/result assembly into services/promotion.py. Existing adapter paths
  retain local/global artifact writes and global-cache safeguards; the full local
  suite has 290 passing tests with three expected platform skips.
- e164875 extracts standalone review packet/rubric/audit/remediation/handoff
  assembly into services/review.py. The full local suite has 294 passing tests
  with three expected platform skips.
- 0e84678 extracts bounded cache limits, JSON structure validation, normalized
  global-graph construction, and canonical graph/receipt projections into
  storage/cache_policy.py. The full local suite has 300 passing tests with three
  expected platform skips; install, contract, compile, and independent boundary
  reviews pass.
- 7112349 closes the optional AIOS adapter response boundary. Child success and
  failure payloads, compose output, status/doctor paths, missing-AIOS diagnostics,
  and timeout errors are redacted or structured safely.
- 22c0edf redacts delta and full `tmcp_runtime_next` responses after internal
  state work, and rejects redacted previous-packet paths without an explicit
  source/project replacement.
- 377bbdd extracts runtime state into domain/runtime_state.py. The reducer owns
  context/family deltas, identity, proposal validation, and state shaping over
  injected safe data.
- cb9ad0f closes public compose/explain project/source-path leaks with final
  adapter response redaction. Session persistence remains redacted internally.
- 278a470 extracts packet composition and source-node enrichment into
  tmcp_runtime/services/compose.py; cache and session authority remains in the
  compatibility adapter.
- `679de6e` moves receipt construction/templates/acknowledgement into
  `domain/receipts.py`; `082bb3a` moves artifact manifests/aliases into a pure
  service; `f34862c` validates cached receipt metadata; `390a2ec` moves cache
  ingestion into read-only storage. Adapter root/write authority is unchanged;
  boundary reviews pass.
- `a375cc0` and `8a0707c` extract pure CLI parsing and shared read-only harvest
  argument projection. `f1e1d4f` adds schema-aware option rejection, bounded
  scan/read budgets, and fail-closed safe reads; `ed9df02` extracts pure
  doctor/status report assembly; `09857db` makes harvest services read-only and
  keeps artifact output-root selection, persistence, and path aliases in the
  adapter; `d1f517e` moves evaluator artifact manifests and writes behind the
  same adapter boundary; `68fb7c4` extracts packet-inclusion lookup,
  compose-callback invocation, and composed-packet diffing into a pure service.
  `78081c4` extracts evaluator decomposition, static review, variants, and
  observables; `931b9bb` extracts trace scoring/report assembly; `a05a6aa`
  extracts rendering/catalog/advisory formatting; `4f68872` hardens advisory
  assembly and catalog/title handling; `6945416` bounds evaluator inputs/traces
  and nested shapes; `d954658` surfaces compose failures; `2c36f53` extracts
  mode orchestration; `e2f1005` extracts plan construction behind safe DTOs;
  `2cc955f` decouples server renderer imports; `f222f0c` centralizes policy
  catalog ownership; `371992d` moves the evaluator entrypoint into
  `tmcp_runtime/api/evaluation.py`, leaving a compatibility facade; `8085efa`
  moves harvest advisory classification and catalog lookup into a runtime
  service; `f1d5811` moves redaction primitives into `tmcp_runtime/safety` and
  leaves the script module as a compatibility facade. Full suite: 401 tests,
  three expected skips; `d67dcc9` isolates the safety import boundary test and
  restores the test-size gate; `7420a2b` moves transport into runtime adapters;
  `cb34594` adds typed request/result dispatch and registry-owned tool selection.
  `78c35a0` moves optional AIOS execution into a redaction-aware runtime adapter;
  `489746d` moves runtime-state/recompile orchestration behind a callback context;
  `a69b4ca` moves project-local session lifecycle orchestration behind an injected
  storage protocol; `50f5758` moves generic artifact-bundle persistence behind
  an explicit runtime service with adapter-owned redaction and verified-storage
  callbacks; `007d7ea` moves receipt recording behind the same explicit runtime
  service while preserving adapter-owned identity and path seams. Full suite:
  423 tests, three expected skips; `ac70786` moves global-promotion manifest
  assembly behind an explicit runtime service while preserving global-root and
  persistence authority. Full suite: 426 tests, three expected skips;
  `1850faa` moves standalone explain assembly and review-evidence parsing into
  runtime services, reducing direct domain ownership in the server. Full suite:
  429 tests, three expected skips; `a40476a` adds a read-only legacy promotion
  summary migration reader with duplicate suppression. Full suite: 434 tests,
  three expected skips; `52f35ca` deletes private server compatibility seams and
  updates tests to target runtime owners directly. Focused suite: 66 tests, three
  expected skips; Ruff is clean for the changed surface. `cae0563` centralizes
  the release compile inventory across workflow and package checks and expands
  install verification to all runtime modules; compile/install/contract checks
  pass locally. `329e065` removes stale evaluator compatibility imports,
  replaces a lambda with an explicit callback, and restores a clean full Ruff
  gate.

The legacy-artifact audit found only the supported promotion-summary migration
boundary. Current promotion graphs win over legacy summaries in the same
directory; receipts and project-local sessions have no alternate shipped schema
and remain strict readers.

The 0.5.0 compatibility note now records the preserved public surface,
deliberate state-effect changes, migration/rollback behavior, and the
evidence-bearing release-PR sequence. The active candidate surfaces and
evidence are now 0.5.0; hosted run `29285497867` passed the post-cutover matrix.

Draft PR #2 run `29283834718` passed all Linux/macOS jobs but exposed Windows
read-only exact-file failures caused by the missing `O_NOFOLLOW` primitive.
`b99c58a` adds a validated Windows path-read fallback without weakening the
durable-write boundary. Hosted run `29284101047` then reduced the Windows
failures to ten path/newline contract cases; `1a59e2f` normalizes stable
workflow error paths and harvested text newlines, and makes injected test
path presentation portable. Hosted run `29284457105` now passes all six
matrix jobs, including Windows 3.10/3.13 package and evidence checks.

## Blockers and risks

- The primary checkout contains user-owned uncommitted work that is not included
  in this audit branch. Integrate or supersede it deliberately during approved
  implementation.
- The post-cutover hosted matrix is green in PR run `29285497867`, final
  evidence-pointer rerun `29285802846`, and the post-review transport/package
  fix run `29287154661`; the release evidence record now binds to the
  code-bearing `1fd10f4` commit. The resulting docs-only rerun `29287368329`
  also passed all six jobs.
- The fresh adversarial review closed malformed MCP framing/params and
  notification-response defects, and the 0.5.0 compatibility note is now in
  release archives. The formatting and typecheck gates are fixed: all 148
  tracked Python files pass `ruff format --check`, and `basedpyright` passes
  across `scripts`, `tmcp_runtime`, and `tests` with zero errors.
- The hosted workflow now installs pinned Ruff/Basedpyright quality tools and
  runs formatting, lint, and typecheck gates in a dedicated Ubuntu job.
- Hosted run `29288492789` passes the quality job and all six platform jobs for
  cleanup commit `03e543d`.
- The 0.5.0 release is now merged, tagged, and published. GitHub release
  `v0.5.0` carries the verified artifact, and MCP Registry publication for
  `io.github.jakyeamos/tmcp` version `0.5.0` succeeded.
- AIOS needs a protected request-input protocol before confidential explicit
  requests can safely use it; the current boundary denies known sensitive values
  rather than forwarding them through process arguments.
- Cached projection requires nonblank IDs and timezone-aware timestamps; public
  v0.1 stays permissive and cache still orders by safe file mtime. Require
  canonical RFC3339 grammar before timestamps gain ranking/retention meaning.
- The legacy server and evaluator scripts remain broader than the target's thin
  compatibility adapter. Artifact planning, cache ingestion, CLI parsing, harvest
  argument projection, safety hardening, diagnostics, generic artifact-bundle
  persistence, receipt recording, global-promotion manifest assembly, and
  evaluator persistence, packet scoring, report, policy, rendering, and advisory
  boundaries are extracted; compatibility scripts retain producer-specific
  output selection, cache/persistence gating, and legacy evaluator,
  harvest-advisory, redaction, and AIOS aliases.

## Next step

Monitor the published release surfaces and handle any post-release reports;
no additional tag or publication action is pending.
