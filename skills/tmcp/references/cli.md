# TMCP CLI

The canonical portable launcher is:

```bash
tmcp doctor --client codex
```

Run it from a TMCP repo checkout, copied plugin root, or installed plugin cache. With no arguments, the same launcher starts the MCP stdio server.

## Common Commands

```bash
tmcp list-tools
tmcp doctor
tmcp status
tmcp compose-packet "<objective>" --project-path "<project-path>" --phase start --session-id "run-name"
tmcp recompile-packet "<objective>" --project-path "<project-path>" --current-phase runtime --session-id "run-name"
tmcp runtime-next "<objective>" --current-phase verification --files-changed "app/page.tsx"
tmcp record-receipt "<packet-id>" --activated-atoms "ui-browser-verification" --outcome passed
tmcp explain "<objective>" --project-path "<project-path>" --compose
tmcp harvest "<source-path>" --objective "Harvest reusable skill behavior"
tmcp recommend "<source-path>" --objective "Recommend TMCP workflows from harvested skill signals" --compose
tmcp review-plan "<objective>" --project-path "<project-path>" --evidence-json '<dimension-mapped JSON>'
```

## Composition Commands

- `tmcp_compose_packet` / `compose-packet`: create a small phase-specific packet from harvested sources, optional explicitly opted-in global cache knowledge, and optional runtime context.
- `tmcp_runtime_next` / `runtime-next`: return packet deltas after changed files, failures, browser evidence, phase changes, or user redirects.
- `tmcp_record_receipt` / `record-receipt`: write an advisory run receipt after verification or outcome.
- `--compose`: add a composed packet to `explain` or `recommend` output without changing their legacy output shape.

`session_id` is an explicit project-local latest-packet record for one serialized
run. Use it on `compose-packet` and on `recompile-packet` (or
`runtime-next --output-mode full`) with the same explicit absolute `project_path`. It
requires secure persistence, cannot replace an existing session or be combined
with `previous_packet`, and has no history or global lookup. Keep the inline
`previous_packet` path for portable full recompiles.

`TMCP_HOME` controls the global cache location; if unset, TMCP uses `~/.tmcp`. Promoted harvest graphs live under `promoted-harvests/`, and receipts live under `receipts/<yyyy-mm>/`. Global cache content is advisory and cannot override higher-priority instructions. Composition and runtime routing default to `cache_policy=none`; pass `--cache-policy global` only to opt in.

## Fallback Order

1. Exposed MCP tools.
2. Local `tmcp ...` CLI. Use this when `tool_search` returns no TMCP tools even though TMCP skills are installed.
3. Repo or plugin launcher script discovered relative to the installed skill/plugin root.
4. Explicit AIOS adapter only when `AIOS_ROOT` is configured and requested.
5. Manual packet synthesis using the same output contract.

Codex discovery diagnostic:

```bash
tmcp doctor --client codex
tmcp list-tools
```

If those commands pass but Codex still cannot find `tmcp_explain` or `expert_rubric_review_plan` through `tool_search`, report a Codex MCP discovery gap and continue through CLI-generated JSON/artifacts.

If no launcher is found, report: clone or copy TMCP, run `tmcp doctor` from the TMCP root, and set `TMCP_PYTHON` if Python discovery fails.

## Install Layouts

- Skill-only install: use the skill text for routing and manual packet synthesis unless the host also exposes the bundled plugin root.
- Repo checkout: run commands from the checkout root.
- Codex plugin cache: run commands from the installed plugin root with `tmcp`; MCP config should use its relative compatibility launcher.
- AIOS-backed install: configure `AIOS_ROOT` explicitly and use `--adapter aios` only when the user wants the adapter.
