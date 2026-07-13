# TMCP Modernization Target

## Product definition

TMCP should be a trustworthy, portable operating-packet compiler for agents:
it turns an explicit task and bounded local evidence into a clear operating
contract, can update that contract from new evidence, and records outcomes only
when the caller deliberately opts into persistence.

The target is not a larger workflow catalog. It is a smaller, legible core with
safe advanced capabilities.

## Product principles

1. **Safe before clever.** No release archive, harvest, or evaluation can read
   or emit an out-of-bound local file by accident.
2. **One default journey.** `compose → update/recompile → record outcome` is
   the only first-run story. `explain`, harvest, recommendation, promotion,
   evaluation, and raw schemas are clearly advanced or compatibility surfaces.
3. **Zero surprise writes.** Each command declares whether it writes, where,
   and why. Preview is the default where a write is not the purpose of the
   command.
4. **Evidence is explicit.** Every review identifies `rendered`,
   `source_only`, or `needs_evidence`; no source-only result masquerades as
   a browser audit.
5. **Structured for machines, readable for people.** JSON schemas remain the
   integration contract; a concise Markdown packet card is the human-facing
   primary view.
6. **One source of truth.** Tool metadata, workflow stability, versioning,
   aliases, docs snippets, and release validation derive from canonical
   registries rather than parallel lists.
7. **Portable by default.** No third-party runtime dependency, no mandatory
   package install, and no network requirement for standalone use.

## Target user journeys

### Run a task

```text
compose "objective" [--session <path>]
  -> packet card: task identity, evidence mode, sources, instructions,
     verification, next action, and state effects
```

The default is a stateless, non-writing operation. `--session` is an explicit
opt-in to an atomic project-local run record such as
`.tmcp/runs/<run-id>.json`.

### Update a run

```text
recompile <run-id> --files-changed … --failures …
  -> complete next packet + human-readable add/drop/reason diff
```

Inline JSON remains a documented compatibility input, but the standard CLI path
uses a run ID or an explicitly named packet file. The tool always reports
whether it has read or written local state.

### Review evidence

```text
review-plan "objective" --evidence-mode source_only|rendered
  -> rubric, evidence gaps, remediation plan, write preview
```

Rendered/browser evidence is caller-supplied and never implied. Artifact
creation is opt-in, or the tool requires an explicit output path.

### Use advanced discovery safely

Harvest, evaluate, recommend, and promote make the selected roots, exclusion
policy, redaction result, output boundary, and persistence effects visible.
Promotion remains an intentional write after review.

## Target information architecture

| Area | Purpose | Default state |
| --- | --- | --- |
| Run a task | Compile a current operating packet. | Read-only / no cache. |
| Understand a run | Inspect identity, evidence, constraints, and next action. | Read-only. |
| Update a run | Recompile a saved packet and show a diff. | Explicit session write only. |
| Record outcome | Persist a receipt. | Explicit write. |
| Advanced | Harvest, evaluate, recommend, promote, raw schema work. | Narrow roots and visible effects. |

## Runtime architecture

Keep `scripts/tmcp_launcher.mjs` and `scripts/tmcp_mcp_server.py` as stable
entrypoints, but reduce the latter to a transport adapter over a new
stdlib-only package.

```text
tmcp_runtime/
  api/          canonical tool registry, version, schemas, request/response models
  domain/       packet, route, source, workflow, and evidence models
  services/     compose, recompile, harvest, recommend, promote, review, evaluate
  safety/       root policy, safe reader, redaction, archive policy, secret scan
  storage/      explicit sessions, optional cache, receipts, retention, atomic writes
  adapters/     MCP stdio, CLI rendering/parsing, optional AIOS

scripts/
  tmcp_mcp_server.py       compatibility entrypoint and transport wiring
  tmcp_launcher.mjs        unchanged public Node launcher
  check_*.py               release/install compatibility checks
```

### Boundary rules

- `api` owns one tool registry: MCP schemas, CLI aliases/defaults, help text,
  stability labels, and verification expectations derive from it.
- `services` depend on typed domain and safety interfaces, never on MCP or CLI
  parsing.
- `safety` is the only place that resolves caller files, follows symlinks,
  reads text, redacts content, or decides archive eligibility.
- `storage` owns only explicitly requested persistence and uses atomic,
  permissions-restricted writes.
- `adapters` translate transport payloads to domain requests and render both
  structured JSON and concise Markdown. AIOS is a separately selected adapter,
  not an implicit branch in core logic.
- Evaluation receives a compose-service interface; it must never import a
  private function from the server adapter.

## Security and privacy target

- Release from a tracked-file allowlist with a denylist, archive manifest,
  secret scan, and reproducibility check.
- Deny symlink traversal by default across packaging, harvesting, and
  evaluation. Explicit traversal still enforces root containment.
- Apply redaction before parsing, title derivation, diagnostics, artifacts, and
  responses. Test every output path.
- Restrict file inputs by root, extension, size, type, and total budget.
- Make persistent data project-scoped by default; cache reads/writes are
  opt-in in the new default path. Preserve the old global behavior behind an
  explicit compatibility mode.
- Use restricted permissions and atomic replacement for local artifacts;
  provide listing, retention, and clear operations.

## Contracts and migration

- Preserve existing tool names and versioned schemas through a compatibility
  adapter. Do not repurpose an old schema identifier.
- Keep additive output fields compatible; introduce a new schema version for
  behaviorally breaking fields or new session semantics.
- Read existing `.tmcp/` and `TMCP_HOME` artifacts; migrate only when the
  user opts in and never delete legacy data automatically.
- Keep `TMCP_PYTHON`, `AIOS_ROOT`, `TMCP_HOME`, Content-Length stdio
  framing, relative launcher paths, and standalone operation.
- Introduce a canonical version descriptor plus a check that validates MCP
  server info, manifests, registry metadata, citation, release evidence, and
  tag workflow configuration.

## Quality strategy

- Unit tests for services and safety boundaries, not private adapter helpers.
- End-to-end CLI and stdio MCP tests through a shared test client.
- Contract tests that execute every public documentation snippet in a temporary
  project and reject unknown flags.
- Adversarial fixtures for ignored files, secret-like content, seed metadata,
  file and directory symlinks, oversized inputs, unsafe output paths, and cache
  migration.
- Cross-platform CI with hermetic `TMCP_HOME`, strict typechecking,
  formatting, linting, install checks, release-evidence checks, package
  content/provenance checks, and version synchronization checks.

## Deliberate non-goals

- A browser dashboard or visual application shell.
- A runtime dependency on AIOS, a database, a package registry, or network
  connectivity.
- Automatic promotion of harvested knowledge or automatic execution of
  third-party instructions.
- A breaking removal of the deployed MCP/CLI surface without a versioned,
  tested migration path.

## Decisions requiring product judgment

The following defaults are recommended so planning can proceed without blocking.
They should be confirmed before implementation starts.

| Decision | Recommended default | Why it matters |
| --- | --- | --- |
| New default storage behavior | Stateless/no-cache; sessions and global cache are explicit opt-ins. | Improves privacy, reproducibility, and user trust; changes convenience semantics. |
| Compatibility release | Ship as `0.5.0` with a documented compatibility adapter and deprecations. | The safe defaults and session workflow are material product changes. |
| AIOS invocation | `adapter=auto` always stays standalone; `adapter=aios` is an explicit opt-in. | Avoids unexpected local subprocess execution and makes data-forwarding consent explicit. |
| Artifact writes | Review and receipt writes require explicit opt-in/path in the new flow; legacy aliases retain behavior with a visible warning until the next breaking release. | Balances safety with existing integrations. |
| Stable catalog policy | Publish a small set of core primitives plus a separately versioned curated-workflow catalog. | Ends ambiguity between stable product APIs and experimental skill families. |
