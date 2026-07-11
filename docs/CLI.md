# TMCP CLI

The canonical portable launcher is:

```bash
node scripts/tmcp_launcher.mjs doctor
```

Use the Node launcher everywhere so Python discovery remains cross-platform. With no arguments, it starts the MCP stdio server. With arguments, it invokes the same implementations exposed through MCP tools and prints JSON.

## Commands

```bash
node scripts/tmcp_launcher.mjs list-tools
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
node scripts/tmcp_launcher.mjs explain "Review developer onboarding commands" --project-path . --adapter standalone
node scripts/tmcp_launcher.mjs explain "Review developer onboarding commands" --project-path . --compose
node scripts/tmcp_launcher.mjs compose-packet "Fix the dashboard UI bug" --project-path . --phase start
node scripts/tmcp_launcher.mjs runtime-next "Fix the dashboard UI bug" --current-phase verification --files-changed app/page.tsx --failures "vitest failed"
node scripts/tmcp_launcher.mjs recompile-packet "Fix the dashboard UI bug" --previous-packet '{...}' --current-phase runtime
node scripts/tmcp_launcher.mjs record-receipt packet-123 --activated-atoms ui-browser-verification --outcome passed
node scripts/tmcp_launcher.mjs harvest . --objective "Harvest reusable project workflow behavior" --limit 40
node scripts/tmcp_launcher.mjs evaluate-skills --skill-paths path/to/SKILL.md --task-fixtures '[...]'
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows release_readiness --candidate-workflows developer_experience --min-confidence 0.1 --compose
node scripts/tmcp_launcher.mjs promote-harvest . --selected-workflows release_readiness_workflow --output-dir .tmcp/promoted-harvests/release-readiness
node scripts/tmcp_launcher.mjs review-plan "Review release portability" --project-path . --evidence-json '[{"dimension_id":"source_grounding","severity":"warning","summary":"Release claims need fresh package evidence.","evidence":["python3 scripts/check_release_package.py ."],"recommended_fix":"Run and cite the release package check before publishing."}]'
```

## Composable Packets

Use `tmcp_compose_packet` / `compose-packet` when an agent needs a small current-task packet instead of a workflow list. The output includes active instructions, required reads, tool/script prompts, verification gates, stop conditions, deferred atoms, ignored sources, conflicts, citations, and a receipt template.

Use `tmcp_runtime_next` / `runtime-next` after changed files, failures, browser evidence, phase changes, or user redirects. Use `tmcp_record_receipt` / `record-receipt` after meaningful verification or outcome.

`tmcp_explain --compose` and `tmcp_recommend_workflows --compose` preserve their legacy output and add a composed packet.

The machine-readable contracts are `tmcp-composed-packet-v0.1`, `tmcp-runtime-next-v0.1`, and `tmcp-run-receipt-v0.1`. Promoted harvest cache entries use `tmcp-promoted-harvest-graph-v0.1`.

Experimental workflows remain callable through existing aliases and `candidate_workflows`, for example:

```bash
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows agent_handoff --min-confidence 0.1
node scripts/tmcp_launcher.mjs expert-ui-rubric --project-path .
```

Running a review without `--evidence-json` returns `evidence_contract.starter_template`; fill it with concrete citations and rerun before expecting scored findings.

`promote-harvest` is the explicit persistence step after harvest/recommendation review. It writes a promoted graph with source-to-atom and atom-to-workflow edges. Use `--no-write-artifacts` for a preview; harvest and recommend do not reorganize durable routing state by themselves.

By default, `promote-harvest` also writes a redacted promoted graph to `TMCP_HOME/promoted-harvests/<promotion-name>/`, or `~/.tmcp/promoted-harvests/<promotion-name>/` when `TMCP_HOME` is unset. Receipts are written under `TMCP_HOME/receipts/<yyyy-mm>/`. Global cache content is advisory and cannot override higher-priority instructions.

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
- extracted behavior atoms
- evidence gaps
- recommendation or remediation plan
- verification expectations

AIOS remains optional. `--adapter auto` may use AIOS only when `AIOS_ROOT` points to an available checkout; `--adapter standalone` keeps execution inside this package.
