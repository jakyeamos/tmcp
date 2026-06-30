# TMCP Quickstart

TMCP should prove itself in the first five minutes. Start with the path that matches your client, then run the same smoke test everywhere.

## 1. Pick An Install Path

| Client | Use This | Best For |
| --- | --- | --- |
| Codex | Codex plugin store or personal marketplace | Codex skills plus bundled MCP tools |
| Claude Code | `claude plugin marketplace add jakyeamos/tmcp` | Claude Code slash command and plugin MCP tools |
| Claude Desktop | Local stdio MCP config | Desktop chat with local MCP tools |
| Plain MCP client | `node scripts/tmcp_launcher.mjs` | Any MCP host that can launch stdio servers |
| Direct CLI | `node scripts/tmcp_launcher.mjs <command>` | Shell smoke tests, CI, and MCP fallback |

More detail: [DISTRIBUTION.md](DISTRIBUTION.md).

If a host cannot discover MCP tools, use [CLI.md](CLI.md). The command names mirror the MCP tools:

```bash
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
node scripts/tmcp_launcher.mjs explain "Review developer onboarding commands and CLI docs" --project-path .
```

## 2. Run The Doctor

Call the `tmcp_doctor` MCP tool.

Expected result:

```json
{
  "ok": true,
  "schema": "tmcp-doctor-v0.1",
  "smoke_test": {
    "tool": "tmcp_status",
    "expected": "structuredContent.standalone.available == true"
  }
}
```

If Python discovery fails, set `TMCP_PYTHON` to the Python 3.10+ executable path.

## 3. Verify Standalone Mode

Call `tmcp_status`.

Expected result:

- `standalone.available` is `true`.
- `aios_adapter.available` may be `false`; AIOS is optional.

## 4. Compile A Packet

Call `tmcp_explain`:

```json
{
  "objective": "Review developer onboarding commands and CLI docs",
  "project_path": ".",
  "adapter": "standalone"
}
```

Expected result:

- `packet.schema` is `tmcp-skill-packet-v0.2`.
- `packet.selected_nodes` contains the task route and supporting behavior modules.
- `packet.output_contract` states what the agent must preserve.
- `packet.substance_check.level` states whether the packet is `process_only`, `thin_domain_signals`, or `source_backed_playbook`.

## 5. Harvest Local Skills

Call `tmcp_harvest_skills`:

```json
{
  "source_path": ".",
  "objective": "Harvest reusable project workflow behavior",
  "limit": 20
}
```

Expected result:

- `source_nodes` contains local instruction and workflow documents.
- `warnings` names skipped or missing surfaces without failing the run.
- `redaction_summary` reports secret redaction activity.
- `packet_seed` is ready to feed into later TMCP workflows.

## 6. Build An Adaptive Workflow Pack

Call `tmcp_recommend_workflows` when you want TMCP to infer which expert workflows fit a harvested skill corpus. Fixed workflows are default templates; harvested user, team, or repo signals can also shape custom workflow-pack ideas.

```json
{
  "source_path": ".",
  "objective": "Recommend custom TMCP workflows from this project's skill signals",
  "limit": 40
}
```

Expected result:

- `priority_profile.primary_signals` names the strongest coding-quality priorities.
- `recommended_workflows` includes evidence-backed workflow recommendations.
- `starter_prompt` gives the prompt to run the selected workflow.
- weak or absent signals identify skill, routing, or process documentation gaps.

Use one of the examples in [examples/workflows](../examples/workflows):

- [Developer onboarding audit](../examples/workflows/developer-onboarding-audit.md)
- [Security and privacy harvest audit](../examples/workflows/security-privacy-harvest-audit.md)
- [Release readiness planning](../examples/workflows/release-readiness-planning.md)
- [Skill harvest workflow recommendation](../examples/workflows/skill-harvest-workflow-recommendation.md)
- [Adaptive workflow pack](../examples/workflows/adaptive-workflow-pack.md)
- [Incident postmortem packet](../examples/workflows/incident-postmortem-packet.md)
- [Architecture decision review](../examples/workflows/architecture-decision-review.md)
- [Migration readiness](../examples/workflows/migration-readiness.md)
- [Agent handoff packet](../examples/workflows/agent-handoff-packet.md)
- [PR risk review](../examples/workflows/pr-risk-review.md)
- [Performance readiness](../examples/workflows/performance-readiness.md)
- [Data integrity audit](../examples/workflows/data-integrity-audit.md)

CLI equivalent:

```bash
node scripts/tmcp_launcher.mjs recommend . \
  --objective "Build an adaptive TMCP workflow pack from this project's skill signals" \
  --limit 40 \
  --write-artifacts \
  --output-dir .tmcp/workflow-recommendations
```

## 7. Run The Expert Rubric Workflow

For phrases like "TMCP expert UI rubric" or "expert rubric workflow", use `expert_rubric_review_plan` after gathering concrete evidence:

```json
{
  "objective": "Use the TMCP expert UI rubric on Hoopscout",
  "project_path": ".",
  "evidence_json": "[]",
  "write_artifacts": true
}
```

CLI equivalent:

```bash
node scripts/tmcp_launcher.mjs review-plan "Use the TMCP expert UI rubric on Hoopscout" \
  --project-path . \
  --evidence-json '[]' \
  --write-artifacts \
  --output-dir .tmcp/expert-ui-review
```

Short fallback alias for the exact same workflow:

```bash
node scripts/tmcp_launcher.mjs expert-ui-rubric \
  --project-path . \
  --evidence-json '[]' \
  --write-artifacts \
  --output-dir .tmcp/expert-ui-review
```

If MCP tool discovery does not show TMCP tools, use this CLI alias instead of downgrading the request to a generic rendered UI audit.

For non-UI audits, `expert_rubric_review_plan` harvests target project sources by default. If the resulting `substance_check` is `process_only` or `thin_domain_signals`, treat TMCP as the process wrapper and derive the actual rubric from target repo artifacts.
