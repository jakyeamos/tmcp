# TMCP

TMCP is a standalone adaptive skill-packet workflow plugin. It compiles task-specific packets from local instructions and evidence, harvests reusable skill behavior from arbitrary repositories, recommends default and custom workflows from harvested signals, and produces expert rubric remediation plans.

AIOS is optional. When `AIOS_ROOT` points to an AIOS checkout, the plugin can use AIOS for richer graph traversal and persistence. Without AIOS, the MCP server still supports packet compilation, skill harvest, expert rubric planning, and artifact writing.

## Quickstart

Start with [docs/QUICKSTART.md](docs/QUICKSTART.md). The shortest first-run path is:

1. Install TMCP through your client: Codex plugin, Claude Code plugin, Claude Desktop MCP config, or plain MCP stdio command.
2. Run `tmcp_doctor`.
3. Run `tmcp_status`.
4. Run `tmcp_explain` with your objective.
5. Run `tmcp_recommend_workflows` to infer which expert workflows fit your harvested skill signals.
6. Use one of the default workflow templates or generate a custom workflow pack from [examples](examples).

If your MCP host does not expose tools cleanly, use the same surface through the direct CLI:

```bash
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
node scripts/tmcp_launcher.mjs explain "Use the TMCP expert UI rubric on Hoopscout" --project-path .
node scripts/tmcp_launcher.mjs expert-ui-rubric --project-path . --evidence-json '[]'
node scripts/tmcp_launcher.mjs recommend . --write-artifacts
```

See [docs/CLI.md](docs/CLI.md).

## Install

TMCP is packaged for multiple runtimes:

- Codex plugin: install from the Codex plugin store or local personal marketplace.
- Claude Code plugin: install from the GitHub-hosted Claude marketplace once the repository is public.
- Claude Desktop: add TMCP as a local stdio MCP server.
- Plain MCP server: run `node scripts/tmcp_launcher.mjs` from a local checkout.
- Direct CLI: run `node scripts/tmcp_launcher.mjs <command>` from a local checkout.

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md), [docs/MARKETPLACE_MATRIX.md](docs/MARKETPLACE_MATRIX.md), [docs/CLAUDE_CODE.md](docs/CLAUDE_CODE.md), and [docs/CLAUDE_DESKTOP.md](docs/CLAUDE_DESKTOP.md).

## Tools

- `tmcp_doctor`: checks first-run readiness and points each client type at the right install path.
- `tmcp_status`: reports standalone capability and optional AIOS adapter availability.
- `tmcp_explain`: compiles a task-specific TMCP packet.
- `tmcp_harvest_skills`: harvests local skills, agent instructions, editor rules, repository process docs, and workflow docs into source nodes.
- `tmcp_recommend_workflows`: harvests skill sources, infers priority signals, emits an `adaptive_workflow_pack`, and recommends default workflow templates plus custom workflow ideas with evidence.
- `expert_rubric_review_plan`: creates an expertise packet, scored rubric, audit report, remediation plan, and approval-gated implementation handoff.

## Packet Substance

Every compiled packet includes a `substance_check`. This separates broad TMCP process scaffolding from concrete source-backed playbook content.

- `process_only`: TMCP has routing/process guidance, but no useful domain playbook.
- `thin_domain_signals`: TMCP found related terms, but not enough actionable source material.
- `source_backed_playbook`: harvested sources contain concrete task guidance that can shape the rubric.

When a packet is process-only or thin, TMCP should say so and derive rubric substance from the target repo's docs, code, tests, risk registers, and readiness gates.

## Skill Harvest

Harvest is setup-agnostic. It does not assume Codex, Claude, AIOS, or a specific home directory layout.

Default harvest inputs include:

- `SKILL.md`
- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `.cursor/rules`
- `.github`
- `docs`
- `planning`
- `workflows`
- markdown process docs

Default exclusions include dependency, build, cache, VCS, coverage, generated plugin-cache directories, and generated `.aios` / `.tmcp` run artifacts.

Sensitive-looking values are redacted by default before excerpts, frontmatter, keywords, or artifact output are returned. Redaction covers common API keys, bearer tokens, GitHub tokens, AWS access keys, private key blocks, secret assignments, and long high-entropy strings.

## Packet Stability

The current packet schema is `tmcp-skill-packet-v0.2`. The stability policy is documented in [docs/PACKET_STABILITY.md](docs/PACKET_STABILITY.md), and the machine-readable schema lives at [schemas/tmcp-skill-packet-v0.2.schema.json](schemas/tmcp-skill-packet-v0.2.schema.json).

## Adaptive Workflow Model

TMCP treats fixed workflows as default templates, not limits. A skill harvest can reveal a user, team, or repo operating profile, then recommend the right workflow family or a custom workflow-pack direction.

`tmcp_recommend_workflows` now returns a first-class `adaptive_workflow_pack` artifact. The pack includes a harvested source map, operating profile, strongest behavior signals, recommended default templates, generated custom workflow ideas, suggested routing triggers, documented process gaps, and an approval-gated next workflow selection.

Each recommended default workflow separates the reusable `template` from a candidate `workflow_instance`. The template describes the fixed workflow family; the instance adapts that template to the harvested sources with a generated rubric seed, required evidence checklist, routing trigger, and approval gate.

Current default workflow families include UI quality, security/privacy, test strategy, release readiness, developer experience, maintainability, performance, data integrity, incident postmortems, architecture decisions, migration readiness, agent handoff, and PR risk review.

## Example Workflows

TMCP is not limited to UI audits. The repository includes examples for:

- [Adaptive workflow pack](examples/workflows/adaptive-workflow-pack.md)
- [Architecture decision review](examples/workflows/architecture-decision-review.md)
- [Incident postmortem packet](examples/workflows/incident-postmortem-packet.md)
- [Test strategy audit](examples/workflows/test-strategy-audit.md)
- [Migration readiness](examples/workflows/migration-readiness.md)
- [Agent handoff packet](examples/workflows/agent-handoff-packet.md)
- [PR risk review](examples/workflows/pr-risk-review.md)
- [Performance readiness](examples/workflows/performance-readiness.md)
- [Data integrity audit](examples/workflows/data-integrity-audit.md)
- [Developer onboarding audit](examples/workflows/developer-onboarding-audit.md)
- [Security and privacy harvest audit](examples/workflows/security-privacy-harvest-audit.md)
- [Release readiness planning](examples/workflows/release-readiness-planning.md)
- [Skill harvest workflow recommendation](examples/workflows/skill-harvest-workflow-recommendation.md)

## Local Verification

Run the standard-library test suite:

```bash
python3 -m unittest discover -s tests
```

Run a syntax check:

```bash
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
```

Run the install-shape check:

```bash
python3 scripts/check_install.py .
```

Run the release-package check:

```bash
python3 scripts/check_release_package.py .
```

Validate Claude Code packaging:

```bash
claude plugin validate .
```

The MCP entrypoint is `node scripts/tmcp_launcher.mjs`. The launcher selects Python in this order:

- `TMCP_PYTHON`, when explicitly set.
- Windows: `py -3`, then `python`, then `python3`.
- macOS/Linux: `python3`, then `python`.

The launcher also exposes direct commands for debugging, CI, and agents without usable MCP tool discovery:

```bash
node scripts/tmcp_launcher.mjs list-tools
node scripts/tmcp_launcher.mjs harvest . --limit 40
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows agent_handoff
node scripts/tmcp_launcher.mjs expert-ui-rubric --project-path . --evidence-json '[]'
node scripts/tmcp_launcher.mjs review-plan "Review release readiness" --project-path . --evidence-json '[]'
```

## Release Rubric

Tier One release readiness is tracked in [docs/TIER_ONE_RELEASE_RUBRIC.md](docs/TIER_ONE_RELEASE_RUBRIC.md).
