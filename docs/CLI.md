# TMCP CLI

The canonical portable launcher is:

```bash
node scripts/tmcp_launcher.mjs doctor
```

Use the Node launcher everywhere so Python discovery remains cross-platform. With no arguments, it starts the MCP stdio server. With arguments, it invokes the same implementations exposed through MCP tools and prints JSON. Launcher portability is separate from durable artifact persistence; see [Compatibility](COMPATIBILITY.md#secure-artifact-persistence).

## Commands

`record-receipt` requires `status` to report secure artifact persistence. It
fails closed on portable-only hosts because a receipt is itself a durable
artifact.

```bash
node scripts/tmcp_launcher.mjs list-tools
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
node scripts/tmcp_launcher.mjs explain "Review developer onboarding commands" --project-path . --adapter standalone
node scripts/tmcp_launcher.mjs explain "Review developer onboarding commands" --project-path . --compose
node scripts/tmcp_launcher.mjs prepare-composition "Fix and verify the dashboard workflow" --project-path "$PWD"
node scripts/tmcp_launcher.mjs promote-composition-recipe research-review --project-path "$PWD" --composition-plan '{...}' --receipts '[...]' --explicit-promotion
node scripts/tmcp_launcher.mjs compose-packet "Fix the dashboard UI bug" --project-path "$PWD" --phase start --session-id dashboard-run
node scripts/tmcp_launcher.mjs runtime-next "Fix the dashboard UI bug" --current-phase verification --files-changed app/page.tsx --failures "vitest failed"
node scripts/tmcp_launcher.mjs recompile-packet "Fix the dashboard UI bug" --project-path "$PWD" --session-id dashboard-run --current-phase runtime
node scripts/tmcp_launcher.mjs record-receipt packet-123 --activated-atoms ui-browser-verification --outcome passed
node scripts/tmcp_launcher.mjs harvest . --objective "Harvest reusable project workflow behavior" --limit 40
node scripts/tmcp_launcher.mjs evaluate-skills --skill-paths path/to/SKILL.md --task-fixtures '[...]'
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows release_readiness --candidate-workflows developer_experience --min-confidence 0.1 --compose
node scripts/tmcp_launcher.mjs promote-harvest . --selected-workflows release_readiness_workflow --output-dir .tmcp/promoted-harvests/release-readiness
node scripts/tmcp_launcher.mjs review-plan "Review release portability" --project-path . --evidence-json '[{"dimension_id":"source_grounding","severity":"warning","summary":"Release claims need fresh package evidence.","evidence":["python3 scripts/check_release_package.py ."],"recommended_fix":"Run and cite the release package check before publishing."}]'
```

## Composable Packets

For substantial multi-step, tool-using, high-stakes, or skill-relevant work, ordinary hosts should run this flow without asking the user to name TMCP or skills:

1. `tmcp_prepare_composition` / `prepare-composition` returns bounded candidate slices, source roles and content digests, diagnostics, and a `tmcp-semantic-proposal-v0.1` starter.
2. The host fills that contract using cited slices. TMCP remains the validator; the proposal cannot create authority, unknown nodes, unsupported relationships, cycles, or active conflicts.
3. `tmcp_compose_packet` / `compose-packet` validates the proposal and adds `tmcp-composition-plan-v0.1` to the familiar packet. The agent executes its active stage and honors entry, exit, and verification gates.

Bypass the assisted flow for trivial conversation and simple status replies. Calling compose without `semantic_proposal` remains the compatible deterministic path. TMCP compiles and validates; it does not execute tools or mutations.

MCP hosts should pass the proposal object directly. CLI hosts can pass the same host-produced JSON through `--semantic-proposal '<json>'`; do not invent unsupported nodes or citations merely to fill the flag.

Use `tmcp_runtime_next` / `runtime-next` after reads, commands, changed files, failures, browser evidence, verification results, phase changes, or user redirects. Prefer a full recompile when relationships, stages, gates, or obligations may change. Use `tmcp_record_receipt` / `record-receipt` after meaningful verification or outcome when secure artifact persistence is available; receipts never auto-promote a recipe.

Use `tmcp_promote_composition_recipe` / `promote-composition-recipe` only after review. It requires `explicit_promotion=true`, at least three verified receipts across two fixtures, identical graph provenance, passing safety gates, median synergy lift of at least `0.10`, median compiler and order lift of at least `0.05`, and context ratio at or below `0.75`. Every matching receipt must include a structured safety-classified gate (`safety=true` or a safety/security/privacy category, type, or identifier) with an explicit passing result; missing, ambiguous, or failing safety-gate evidence blocks promotion. A named recipe is project-local, create-only, and revalidated against current source content every time it loads.

`tmcp_explain --compose` and `tmcp_recommend_workflows --compose` preserve their legacy output and add a composed packet.

The assisted contracts are `tmcp-composition-preflight-v0.1`, `tmcp-semantic-proposal-v0.1`, and `tmcp-composition-plan-v0.1`. Existing packet/runtime contracts remain unchanged and compose without a proposal stays supported.

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
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows agent_handoff --min-confidence 0.1
node scripts/tmcp_launcher.mjs expert-ui-rubric --project-path .
```

Running a review without `--evidence-json` returns `evidence_contract.starter_template`; fill it with concrete citations and rerun before expecting scored findings.

`promote-harvest` is the explicit persistence step after harvest/recommendation review. It writes a promoted graph with source-to-atom and atom-to-workflow edges. Use `--no-write-artifacts` for a preview; harvest and recommend do not reorganize durable routing state by themselves. Where `status` reports artifact persistence unavailable, all durable writes fail closed and preview mode is the portable option.

`harvest` does not follow source symlinks by default. Set `--follow-symlinks` only when the linked targets are intentionally in scope; TMCP still rejects targets outside the selected source root and redacts secret-like path metadata. Harvest artifact output is an atomic bundle, so an explicit `--output-dir` must be new or empty; omit it to use a unique `.tmcp/harvest-*` directory.

`evaluate-skills` follows the safety boundary described in the README: pass explicit `SKILL.md` files, optionally constrain them with a project root, and use a new or empty directory when writing an initial evaluation plan.

On secure-persistence hosts, `promote-harvest` also writes a redacted promoted graph to `TMCP_HOME/promoted-harvests/<opaque-promotion-key>/`, or `~/.tmcp/promoted-harvests/<opaque-promotion-key>/` when `TMCP_HOME` is unset. Receipts are written under `TMCP_HOME/receipts/<yyyy-mm>/`. Global cache content is advisory and cannot override higher-priority instructions.
`compose-packet` and `runtime-next` use `cache_policy=none` by default. Pass
`--cache-policy project` only for reviewed project-local recipes, or
`--cache-policy global` to opt into advisory shared artifacts. Promotion remains
an explicit reviewed command under every policy.

## Argument Rules

- Kebab-case flags map to snake_case tool arguments.
- Flags without values become boolean `true`.
- `--no-<flag>` becomes boolean `false`.
- Repeat a flag to send an array.
- Values that look like JSON objects, arrays, numbers, booleans, or `null` are decoded.
- Use `--compact` when another tool will parse the output.

`doctor`, `status`, `explain`, `harvest`, `evaluate-skills`, `recommend`,
`promote-harvest`, `prepare-composition`, `promote-composition-recipe`, `compose-packet`, `runtime-next`, `record-receipt`, and
`review-plan` are the canonical CLI names. Compatibility aliases remain
supported and are frozen in `tmcp_runtime/api/registry.py`; use `list-tools`
for the live MCP schema surface.

## Composition Acceptance Benchmark

Run the release gate only with complete observed host-run evidence:

```bash
python3 scripts/run_composition_benchmark.py path/to/observations.json
```

The command rejects missing cases, fixtures, singleton/leave-one-out controls, provenance, ordering, quality scores, or context measurements. Repository unit fixtures validate scoring math; they do not demonstrate lift. See [COMPOSITION_BENCHMARK.md](COMPOSITION_BENCHMARK.md).

## Fallback Order

1. Exposed MCP tools.
2. Local `node scripts/tmcp_launcher.mjs ...` CLI. Use this when `tool_search` returns no TMCP tools even though TMCP skills are installed.
3. Repo or plugin launcher script discovered relative to the installed skill/plugin root.
4. Explicit AIOS adapter only when `AIOS_ROOT` is configured and requested.
5. Manual packet synthesis using the same output contract.

For Codex discovery issues, run:

```bash
node scripts/tmcp_launcher.mjs doctor --client codex
node scripts/tmcp_launcher.mjs list-tools
```

If those pass but Codex still cannot find `tmcp_explain` or `expert_rubric_review_plan` through `tool_search`, report a Codex MCP discovery gap and continue through CLI-generated JSON/artifacts.

If no launcher is found, clone or copy TMCP, run `node scripts/tmcp_launcher.mjs doctor` from the TMCP root, and set `TMCP_PYTHON` if Python discovery fails.

## Output Contract

Workflow outputs should include or cite:

- sources inspected
- skipped sources and why
- packet summary
- validated composition plan and diagnostics when assisted composition was used
- extracted behavior atoms
- evidence gaps
- recommendation or remediation plan
- verification expectations

AIOS remains optional. `--adapter auto` and `--adapter standalone` keep execution inside this package; use `--adapter aios` only when the caller explicitly opts into the local AIOS adapter. Expert review keeps `adapter=auto` standalone so evidence is not forwarded implicitly. An explicit AIOS review is read-only (`--no-write-artifacts`); durable review artifacts always use the standalone protected store.

Until AIOS supports protected request input, TMCP rejects known sensitive values before an AIOS command can receive them through process arguments. Use the standalone adapter for those requests.
