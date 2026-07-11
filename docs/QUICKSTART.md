# TMCP Quickstart

TMCP should prove itself without personal paths or an AIOS setup. The canonical command is:

```bash
node scripts/tmcp_launcher.mjs doctor
```

Run it from the TMCP repo checkout, copied plugin root, or installed plugin cache.

## 1. Pick An Install Layout

| Layout | How It Works |
| --- | --- |
| Skill-only install | Copy `skills/tmcp`; use manual packet synthesis unless a launcher is also available. |
| Repo checkout | Run `node scripts/tmcp_launcher.mjs ...` from the checkout root. |
| Codex plugin cache | MCP config launches relative `scripts/tmcp_launcher.mjs` from the plugin root. |
| AIOS-backed install | Set `AIOS_ROOT` explicitly only when optional adapter behavior is wanted. |
| Plain MCP client | Configure command `node`, args `["scripts/tmcp_launcher.mjs"]`, and cwd as the TMCP root. |

## 2. Run Doctor And Status

```bash
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
```

Expected:

- standalone mode is available
- Python discovery passes, or the result says to set `TMCP_PYTHON`
- AIOS may be unconfigured; that is not a failure

## 3. Harvest Local Skills

```bash
node scripts/tmcp_launcher.mjs harvest ./skills \
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
node scripts/tmcp_launcher.mjs compose-packet \
  "Redesign these pages. Make them visually striking, interactive, modern, motion-rich, and production-ready." \
  --project-path . \
  --phase start
```

Expected:

- `task_identity.primary` describes the real work
- `packet_markdown` is a readable operating contract
- `compiled_from` and `shortcut_candidate` include provenance
- `evidence_citations` lists selected skill sources; `ignored_sources` explains skips

Recompile after runtime evidence changes:

```bash
node scripts/tmcp_launcher.mjs recompile-packet \
  "Redesign these pages..." \
  --current-phase runtime \
  --previous-packet '<paste prior compose JSON>' \
  --files-changed app/page.tsx
```

Expected:

- schema is `tmcp-recompiled-packet-v0.1`
- `packet_diff` lists dropped/added routes, skills, or atoms
- `packet.packet_markdown` includes a Recompile section

Record a receipt after verification:

```bash
node scripts/tmcp_launcher.mjs record-receipt packet-abc123 \
  --activated-atoms ui-browser-verification \
  --outcome passed
```

Reference seed template: [examples/seeds/frontend-redesign-runtime.json](../examples/seeds/frontend-redesign-runtime.json)

## 5. Recommend Stable Workflows

```bash
node scripts/tmcp_launcher.mjs recommend ./skills \
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
node scripts/tmcp_launcher.mjs review-plan "Review release portability" \
  --project-path . \
  --evidence-json '[{"dimension_id":"source_grounding","severity":"warning","summary":"Release claims need fresh package evidence.","evidence":["python3 scripts/check_release_package.py ."],"recommended_fix":"Run and cite the release package check before publishing."}]' \
  --no-write-artifacts
```

If evidence is not ready, omit `--evidence-json`. The result returns `evidence_contract.starter_template`; fill it with concrete citations and rerun.

## Stable Public Workflows

- `skill-harvest`
- `workflow-recommendation`
- `expert-rubric-review`
- `release-readiness`
- `dx-audit`

## Experimental Workflows

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
