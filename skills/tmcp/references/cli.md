# TMCP CLI

The canonical portable launcher is:

```bash
node scripts/tmcp_launcher.mjs doctor --client codex
```

Run it from a TMCP repo checkout, copied plugin root, or installed plugin cache. With no arguments, the same launcher starts the MCP stdio server.

## Common Commands

```bash
node scripts/tmcp_launcher.mjs list-tools
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
node scripts/tmcp_launcher.mjs compose-packet "<objective>" --project-path "<project-path>" --phase start
node scripts/tmcp_launcher.mjs runtime-next "<objective>" --current-phase verification --files-changed "app/page.tsx"
node scripts/tmcp_launcher.mjs record-receipt "<packet-id>" --activated-atoms "ui-browser-verification" --outcome passed
node scripts/tmcp_launcher.mjs explain "<objective>" --project-path "<project-path>" --compose
node scripts/tmcp_launcher.mjs harvest "<source-path>" --objective "Harvest reusable skill behavior"
node scripts/tmcp_launcher.mjs recommend "<source-path>" --objective "Recommend TMCP workflows from harvested skill signals" --compose
node scripts/tmcp_launcher.mjs review-plan "<objective>" --project-path "<project-path>" --evidence-json '<dimension-mapped JSON>'
```

## Composition Commands

- `tmcp_compose_packet` / `compose-packet`: create a small phase-specific packet from harvested sources, promoted global cache knowledge, and optional runtime context.
- `tmcp_runtime_next` / `runtime-next`: return packet deltas after changed files, failures, browser evidence, phase changes, or user redirects.
- `tmcp_record_receipt` / `record-receipt`: write an advisory run receipt after verification or outcome.
- `--compose`: add a composed packet to `explain` or `recommend` output without changing their legacy output shape.

`TMCP_HOME` controls the global cache location; if unset, TMCP uses `~/.tmcp`. Promoted harvest graphs live under `promoted-harvests/`, and receipts live under `receipts/<yyyy-mm>/`. Global cache content is advisory and cannot override higher-priority instructions.

## Fallback Order

1. Exposed MCP tools.
2. Local `node scripts/tmcp_launcher.mjs ...` CLI. Use this when `tool_search` returns no TMCP tools even though TMCP skills are installed.
3. Repo or plugin launcher script discovered relative to the installed skill/plugin root.
4. Explicit AIOS adapter only when `AIOS_ROOT` is configured and requested.
5. Manual packet synthesis using the same output contract.

Codex discovery diagnostic:

```bash
node scripts/tmcp_launcher.mjs doctor --client codex
node scripts/tmcp_launcher.mjs list-tools
```

If those commands pass but Codex still cannot find `tmcp_explain` or `expert_rubric_review_plan` through `tool_search`, report a Codex MCP discovery gap and continue through CLI-generated JSON/artifacts.

If no launcher is found, report: clone or copy TMCP, run `node scripts/tmcp_launcher.mjs doctor` from the TMCP root, and set `TMCP_PYTHON` if Python discovery fails.

## Install Layouts

- Skill-only install: use the skill text for routing and manual packet synthesis unless the host also exposes the bundled plugin root.
- Repo checkout: run commands from the checkout root.
- Codex plugin cache: run commands from the installed plugin root; MCP config should use relative `scripts/tmcp_launcher.mjs`.
- AIOS-backed install: configure `AIOS_ROOT` explicitly and use `--adapter aios` only when the user wants the adapter.
