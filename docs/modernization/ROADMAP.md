# Long-Range Modernization Roadmap

## End state

TMCP is one coherent, portable operating-packet compiler. A caller can run the
default journey—compose a packet, update it from evidence, and record an
outcome—without knowing which internal service produced it. Advanced discovery
and review capabilities remain explicit, bounded, and clearly separated from
the core journey.

The migration is organized around end-state outcomes, not individual helper
extractions. Each horizon ends with a runnable product, contract evidence, and
an explicit rollback path.

## Horizon 1 — Product contract reset

Make the default product experience unambiguous:

- `compose → session → recompile → receipt` is the primary journey.
- Evidence modes are explicit: `rendered`, `source_only`, or `needs_evidence`.
- Every operation declares read-only, optional-write, or default-write effects.
- The tool registry, CLI aliases, MCP schemas, version metadata, and docs share
  one source of truth.

Exit criteria: the documented journey works from a fresh install; contract
tests cover every public alias; no documentation implies an unavailable state
effect or browser inspection.

## Horizon 2 — Runtime and adapter convergence

Make `tmcp_runtime` the product implementation and reduce the Python entrypoint
to transport and compatibility wiring:

- `tmcp_runtime/adapters/mcp.py` owns MCP framing and JSON-RPC transport.
- `tmcp_runtime/adapters/cli.py` owns CLI output/error translation.
- A typed request context and result contract connect adapters to services.
- Tool dispatch is a registry-driven adapter concern, not a monolithic server
  branch.
- The historical `scripts/` modules remain only where deployed callers need
  compatibility aliases.

Exit criteria: all public MCP and CLI calls enter through adapters; the server
contains no domain policy, filesystem reads, storage policy, or duplicated
transport logic; service tests and end-to-end transport tests cover behavior.

## Horizon 3 — Advanced capability consolidation

Make advanced features coherent without expanding their authority:

- Harvest, evaluation, review, recommendation, and promotion consume the same
  safe source and evidence contracts.
- Stable core primitives and experimental curated workflows are separately
  versioned and labeled.
- Existing local artifacts have migration readers; migration never deletes
  legacy data automatically.
- Preview, persistence, promotion, cache activation, and AIOS execution remain
  explicit and visible.

Exit criteria: advanced flows preserve advisory trust semantics, use bounded
safe inputs, expose state effects, and have migration/rollback fixtures.

## Horizon 4 — Release transition and hardening

Turn the modernization into a shippable compatibility release:

- Publish the planned `0.5.0` compatibility/version process.
- Add strict formatting, linting, typechecking, contract, and cross-platform
  gates where the project supports them.
- Run adversarial security, privacy, data-integrity, architecture, and release
  reviews from a fresh context.
- Document deprecations, compatibility aliases, migration readers, rollback,
  and the removal criteria for legacy server paths.

Exit criteria: reproducible packages pass the full matrix; no confirmed P0/P1
findings remain; every accepted P2 has an owner and rationale; the release
branch is deployable and the compatibility surface is documented.

## Current position

Horizon 1 is substantially implemented. Safety, storage, packet/recompile,
evaluation, harvest advisory, and redaction ownership are in the runtime. The
first Horizon 2 slice is complete: MCP framing/JSON-RPC and CLI execution now
live in runtime adapters. The typed request/result boundary and registry-owned
tool dispatch are also complete; the legacy server now supplies handlers and
compatibility wrappers without owning transport-level tool selection. Optional
AIOS execution is now an explicit runtime adapter with its own redaction and
subprocess boundary.

Runtime-state/recompile orchestration now lives behind an explicit service
context with source, cache, and composition callbacks supplied by the adapter.
Project-local session lifecycle orchestration now lives in a runtime service
over an injected storage protocol; the adapter retains the validated store
factory and final redaction. Generic artifact-bundle persistence now lives in a
runtime service; the adapter supplies redaction, path presentation, and
verified storage callbacks while retaining output-root selection and capability
checks. Receipt recording now uses the same callback-driven runtime boundary
while preserving adapter-owned clock, opaque identity, path, and write
authority. Global-promotion manifest assembly now lives in a runtime service;
the adapter retains global roots, persistence gating, opaque identity, and cache
 authority. Explain packet assembly and review evidence parsing now also live in
 runtime services. The thin-adapter deletion pass removed the server's private
 CLI parser, AIOS subprocess, harvest-constant, and unused schema seams; tests
 now target their runtime owners directly. The first Horizon 3 migration reader
 projects legacy promoted summaries into the current graph contract without
 mutating source artifacts; current graph files take precedence when both
 formats exist. Remaining work is advanced-capability migration completion and
 Horizon 4 release hardening. The release compile/install surface is now
 centralized and the cross-platform workflow invokes the same inventory used
 by package checks.

The legacy-artifact audit found two supported promotion representations: the
current `promotion-graph.json` and the legacy `promoted-harvest.json` summary;
the latter now projects read-only into the former and is suppressed when a
current graph is present. Receipts and project-local sessions have no alternate
shipped schema in this tree and remain strict readers.

The 0.5.0 compatibility cutover is now active on the release-candidate branch
in `docs/release-notes/v0.5.0-compatibility.md`; its evidence record now
points to successful post-cutover PR run `29285497867`.

The first hosted PR run exposed a Windows read-only regression: exact-file
inputs were rejected because Windows lacks `O_NOFOLLOW`. The reader now uses a
validated path-read fallback only for read-only inputs while durable writes
remain fail-closed. A follow-up run reduced the remaining Windows failures to
path/newline presentation contracts; `1a59e2f` normalizes those contracts and
hosted run `29284457105` passes the complete six-job matrix, including both
Windows package/evidence jobs. The final evidence-pointer rerun is next.
