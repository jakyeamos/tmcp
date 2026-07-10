# TMCP Modernization Audit

**Baseline:** `72baf609a519bebdabc4287b2671f04554ef6c23` (`0.4.0` release)

**Scope:** Read-only audit of product behavior, runtime architecture, security
boundaries, release process, documentation, and verification. This audit did
not modify product code. It deliberately excludes the user-owned uncommitted
changes in the primary checkout (`skills/tmcp/SKILL.md` and `.agents/`).

## Executive assessment

TMCP has a strong core idea and a valuable portable implementation: natural
language intent is compiled into an advisory operating packet, then updated as
runtime evidence changes. Its best qualities are local-first execution,
standard-library portability, explicit provenance, and a clear trust boundary
between packet guidance and higher-priority instructions.

The `0.4.0` implementation is now carrying too much in one runtime module,
and its public experience has begun to diverge from its documented one. The
highest-priority issue is release safety: the package builder can publish
untracked or ignored local files, including secrets. That must be fixed before
the next release, independently of the deeper refactor.

This is not a browser-application redesign. TMCP's user interface is its
MCP/CLI output, Markdown artifacts, and installation documentation. The target
therefore focuses on a safe, coherent agent-facing experience and a modular
runtime rather than a visual dashboard.

## Baseline evidence

| Check | Result | Notes |
| --- | --- | --- |
| `python3 -m py_compile …` | Pass | All documented Python entrypoints compiled. |
| `node --check scripts/tmcp_launcher.mjs` | Pass | Launcher syntax is valid. |
| `python3 -m unittest discover -s tests` | Pass in isolated `TMCP_HOME` | 120 tests passed. Without isolation, one test tried to write to sandboxed `~/.tmcp`; this is a determinism issue, not a reproduced product failure. |
| `python3 scripts/check_install.py .` | Pass | Standalone MCP install shape works. |
| `python3 scripts/check_release_evidence.py .` | Pass | Current release evidence matches `0.4.0`. |
| `python3 scripts/check_release_package.py .` | Pass in isolated `TMCP_HOME` | Existing checks passed, but did not cover untracked/ignored secret inclusion. |
| `doctor`, `status`, `list-tools`, `compose-packet` smoke | Pass | Standalone mode and the core packet flow work. |

## Current system map

```text
Node launcher
  -> Python MCP/CLI server
       -> packet compile / runtime update / receipts
       -> harvest / recommend / promote / evaluate / review
       -> optional AIOS adapter and local filesystem storage

Public surface
  -> MCP tools + CLI aliases + JSON schemas
  -> Codex/Claude manifests + Markdown skills/docs
  -> release tarball and registry metadata
```

The main server, `scripts/tmcp_mcp_server.py`, is 8,662 lines and owns tool
schemas, MCP transport, CLI parsing, packet compilation, harvest, rubric
generation, workflow selection, persistence, AIOS adaptation, and output
formatting. `scripts/tmcp_route_catalog.py`, `scripts/tmcp_mcp_framing.py`,
and `scripts/tmcp_redaction.py` show the cohesive boundaries that the target
should extend.

## Preserve

- The product promise: intent → task-specific packet → runtime update →
  outcome receipt.
- Standalone, standard-library Python plus the cross-platform Node launcher.
- Existing MCP tool names, CLI aliases, stdio framing, schemas, and launch
  paths unless a versioned compatibility plan explicitly changes them.
- Advisory trust semantics: harvested text and promoted cache data never
  override system, developer, user, or repository instructions.
- Default redaction and the distinction between preview operations and explicit
  promotion.
- JSON schemas, golden fixtures, and the cross-platform CI matrix.

## Findings

### P0 — release builder can publish ignored or untracked local files

`scripts/check_release_package.py:17-35,88-105` packages a recursive
filesystem walk with a small hard-coded exclusion list. It does not use a
tracked-file allowlist, honor `.gitignore`, reject `.env*`/key material, or
exclude local agent state such as `.agents/`. The primary checkout currently
demonstrates the risk with untracked `.agents/` content.

**Impact:** a published archive can disclose secrets or private local process
material.

**Required remediation before release:** build from a tracked-file allowlist
(or `git archive` with a reviewed export policy), enforce a denylist and
secret scan, reject symlinks, and add archive-content tests for untracked
files, `.env*`, private keys, credentials, and agent state.

### P1 — local-file safety boundaries are incomplete

| Finding | Evidence | Target correction |
| --- | --- | --- |
| File symlinks are followed when `follow_symlinks=false`. | `scripts/tmcp_mcp_server.py:4876-4927,5455-5470` filters symlinked directories but reads symlinked files. | Reject all symlinks by default; when explicitly enabled, require the resolved path to remain inside the selected root. |
| Redaction is bypassed for scoped seeds and derived titles. | `scripts/tmcp_mcp_server.py:5490-5625,5699-5716,5738` derives output from raw text. | Establish a single safe-reader pipeline; redact before parse, derivation, artifact generation, and response rendering. |
| Skill evaluation reads arbitrary files without the harvest guardrails. | `scripts/tmcp_skill_evaluate.py:194-195,994-1071` accepts arbitrary paths and emits raw file content. | Permit only vetted `SKILL.md` files under approved roots, use the bounded/redacted reader, and cap attachments. |
| Global artifacts lack a clear privacy/retention model. | Review plans and receipts write under shared state by default (`scripts/tmcp_mcp_server.py:3764-3768,7783-7819`). | Make state effects explicit, use atomic restricted-permission writes, redact persisted fields, and provide list/clear/retention controls. |
| `adapter=auto` can implicitly execute AIOS and pass evidence via argv. | `scripts/tmcp_mcp_server.py:1863-1920,8375-8398`. | Default to standalone for sensitive actions; require AIOS opt-in and use protected stdin/files for sensitive payloads. |

### P1 — the documented core task flow is not reliably executable

The intended product path is composition → recompile → receipt, but its
documentation and implementation disagree:

- `README.md:91-105` refers to `.tmcp/last-packet.json`, but compose has no
  persistence option in `scripts/tmcp_mcp_server.py:1496-1524`.
- `docs/ADAPTIVE_PACKET_RUNTIME.md:533-540` advertises
  `--previous-packet @file`, while `_parse_previous_packet()` accepts only an
  object or inline JSON (`scripts/tmcp_mcp_server.py:2256-2263`).
- `docs/QUICKSTART.md:54` documents `--no-write-artifacts` for compose even
  though it is absent from the schema and silently ignored by the permissive
  parser (`scripts/tmcp_mcp_server.py:8542-8618`).

**Target correction:** introduce an explicit optional run/session record and
use a run ID or explicit packet file for recompile. A user should never need to
paste a large JSON packet into a shell.

### P1 — public metadata and taxonomy have drifted

- MCP initialization reports `0.3.0` at
  `scripts/tmcp_mcp_server.py:8438`, while manifests, registry metadata,
  citation data, and release evidence say `0.4.0`.
- Docs describe five stable workflows while runtime catalog logic treats only
  two as stable (`README.md:42`, `scripts/tmcp_mcp_server.py:210`).
- `tmcp_explain` is simultaneously presented as a starting point, legacy
  path, and compatibility tool across docs and skill content.

**Target correction:** make one typed tool/workflow registry and one version
source feed the transport, CLI, manifest validation, docs snippets, and release
checks. Present one default journey and label compatibility/advanced paths.

### P2 — architecture and tests make change unnecessarily risky

- The monolith owns unrelated transport, domain, policy, and storage concerns.
- `scripts/tmcp_skill_evaluate.py` dynamically imports the server's private
  compose function while the server imports the evaluator, creating a fragile
  reverse dependency.
- Tests commonly reach private server functions; parser behavior is
  reimplemented in tests and install checks instead of using a shared client.
- Runtime code has extensive dynamic `dict[str, Any]` use without a strict
  typed boundary or a lint/typecheck gate.

**Target correction:** extract a stdlib-only runtime package with public
service contracts, dependency injection for composition, typed request/response
models, and a thin MCP/CLI adapter.

### P2 — operational gates are incomplete

- `.github/workflows/verify.yml` hard-codes `0.4.0` tag patterns and does
  not run release-evidence verification.
- CI runs no formatter, lint, or strict typecheck.
- Release metadata is edited in multiple places and no check prevents version
  drift.
- The default test suite assumes a writable global TMCP home, which makes local
  execution less hermetic.

### P2 — agent-facing presentation needs to be more honest and legible

TMCP has no rendered UI. Its primary presentation should be concise Markdown
plus machine-readable structured content, not raw JSON alone. A review must
clearly identify its evidence mode: `rendered`, `source_only`, or
`needs_evidence`. Every operation that changes local state should state the
paths it will write before doing so.

## Scores

| Dimension | Current | Target | Rationale |
| --- | ---: | ---: | --- |
| Product coherence | 3 | 5 | Good thesis; conflicting default journeys. |
| Correctness and data integrity | 2 | 4 | Strong schemas, but unsafe persistence and release boundaries. |
| Architectural coherence | 2 | 4 | Valuable modules exist, but the main server is a monolith. |
| Maintainability | 2 | 4 | Coupled internals and duplicate metadata slow safe change. |
| Testability | 3 | 5 | Broad test coverage; needs public seams and adversarial fixtures. |
| Security and privacy | 1 | 5 | P0 package exposure plus local-file/redaction gaps. |
| Agent UX and accessibility | 2 | 4 | Markdown is viable; flows and state effects are unclear. |
| Performance | 3 | 4 | No urgent regression found; safe bounded I/O should be measurable. |
| Operability | 2 | 5 | Version/CI/release assertions need to become enforceable. |
| Developer experience | 2 | 5 | Simple runtime, but unclear docs and weak automation. |

## Constraints for implementation

- No database or remote customer data exists. Migration concerns are local
  `.tmcp/` artifacts and `TMCP_HOME` promoted graphs/receipts.
- Publishing archives, promotion, receipt recording, review artifact writes,
  and optional AIOS invocation are the meaningful irreversible operations.
- Preserve Python 3.10+, Node 20+, and macOS/Linux/Windows support.
- The existing `.planning` project says broad rewrites are out of scope. This
  modernization directive supersedes that scope and must be made explicit in
  the project truth before implementation begins.
