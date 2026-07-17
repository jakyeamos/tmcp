# TMCP Quickstart

TMCP should prove itself without personal paths or an AIOS setup. The canonical command is the package-root executable:

```bash
tmcp doctor
```

Run it from the TMCP repo checkout, copied plugin root, or installed plugin cache. Use `./tmcp` when the package root is not on `PATH`.

## 1. Pick An Install Layout

| Layout | How It Works |
| --- | --- |
| Skill-only install | Copy `skills/tmcp`; use manual packet synthesis unless a launcher is also available. |
| Repo checkout | Run `tmcp ...` from the checkout root. |
| Codex plugin cache | Human-facing commands use `tmcp`; MCP config retains its relative compatibility launcher. |
| AIOS-backed install | Set `AIOS_ROOT` explicitly only when optional adapter behavior is wanted. |
| Plain MCP client | Configure a stdio MCP entry with the TMCP root as its working directory. |

## 2. Run Doctor And Status

```bash
tmcp --help
tmcp --version
tmcp doctor
tmcp status
```

Expected:

- standalone mode is available
- Python discovery passes, or the result says to set `TMCP_PYTHON`
- AIOS may be unconfigured; that is not a failure
- artifact persistence is either available or explicitly marked limited

To inspect a task without selecting an experimental workflow, use `explain`:

```bash
tmcp explain "Review this agent run" --project-path . --adapter standalone
```

## 3. Harvest Local Skills

```bash
tmcp harvest ./skills \
  --objective "Harvest reusable skill behavior" \
  --limit 20 \
  --no-write-artifacts
```

Expected:

- `source_nodes` contains harvested files
- `redaction_summary` is present
- `warnings` includes skipped sources or instruction override warnings when relevant
- `safety.harvested_text_trust` is `untrusted`

## 4. Compile An Adaptive Operating Packet

Natural-language objective at intake:

```bash
tmcp compose-packet \
  "Redesign these pages. Make them visually striking, interactive, modern, motion-rich, and production-ready." \
  --project-path "$PWD" \
  --phase start
```

Expected:

- `task_identity.primary` describes the real work
- `packet_markdown` is a readable operating contract
- `compiled_from` and `shortcut_candidate` include provenance
- `evidence_citations` lists selected skill sources; `ignored_sources` explains skips

To let TMCP retain the latest packet for one explicit, serialized run, first
confirm that `status` reports secure artifact persistence. Then give both calls
the same project path and session identifier:

```bash
tmcp compose-packet \
  "Redesign these pages. Make them visually striking, interactive, modern, motion-rich, and production-ready." \
  --project-path "$PWD" \
  --phase start \
  --session-id redesign-run

tmcp recompile-packet \
  "Redesign these pages..." \
  --project-path "$PWD" \
  --current-phase runtime \
  --session-id redesign-run \
  --files-changed app/page.tsx
```

Recompile after runtime evidence changes without persistence by using the
compatible inline-packet path:

```bash
tmcp recompile-packet \
  "Redesign these pages..." \
  --current-phase runtime \
  --previous-packet '<paste prior compose JSON>' \
  --files-changed app/page.tsx
```

Expected:

- schema is `tmcp-recompiled-packet-v0.1`
- `packet_diff` lists dropped/added routes, skills, or atoms
- `packet.packet_markdown` includes a Recompile section

Sessions write only a redacted latest-packet record under the explicit project;
they do not create history, discover runs globally, or coordinate concurrent
agents. See [CLI](CLI.md#packet-sessions) for the operational boundary.

Record a receipt after verification only when `status` reports artifact
persistence available:

```bash
tmcp record-receipt packet-abc123 \
  --activated-atoms ui-browser-verification \
  --outcome passed
```

Reference seed template: [examples/seeds/frontend-redesign-runtime.json](../examples/seeds/frontend-redesign-runtime.json)

## 5. Recommend Curated Workflows

```bash
tmcp recommend ./skills \
  --candidate-workflows release_readiness \
  --candidate-workflows developer_experience \
  --min-confidence 0.1 \
  --no-write-artifacts
```

Expected:

- recommended workflows include `stability`
- stable workflows are labeled `stable`
- experimental workflows remain callable when explicitly requested with `candidate_workflows`
- recommendations cite harvested evidence

## 6. Run Expert Rubric Review

```bash
tmcp review-plan "Review release portability" \
  --project-path . \
  --evidence-json '[{"dimension_id":"source_grounding","severity":"warning","summary":"Release claims need fresh package evidence.","evidence":["python3 scripts/check_release_package.py ."],"recommended_fix":"Run and cite the release package check before publishing."}]' \
  --no-write-artifacts
```

If evidence is not ready, omit `--evidence-json`. The result returns `evidence_contract.starter_template`; fill it with concrete citations and rerun.

## Stability Scopes

- Stable skill packages: `tmcp`, `skill-harvest`, `workflow-recommendation`, `release-readiness`, and `dx-audit`.
- Stable curated workflow templates: `release-readiness` and `dx-audit`.
- Stable MCP tool contracts: `doctor`, `status`, `explain`, `compose-packet`, and `runtime-next`; harvest, evaluation, recommendation, promotion, receipt, and expert-rubric tools are experimental.

## Experimental Curated Workflows

Experimental workflows remain shipped, callable, documented, and tested where existing coverage applies. Their public contract may change.

- UI rubric
- Security/privacy audit
- Test strategy
- Adaptive workflow pack
- Custom rubric generation
- Routing policy generation
- Skill gap analysis
- Incident postmortem
- Architecture decision
- Migration readiness
- Agent handoff
- PR risk review
- Performance readiness
- Data integrity audit
- Public-sector readiness

Use [../examples](../examples) for stable and experimental examples.
