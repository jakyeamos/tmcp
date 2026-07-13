# TMCP Modernization Progress

## Current state

**Phase:** Milestone 3 adapter thinning and security hardening. Receipt
construction/presentation, artifact manifests, semantic cache validation,
fail-closed cache opt-in, storage cache ingestion, CLI parsing, harvest
  argument projection, safety hardening, diagnostics, evaluator artifact
  persistence, packet/report assembly, policy, rendering, advisory, and input
  hardening complete;
  map the read-only boundary.

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
Harvest labels and source-node policy are now pure domain modules, while the
runtime service owns safe traversal, redaction, scoped-seed projection, packet
seeding, and artifact writes. The adapter injects only the evaluator-specific
advisory callback and retains compatibility facades used by existing callers.
Workflow recommendation assembly now has its own read-only runtime service. The
adapter injects advisory and compose-preview callbacks, then retains result
redaction, artifact persistence, promotion, and global-cache authority.
Promotion target selection, graph construction, and status/result assembly are
also runtime-owned. The adapter retains opaque storage-key derivation, path
approval, local/global writes, and all cache validation/projection.
Standalone review-plan assembly is pure and runtime-owned. The adapter retains
source harvest, evidence parsing, redaction, approved output selection, artifact
persistence, and explicit AIOS dispatch. Global-cache policy remains pure;
storage now owns bounded, redacted, TOCTOU-safe cache ingestion, while the adapter
owns cache-root selection and durable writes. Optional AIOS execution remains adapter-only
and redacts child payloads, configuration paths, composed output, and execution
errors before returning transport results.
Runtime context normalization, family transitions, identity deltas, proposal
validation, and state shaping are now a pure domain reducer over adapter-supplied
source nodes and cache warnings; the adapter keeps source/cache acquisition,
sessions, recompile, redaction, and transport authority.
Packet composition and source-node enrichment are now an in-memory service over
adapter-supplied harvested nodes and canonical cache snapshots. Storage supplies
cache reads; the adapter retains path redaction, harvest, sessions, recompile, and transport;
the service defensively discards any injected cache inputs under
cache_policy=none.
Full recompile finalization is also service-owned once the adapter has validated
raw path precedence and built a fresh packet. The service merges runtime deltas,
enriches required evidence, applies the authoritative runtime identity before
validated proposals, then derives the diff and Markdown. Sessions and final
response redaction remain adapter-owned.
Public compose and standalone/auto explain responses now redact complete result
trees only after their internal session/packet work is complete.
AIOS is now an explicit-only adapter: `auto` stays inside TMCP, and known
sensitive values are rejected before an explicit AIOS subprocess receives its
arguments. Review evidence is decoded before that check so escaped sensitive
values cannot bypass it.
Run receipts are now built and acknowledged by a pure domain module. The adapter
retains the UTC clock, raw-to-redacted opaque identity, filename digest/nonce,
safe storage write, cache ingress, and final response redaction. Only literal
`cache_policy=global` can consume shared graphs or receipts. Artifact manifests,
Markdown rendering, and public path aliases are now pure service data; the adapter
retains output-root selection, final redaction, and atomic persistence. Cached
receipt projection requires nonblank IDs and timezone-aware timestamps without
changing the public receipt schema. Evaluator artifact manifests are also pure
service data; the evaluator is storage-free and the adapter alone selects roots,
persists atomic bundles, and returns redacted path aliases. Packet-inclusion
expectation lookup and composed-packet diffing are now a pure service over an
adapter-injected callback.

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
- Treat evaluator advisories as an explicit adapter-injected dependency of
  harvest-node construction; pure runtime modules must not import the MCP adapter.
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
- 1476d21 makes AIOS explicit-only and rejects known sensitive command values,
  including JSON-escaped review evidence, before external execution. The public
  tool contract, release guidance, and install checks pass.
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
  and validates nested shapes. Full suite: 390 tests, three expected skips

## Blockers and risks

- The primary checkout contains user-owned uncommitted work that is not included
  in this audit branch. Integrate or supersede it deliberately during approved
  implementation.
- Hosted matrix evidence is pending because this branch has no pull request or
  tag-triggered run; local package and contract checks are current.
- The branch intentionally retains `0.4.0` release metadata while unpublished;
  before release, use the target's planned `0.5.0` compatibility/version process
  because the stateless default and explicit-only AIOS behavior are material
  changes.
- AIOS needs a protected request-input protocol before confidential explicit
  requests can safely use it; the current boundary denies known sensitive values
  rather than forwarding them through process arguments.
- Cached projection requires nonblank IDs and timezone-aware timestamps; public
  v0.1 stays permissive and cache still orders by safe file mtime. Require
  canonical RFC3339 grammar before timestamps gain ranking/retention meaning.
- The legacy server and evaluator scripts remain broader than the target's thin
  transport adapter. Artifact planning, cache ingestion, CLI parsing, harvest
  argument projection, safety hardening, diagnostics, harvest persistence, and
  evaluator persistence, packet scoring, report, policy, rendering, and advisory
  boundaries are extracted; mode orchestration and composition-failure policy
  remain to be cut over without moving root, write, or transport authority.

## Next step

Narrow composition-failure handling before extracting evaluator mode orchestration.
