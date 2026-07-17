# TMCP CLI

The canonical portable launcher is:

```bash
tmcp doctor
```

Use the package-root `tmcp` executable (or `./tmcp` when the root is not on
`PATH`) so Python discovery remains cross-platform. With no arguments, it starts
the MCP stdio server. With arguments, it invokes the same implementations
exposed through MCP tools and prints JSON. Launcher portability is separate from
durable artifact persistence; see [Compatibility](COMPATIBILITY.md#secure-artifact-persistence).

`node scripts/tmcp_launcher.mjs` remains supported for existing MCP
configurations and compatibility scripts; new human-facing commands should use
`tmcp`.

## Commands

`record-receipt` requires `status` to report secure artifact persistence. It
fails closed on portable-only hosts because a receipt is itself a durable
artifact.

```bash
tmcp --help
tmcp --version
tmcp list-tools
tmcp doctor
tmcp status
tmcp explain "Review developer onboarding commands" --project-path . --adapter standalone
tmcp explain "Review developer onboarding commands" --project-path . --compose
tmcp compose-packet "Fix the dashboard UI bug" --project-path "$PWD" --phase start --session-id dashboard-run
tmcp runtime-next "Fix the dashboard UI bug" --current-phase verification --files-changed app/page.tsx --failures "vitest failed"
tmcp recompile-packet "Fix the dashboard UI bug" --project-path "$PWD" --session-id dashboard-run --current-phase runtime
tmcp record-receipt packet-123 --activated-atoms ui-browser-verification --outcome passed
tmcp harvest . --objective "Harvest reusable project workflow behavior" --limit 40
tmcp evaluate-skills --skill-paths path/to/SKILL.md --task-fixtures '[...]'
tmcp recommend . --candidate-workflows release_readiness --candidate-workflows developer_experience --min-confidence 0.1 --compose
tmcp promote-harvest . --selected-workflows release_readiness_workflow --output-dir .tmcp/promoted-harvests/release-readiness
tmcp review-plan "Review release portability" --project-path . --evidence-json '[{"dimension_id":"source_grounding","severity":"warning","summary":"Release claims need fresh package evidence.","evidence":["python3 scripts/check_release_package.py ."],"recommended_fix":"Run and cite the release package check before publishing."}]'
```

## Composable Packets

Use `tmcp_compose_packet` / `compose-packet` when an agent needs a small current-task packet instead of a workflow list. The output includes active instructions, required reads, tool/script prompts, verification gates, stop conditions, deferred atoms, ignored sources, conflicts, citations, and a receipt template.

Use `tmcp_runtime_next` / `runtime-next` after changed files, failures, browser evidence, phase changes, or user redirects. Use `tmcp_record_receipt` / `record-receipt` after meaningful verification or outcome when secure artifact persistence is available.

`tmcp_explain --compose` and `tmcp_recommend_workflows --compose` preserve their legacy output and add a composed packet.

The machine-readable contracts are `tmcp-composed-packet-v0.1`, `tmcp-runtime-next-v0.1`, `tmcp-recompiled-packet-v0.1`, `tmcp-run-receipt-v0.1`, and the project-local `tmcp-run-session-v0.1`. Promoted harvest cache entries use `tmcp-promoted-harvest-graph-v0.1`.

## Packet Sessions

Composition and runtime remain read-only unless `session_id` is supplied. A
session requires an explicit absolute `project_path`; `compose-packet` creates one
redacted latest-packet record beneath that project, and `recompile-packet` (or
`runtime-next --output-mode full`) reloads and replaces that record. The result
contains additive `session` metadata with an opaque key, record path, revision,
and packet id.

Sessions are deliberately narrow: the raw identifier is not persisted in the
filename (identifiers are labels, not secrets), creation never replaces an existing session, and updates are
serialized against the current revision. They have no automatic creation, global
lookup, history, retention policy, rollback, or multi-agent coordination. Use a
new identifier for a new run and serialize callers that share one. On a host
without secure persistence, session operations fail before creating artifacts.

`session_id` is valid only for a full recompile and cannot be combined with
`previous_packet`. Existing inline `previous_packet` calls remain the portable
compatibility path. `explain --compose` and `recommend --compose` do not accept
or create packet sessions.

Experimental workflows remain callable through existing aliases and `candidate_workflows`, for example:

```bash
tmcp recommend . --candidate-workflows agent_handoff --min-confidence 0.1
tmcp expert-ui-rubric --project-path .
```

Running a review without `--evidence-json` returns `evidence_contract.starter_template`; fill it with concrete citations and rerun before expecting scored findings.

`promote-harvest` is the explicit persistence step after harvest/recommendation review. It writes a promoted graph with source-to-atom and atom-to-workflow edges. Use `--no-write-artifacts` for a preview; harvest and recommend do not reorganize durable routing state by themselves. Where `status` reports artifact persistence unavailable, all durable writes fail closed and preview mode is the portable option.

`harvest` does not follow source symlinks by default. Set `--follow-symlinks` only when the linked targets are intentionally in scope; TMCP still rejects targets outside the selected source root and redacts secret-like path metadata. Harvest artifact output is an atomic bundle, so an explicit `--output-dir` must be new or empty; omit it to use a unique `.tmcp/harvest-*` directory.

`evaluate-skills` follows the safety boundary described in the README: pass explicit `SKILL.md` files, optionally constrain them with a project root, and use a new or empty directory when writing an initial evaluation plan.

On secure-persistence hosts, `promote-harvest` also writes a redacted promoted graph to `TMCP_HOME/promoted-harvests/<opaque-promotion-key>/`, or `~/.tmcp/promoted-harvests/<opaque-promotion-key>/` when `TMCP_HOME` is unset. Receipts are written under `TMCP_HOME/receipts/<yyyy-mm>/`. Global cache content is advisory and cannot override higher-priority instructions.
`compose-packet` and `runtime-next` use `cache_policy=none` by default; pass
`--cache-policy global` only to opt into those advisory global artifacts.

## Argument Rules

- Kebab-case flags map to snake_case tool arguments.
- Flags without values become boolean `true`.
- `--no-<flag>` becomes boolean `false`.
- Repeat a flag to send an array.
- Values that look like JSON objects, arrays, numbers, booleans, or `null` are decoded.
- Use `--compact` when another tool will parse the output.

`doctor`, `status`, `explain`, `harvest`, `evaluate-skills`, `recommend`,
`promote-harvest`, `compose-packet`, `runtime-next`, `record-receipt`, and
`review-plan` are the canonical CLI names. Compatibility aliases remain
supported and are frozen in `tmcp_runtime/api/registry.py`; use `list-tools`
for the live MCP schema surface.

## Fallback Order

1. Exposed MCP tools.
2. Local `tmcp ...` CLI. Use this when `tool_search` returns no TMCP tools even though TMCP skills are installed.
3. Repo or plugin launcher script discovered relative to the installed skill/plugin root.
4. Explicit AIOS adapter only when `AIOS_ROOT` is configured and requested.
5. Manual packet synthesis using the same output contract.

For Codex discovery issues, run:

```bash
tmcp doctor --client codex
tmcp list-tools
```

If those pass but Codex still cannot find `tmcp_explain` or `expert_rubric_review_plan` through `tool_search`, report a Codex MCP discovery gap and continue through CLI-generated JSON/artifacts.

If no launcher is found, clone or copy TMCP, run `tmcp doctor` from the TMCP root, and set `TMCP_PYTHON` if Python discovery fails.

## Output Contract

Workflow outputs should include or cite:

- sources inspected
- skipped sources and why
- packet summary
- extracted behavior atoms
- evidence gaps
- recommendation or remediation plan
- verification expectations

AIOS remains optional. `--adapter auto` and `--adapter standalone` keep execution inside this package; use `--adapter aios` only when the caller explicitly opts into the local AIOS adapter. Expert review keeps `adapter=auto` standalone so evidence is not forwarded implicitly. An explicit AIOS review is read-only (`--no-write-artifacts`); durable review artifacts always use the standalone protected store.

Until AIOS supports protected request input, TMCP rejects known sensitive values before an AIOS command can receive them through process arguments. Use the standalone adapter for those requests.
