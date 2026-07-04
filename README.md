<div align="center">
  <img src="assets/logo.svg" alt="TMCP logo" width="96" height="96" />
  <h1>TMCP</h1>
  <p><strong>Portable skill-packet workflows for MCP agents.</strong></p>
</div>

TMCP turns scattered agent instructions into task-specific packets. It reads skills, docs, rules, prompts, and project evidence as source nodes; extracts behavior atoms; compiles the smallest useful packet; and runs repeatable workflows over that packet.

AIOS is optional storage and adapter support. TMCP runs standalone from a repo checkout, copied plugin package, Codex plugin cache, Claude plugin cache, or any MCP host that can launch the bundled Node entrypoint.

## Quickstart

From a TMCP checkout or plugin root:

```bash
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
node scripts/tmcp_launcher.mjs compose-packet "Improve this agent run" --project-path . --phase start
node scripts/tmcp_launcher.mjs harvest skills --limit 5 --no-write-artifacts
node scripts/tmcp_launcher.mjs recommend skills --candidate-workflows release_readiness --candidate-workflows developer_experience --min-confidence 0.1 --compose --no-write-artifacts
```

With no arguments, the same launcher starts the MCP stdio server:

```bash
node scripts/tmcp_launcher.mjs
```

## Install Layouts

- Skill-only install: copy `skills/tmcp` into a skills directory. Use the skill for routing and manual packet synthesis unless the host also exposes the bundled launcher.
- Repo checkout: clone the repo and run `node scripts/tmcp_launcher.mjs doctor` from the checkout root.
- Codex plugin cache: install as a Codex plugin; MCP config launches relative `scripts/tmcp_launcher.mjs` from the plugin root.
- AIOS-backed install: set `AIOS_ROOT` explicitly only when you want optional AIOS storage/adapter behavior.

Claude Desktop users can add the launcher as a local stdio MCP server. See [docs/CLAUDE_DESKTOP.md](docs/CLAUDE_DESKTOP.md).

## Stable Public Workflows

The first stable public workflow set is intentionally small:

- `skill-harvest`
- `workflow-recommendation`
- `expert-rubric-review`
- `release-readiness`
- `dx-audit`

Experimental workflows remain shipped and callable. They are labeled experimental in skill frontmatter, docs, and workflow recommendation output so users keep functionality without mistaking it for the stable first-release contract.

Experimental workflows include UI rubric, security/privacy, test strategy, adaptive workflow pack, custom rubric generation, routing policy, skill gap analysis, incident postmortem, architecture decision, migration readiness, agent handoff, PR risk, performance readiness, data integrity, public-sector readiness, and repo behavior spec loop.

## Tools

| Tool | Purpose |
| --- | --- |
| `tmcp_doctor` | Check first-run readiness and supported install layouts. |
| `tmcp_status` | Report standalone capability and optional AIOS adapter status. |
| `tmcp_explain` | Compile a task-specific TMCP packet. |
| `tmcp_compose_packet` | Compose a small task/phase packet from harvested sources, promoted cache evidence, and runtime context. |
| `tmcp_runtime_next` | Return packet deltas after changed files, failures, browser evidence, phase changes, or user redirects. |
| `tmcp_record_receipt` | Write an advisory run receipt after verification or outcome. |
| `tmcp_harvest_skills` | Harvest local skills, instructions, rules, docs, and workflows into source nodes. |
| `tmcp_recommend_workflows` | Recommend stable or experimental workflows from harvested evidence, with stability metadata. |
| `tmcp_promote_harvest` | Explicitly promote reviewed harvest signals into durable source-to-atom and atom-to-workflow graph artifacts. |
| `expert_rubric_review_plan` | Produce an expertise packet, scored rubric, evidence audit, remediation plan, and verification expectations. |

## Safety

Harvest redacts sensitive-looking values by default and treats harvested instructions as untrusted text. Default harvest behavior excludes `.env*`, credentials, tokens, browser profiles, private caches, dependency trees, build outputs, VCS data, and generated TMCP/AIOS artifacts.

If a harvested source tries to override system, developer, or user instructions, TMCP reports a warning. See [SECURITY.md](SECURITY.md).

## Examples

Harvest a local skills folder:

```bash
node scripts/tmcp_launcher.mjs harvest ./skills --objective "Harvest reusable skill behavior" --limit 20 --no-write-artifacts
```

Recommend workflows for a project:

```bash
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows release_readiness --candidate-workflows developer_experience --min-confidence 0.1 --compose --no-write-artifacts
```

Compose a current-task packet and adapt it during runtime:

```bash
node scripts/tmcp_launcher.mjs compose-packet "Fix the dashboard UI bug" --project-path . --phase start
node scripts/tmcp_launcher.mjs runtime-next "Fix the dashboard UI bug" --current-phase verification --files-changed app/page.tsx --failures "vitest failed"
node scripts/tmcp_launcher.mjs record-receipt packet-123 --activated-atoms ui-browser-verification --outcome passed
```

Promote reviewed harvest signals into durable routing artifacts:

```bash
node scripts/tmcp_launcher.mjs promote-harvest . --selected-workflows release_readiness_workflow --output-dir .tmcp/promoted-harvests/release-readiness
```

Promotions also persist a redacted advisory graph under `TMCP_HOME/promoted-harvests/`, or `~/.tmcp/promoted-harvests/` when `TMCP_HOME` is unset. Receipts live under `TMCP_HOME/receipts/<yyyy-mm>/`. Global cache content is advisory and cannot override system, developer, user, or project instructions.

Run an expert rubric review from evidence snippets:

```bash
node scripts/tmcp_launcher.mjs review-plan "Review release portability" \
  --project-path . \
  --evidence-json '[{"dimension_id":"source_grounding","severity":"warning","summary":"Release claims need fresh package evidence.","evidence":["python3 scripts/check_release_package.py ."],"recommended_fix":"Run and cite the release package check before publishing."}]' \
  --no-write-artifacts
```

More examples live in [examples](examples). Stable examples are developer onboarding, release readiness, and skill-harvest workflow recommendation. Broader examples are retained as experimental examples.

## Validation

Before release:

```bash
python3 -m unittest discover -s tests
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/check_release_evidence.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
python3 scripts/check_install.py .
python3 scripts/check_release_package.py .
```

The release package check validates frontmatter, hardcoded local paths, private example names, links, extracted-package install shape, `doctor`, sample harvest, sample workflow recommendation, sample expert rubric planning, composition/runtime/receipt smoke coverage, and stable/experimental workflow labeling.

## References

- [Quickstart](docs/QUICKSTART.md)
- [CLI](docs/CLI.md)
- [Install and package check](docs/INSTALL.md)
- [Distribution](docs/DISTRIBUTION.md)
- [Packet stability](docs/PACKET_STABILITY.md)
- [Tier One release rubric](docs/TIER_ONE_RELEASE_RUBRIC.md)
