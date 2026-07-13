# TMCP Modernization Execution Plan

## Chosen strategy: parallel v2 core behind stable entrypoints

Use a parallel `tmcp_runtime` core while keeping the Node launcher and current
Python entrypoint as adapters. This is safer than an in-place monolith rewrite:
TMCP already has public MCP tools, CLI aliases, schemas, and plugin manifests.
Each vertical slice can migrate behind the adapter, preserve public behavior,
and delete the equivalent monolith code only after its consumers and tests have
moved.

This is neither a clean-slate compatibility break nor permanent dual-runtime
maintenance. The old server becomes progressively thinner and is reduced to a
compatibility transport layer by the final cutover.

The long-range sequencing is recorded in `docs/modernization/ROADMAP.md`:
product contract reset, runtime/adapter convergence, advanced capability
consolidation, and release transition. Work should advance toward those
outcomes rather than accumulate isolated helper extractions.

## Precondition

Do not publish another archive until Milestone 0 passes. The P0 packaging issue
is a release blocker even if the larger modernization is deferred.

## Milestones

### 0. Release safety emergency gate

**Objective:** eliminate release-tarball disclosure risk without waiting for
the full architectural migration.

**Affected surfaces:** archive-policy and release-check scripts, package tests,
release documentation, CI.

**Preserve:** portable source-checkout installation and deterministic archive
output.

**Change intentionally:** release contents become a reviewed tracked-file
allowlist; ignored/untracked files are no longer eligible for shipment.

**Implementation:**

- Build the archive from tracked/reviewed files only and reject symlinks.
- Add a denylist and content scan for `.env*`, keys, credentials, agent state,
  generated caches, and high-risk file names.
- Generate a manifest and verify it is deterministic.
- Add version-agnostic release trigger, least-privilege workflow permissions,
  and release-evidence verification to CI.

**Verification:** package a temp worktree containing untracked `.agents/`,
`.env`, a key fixture, and symlinks; assert none appear in the archive. Run
the full release package check twice and compare manifests/digests.

**Rollback:** retain the prior release artifact; revert the new packager only
if it rejects an intended tracked file, after adding that file to the reviewed
allowlist.

### 1. Contract freeze and target baseline

**Objective:** make public compatibility explicit before moving internals.

**Affected surfaces:** tool registry, schemas, manifests, version metadata,
golden fixtures, docs, CI.

**Implementation:**

- Inventory all eleven MCP tools, CLI aliases, defaults, schemas, output
  fields, state effects, and error semantics.
- Create a canonical tool registry and version descriptor with a check for
  metadata drift (including MCP initialize).
- Establish a shared CLI/MCP test client and frozen compatibility fixtures.
- Make tests hermetic by always supplying a temporary `TMCP_HOME`.

**Completion criteria:** every supported alias is represented in one registry;
all current public contracts have a fixture; `0.3.0` server metadata drift is
eliminated; CI checks the version and release evidence.

### 2. Safe input and storage foundation

**Objective:** centralize filesystem boundaries before moving feature logic.

**Affected surfaces:** new `tmcp_runtime/safety` and `storage` modules,
harvest/evaluation/promotion/review call sites, tests.

**Implementation:**

- Add a typed root policy and bounded safe reader.
- Redact before every parse and derived output; centralize diagnostics.
- Reject unsafe symlinks and enforce containment when traversal is enabled.
- Add atomic, restrictive-permission writes; explicit session/cache locations,
  retention, and clear/list operations.
- Restrict evaluation inputs to allowed `SKILL.md` paths and reuse safe
  reading.

**Completion criteria:** adversarial test suite covers every observed P1
filesystem/redaction defect; no feature reads local content outside the safety
service; no write occurs without a declared destination.

### 3. Compose and recompile vertical slice

**Objective:** deliver the coherent primary task journey end to end.

**Affected surfaces:** packet domain models, composition/recompile service,
MCP/CLI adapters, schemas, docs, golden tests.

**Implementation:**

- Move route/task identity and packet composition into typed services.
- Introduce optional project-local session records and run IDs.
- Return structured packets plus a concise Markdown card and clear state-effect
  notice.
- Support full recompile via run ID or explicit packet file; retain inline JSON
  compatibility input with documented limits.
- Reject unknown flags and remove stale `--no-write-artifacts` examples.

**Completion criteria:** a fresh install can compose, inspect, recompile, and
record a run without shell-pasting JSON; CLI/MCP output conforms to schemas;
legacy aliases remain covered.

### 4. Harvest, recommendation, promotion, and evaluation migration

**Objective:** move advanced discovery features onto the safe core without
changing their advisory trust model.

**Affected surfaces:** source graph, workflow catalog, promotion/cache,
evaluation services, skill docs, fixtures.

**Implementation:**

- Extract harvest and source graph services from the monolith.
- Inject composition into evaluation instead of importing private adapter code.
- Make preview versus write state explicit in results and Markdown.
- Split core primitives from stable curated workflows and label experimental
  workflows consistently.
- Add migration readers for existing promoted graphs and receipts.

**Completion criteria:** advanced flows operate through the shared safety and
storage APIs; old artifact formats are readable; promotions remain explicit;
workflow labels match docs, registry, and runtime.

### 5. Evidence-review vertical slice

**Objective:** make expert review outputs trustworthy and comprehensible.

**Affected surfaces:** rubric/review service, evidence model, artifact writer,
UI-rubric skill/docs, tests.

**Implementation:**

- Add explicit evidence-mode fields (`rendered`, `source_only`,
  `needs_evidence`).
- Make artifact output opt-in or require an output location before writing.
- Render a short review card before structured details.
- Pass sensitive AIOS inputs through a protected channel only when the caller
  explicitly chooses the adapter.

**Completion criteria:** source-only audit never implies browser inspection;
no-evidence review has a clear remediation path and no surprise persistence;
all artifacts are redacted and atomically written.

### 6. Thin-adapter cutover and deletion

**Objective:** remove the monolith as the product implementation.

**Affected surfaces:** `scripts/tmcp_mcp_server.py`, legacy helpers, tests,
docs, quality exceptions.

**Implementation:**

- Route MCP and CLI calls through `tmcp_runtime` only.
- Keep MCP framing/JSON-RPC and CLI output/error translation in
  `tmcp_runtime/adapters/`, with a typed request/result boundary for tool
  dispatch.
- Keep the historical script path as a small compatibility adapter.
- Delete migrated server implementations, duplicate helpers, dynamic reverse
  imports, stale schemas/docs, and obsolete quality-gate exceptions.
- Replace private-function tests with service contracts and end-to-end transport
  checks.

**Completion criteria:** all public MCP and CLI calls enter through runtime
adapters; the compatibility adapter is transport-only; no domain feature
imports it; code search finds no duplicate old paths; all public behavior is
covered by service and end-to-end tests.

### 7. Release hardening and adversarial review

**Objective:** prove the result is safe to ship.

**Implementation and verification:**

- Run the complete matrix: formatting, lint, strict typechecking, unit tests,
  CLI/MCP end-to-end tests, install, release evidence, archive content,
  deterministic package, and cross-platform CI.
- Exercise first-run, session recompile, migration-read, preview/promotion,
  evidence review, missing-AIOS, and malicious local-input scenarios.
- Start a fresh review pass for security/privacy, artifact migration,
  architecture, documentation, and release provenance.
- Fix confirmed P0/P1/P2 findings, then rerun the full matrix.

**Completion criteria:** no confirmed P0/P1 remains; all P2 findings are fixed
or explicitly accepted; docs and schemas match observed CLI/MCP behavior.

## Migration and rollback plan

| Surface | Migration | Rollback |
| --- | --- | --- |
| MCP/CLI inputs | Preserve names and aliases through adapter; version new behavior explicitly. | Pin the old package or route legacy clients through compatibility mode. |
| Packet schemas | Add fields compatibly; introduce a new identifier for breaking semantics. | Continue reading old packet schemas. |
| `.tmcp/` sessions | Never create or migrate implicitly; import on request and retain originals. | Revert to original files; no automatic deletion. |
| `TMCP_HOME` cache | Read old promoted graphs/receipts; write new location only after opt-in. | Re-enable legacy cache mode or restore copied artifacts. |
| Release archives | Gate publication on new manifest/scan checks. | Do not replace an already published archive; issue a revocation/release note if needed. |

## Milestone-wide rules

- The application must be runnable at every milestone boundary.
- Each milestone ends with the smallest relevant tests plus the full validation
  suite and a coherent commit.
- Do not keep old and new feature implementations after their consumers have
  migrated, except for the declared public transport compatibility adapter.
- No test may be skipped, weakened, or broad-catch an error to claim success.
- Record behavior intentionally changed, validation evidence, migration notes,
  and remaining risks in `PROGRESS.md` after each milestone.
