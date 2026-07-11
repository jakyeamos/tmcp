# tmcp

## What This Is

tmcp is a portable, local-first MCP/CLI package that compiles task-specific
operating packets from local skills, instructions, and evidence. This planning
project now tracks its proposed modernization from the released 0.4.0 baseline.

## Core Value

Deliver a trustworthy, portable packet compiler with explicit evidence,
safe local-file boundaries, coherent agent-facing workflows, and a maintainable
runtime.

## Requirements

### Validated

- Existing public MCP/CLI contracts and packet schemas are the compatibility
  baseline.
- TMCP is an agent-facing MCP/CLI/Markdown product, not a browser application.
- The released 0.4.0 runtime is portable and works without AIOS.

### Active

- [x] Close the P0 release-package disclosure risk before any new publication.
- [x] Freeze the MCP/CLI compatibility surface in a canonical registry with
  live metadata and transport checks.
- [ ] Migrate the monolithic runtime to a modular, stdlib-only core behind
  stable transport entrypoints.
- [ ] Establish an explicit compose → recompile → outcome journey with honest
  state and evidence modes.
- [ ] Make release, metadata, and verification gates enforceable.

### Out of Scope

- A browser dashboard or visual application shell.
- A required dependency on AIOS, a database, a registry, or network access.
- Silent breaking changes to existing MCP/CLI contracts.
- Automatic promotion of harvested instructions or execution of untrusted text.

## Context

- Baseline: 0.4.0 release commit `72baf609a519bebdabc4287b2671f04554ef6c23`.
- Modernization artifacts: `docs/modernization/AUDIT.md`,
  `docs/modernization/TARGET.md`, and `docs/modernization/EXEC_PLAN.md`.
- The prior QR remediation plan is parked rather than discarded; its
  behavior-preservation discipline remains valuable.

## Constraints

- **Git:** Commit in atomic units scoped to this repo and concern.
- **Release safety:** Do not publish before the package allowlist and secret
  containment gate pass.
- **Compatibility:** Preserve tool names, schema identifiers, stdio framing,
  standalone operation, and documented launch paths through a versioned plan.
- **Verification:** Every milestone must end in focused checks and the full
  package/install validation suite.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use a parallel v2 core behind stable entrypoints | Public MCP/CLI contracts require staged migration, not an uncontrolled rewrite. | Approved for planning |
| Make package safety Milestone 0 | The current packager can include untracked/ignored local content. | Complete |
| Freeze public contracts before core extraction | Protect tool names, schemas, aliases, and release metadata while internals move. | Complete |
| Treat CLI/MCP/Markdown as the UX surface | TMCP has no browser UI. | Approved for planning |
| Keep Quality Runner advisory-only | Quality Runner remains useful evidence, not an execution system. | Retained |

---
*Last updated: 2026-07-11 after Milestone 1 contract-freeze verification*
