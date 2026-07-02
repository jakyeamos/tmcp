# TMCP CLI

The primary TMCP interface is MCP tools. The same implementation is also available through a direct CLI for agents, humans, CI smoke tests, and MCP clients that make stdio debugging hard.

Use the Node launcher everywhere so Python discovery stays cross-platform:

```bash
node scripts/tmcp_launcher.mjs --help
```

With no arguments, the launcher starts the MCP stdio server. With arguments, it calls a TMCP tool directly and prints JSON.

## Commands

```bash
node scripts/tmcp_launcher.mjs list-tools
node scripts/tmcp_launcher.mjs doctor --client codex
node scripts/tmcp_launcher.mjs status
node scripts/tmcp_launcher.mjs explain "Review developer onboarding commands" --project-path . --adapter standalone
node scripts/tmcp_launcher.mjs harvest . --objective "Harvest reusable project workflow behavior" --limit 40
node scripts/tmcp_launcher.mjs recommend . --objective "Build an adaptive TMCP workflow pack from this project's skill signals" --limit 40
node scripts/tmcp_launcher.mjs review-plan "Use the TMCP expert UI rubric on Hoopscout" --project-path . --evidence-json '[]'
node scripts/tmcp_launcher.mjs expert-ui-rubric --project-path . --evidence-json '[]'
```

## Argument Rules

- CLI command names map to MCP tools.
- Kebab-case flags map to snake_case tool arguments, so `--project-path` becomes `project_path`.
- Flags without values become boolean `true`.
- `--no-<flag>` becomes boolean `false`.
- Repeat a flag to send an array.
- Values that look like JSON objects, arrays, numbers, booleans, or `null` are decoded.
- Use `--compact` when another tool will parse the output.

Examples:

```bash
node scripts/tmcp_launcher.mjs harvest . \
  --include-globs "**/SKILL.md" \
  --include-globs "**/AGENTS.md" \
  --exclude-globs "**/node_modules/**" \
  --write-artifacts \
  --output-dir .tmcp/harvest
```

```bash
node scripts/tmcp_launcher.mjs recommend . \
  --candidate-workflows ui_quality \
  --candidate-workflows security_privacy \
  --candidate-workflows agent_handoff \
  --min-confidence 0.3 \
  --write-artifacts \
  --output-dir .tmcp/workflow-recommendations
```

```bash
node scripts/tmcp_launcher.mjs review-plan "Review release readiness for this repo" \
  --project-path . \
  --evidence-json '[{"dimension_id":"risk_priority","severity":"warning","summary":"A release gate is failing after tests pass.","evidence":["pytest: 162 passed","ruff format --check: failed"],"recommended_fix":"Fix the failed gate before release."},{"dimension_id":"verification_readiness","severity":"warning","summary":"Release verification is not green.","evidence":["ruff format --check: failed"],"recommended_fix":"Rerun and cite the full release gate after the fix."},{"dimension_id":"scope_control","severity":"observation","summary":"Review scope is limited to the current working tree and release docs.","evidence":["git status --short","docs/RELEASE_CHECKLIST.md"],"recommended_fix":"Name any deferred release surfaces explicitly."},{"dimension_id":"source_grounding","severity":"observation","summary":"Release claims cite local commands and docs.","evidence":["pytest output","docs/RELEASE_CHECKLIST.md"],"recommended_fix":"Keep command outputs attached to the review artifacts."}]' \
  --write-artifacts \
  --output-dir .tmcp/release-review
```

`evidence_json` accepts any JSON object or array, but only dimension-mapped
records produce scored, cited findings. Each actionable item should include:
`dimension_id`, `severity`, `summary`, non-empty `evidence`, and optional
`recommended_fix`. Generic records such as `{"kind":"checks","pytest":"passed"}`
are reported in `evidence_diagnostics` until mapped to rubric dimensions.

## Agent Routing

Use MCP tools when your host exposes them. Use the CLI when:

- the MCP plugin is installed but tool discovery failed;
- you need a deterministic local smoke test;
- you are writing CI or release checks;
- you are debugging a copied plugin bundle;
- you need to create artifacts from a non-MCP shell.

For expert rubric work, the expected sequence is:

1. `doctor`
2. `status`
3. `explain`
4. gather concrete evidence
5. `review-plan`
6. ask for approval before implementation

For the common prompt "use the TMCP expert UI rubric workflow", the direct fallback command is:

```bash
node scripts/tmcp_launcher.mjs expert-ui-rubric \
  --project-path . \
  --evidence-json '[]' \
  --write-artifacts \
  --output-dir .tmcp/expert-ui-review
```

This command is intentionally equivalent to `expert_rubric_review_plan` with the objective `Use the TMCP expert UI rubric on this project.` Use it when MCP tool discovery fails or when another agent host says TMCP is not exposed as a callable tool.

For adaptive workflow-pack recommendation, the expected sequence is:

1. `harvest`
2. inspect warnings and redaction summary
3. `recommend`
4. inspect `adaptive_workflow_pack`, `custom_workflow_ideas`, and each recommendation's `template` / `workflow_instance`
5. identify recommended default workflows, custom workflow ideas, routing triggers, and documented process gaps
6. run the workflow selected by the user

AIOS remains optional. `--adapter auto` may use AIOS when `AIOS_ROOT` points to an available checkout; `--adapter standalone` keeps execution inside this plugin.
