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
node scripts/tmcp_launcher.mjs prepare-composition "<objective>" --project-path "<project-path>"
node scripts/tmcp_launcher.mjs promote-composition-recipe "<recipe-id>" --project-path "<project-path>" --composition-plan '{...}' --receipts '[...]' --explicit-promotion
node scripts/tmcp_launcher.mjs compose-packet "<objective>" --project-path "<project-path>" --phase start --session-id "run-name"
node scripts/tmcp_launcher.mjs recompile-packet "<objective>" --project-path "<project-path>" --current-phase runtime --session-id "run-name"
node scripts/tmcp_launcher.mjs runtime-next "<objective>" --current-phase verification --files-changed "app/page.tsx"
node scripts/tmcp_launcher.mjs record-receipt "<packet-id>" --activated-atoms "ui-browser-verification" --outcome passed
node scripts/tmcp_launcher.mjs explain "<objective>" --project-path "<project-path>" --compose
node scripts/tmcp_launcher.mjs harvest "<source-path>" --objective "Harvest reusable skill behavior"
node scripts/tmcp_launcher.mjs recommend "<source-path>" --objective "Recommend TMCP workflows from harvested skill signals" --compose
node scripts/tmcp_launcher.mjs review-plan "<objective>" --project-path "<project-path>" --evidence-json '<dimension-mapped JSON>'
```

## Composition Commands

- `tmcp_prepare_composition` / `prepare-composition`: return bounded candidate slices, source roles/digests, diagnostics, and a `tmcp-semantic-proposal-v0.1` starter for host reasoning. It is read-only and experimental.
- `tmcp_compose_packet` / `compose-packet`: validate an optional host semantic proposal and compile its additive `tmcp-composition-plan-v0.1`. Without a proposal, preserve the deterministic compatibility path.
- `tmcp_promote_composition_recipe` / `promote-composition-recipe`: explicitly create one reviewed project-local recipe after three verified receipts across two fixtures pass graph, safety, lift, order, and context gates. Loading is always explicit and revalidates current content.
- `tmcp_runtime_next` / `runtime-next`: return packet deltas after changed files, failures, browser evidence, phase changes, or user redirects.
- `tmcp_record_receipt` / `record-receipt`: write an advisory run receipt after verification or outcome.
- `--compose`: add a composed packet to `explain` or `recommend` output without changing their legacy output shape.

`session_id` is an explicit project-local latest-packet record for one serialized
run. Use it on `compose-packet` and on `recompile-packet` (or
`runtime-next --output-mode full`) with the same explicit absolute `project_path`. It
requires secure persistence, cannot replace an existing session or be combined
with `previous_packet`, and has no history or global lookup. Keep the inline
`previous_packet` path for portable full recompiles.

Ordinary hosts run prepare → host proposal → compose internally for substantial tasks; users continue to prompt naturally. The host must cite returned slices for every proposed relationship. TMCP rejects unknown nodes, unsupported edges, cycles, active conflicts, and precedence overrides. The agent—not TMCP—executes the resulting active stage.

MCP hosts pass the proposal object directly. CLI hosts may pass host-produced JSON with `--semantic-proposal '<json>'`; direct compose without that flag remains supported.

`TMCP_HOME` controls the global cache location; if unset, TMCP uses `~/.tmcp`. Composition and runtime routing default to `cache_policy=none`. Use `project` only for explicitly reviewed project-local recipes, or `global` to opt into advisory promoted graphs and receipts. No cache policy enables automatic promotion.

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
