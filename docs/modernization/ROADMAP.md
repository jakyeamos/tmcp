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
The next major unit is to move remaining persistence/session orchestration and
delete obsolete server paths.
