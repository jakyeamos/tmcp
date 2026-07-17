---
name: tmcp-workflow-recommendation
description: Use TMCP to recommend the best expert workflow from harvested repo, skill, rule, process, quality, security, DX, testing, release, UI, or data-integrity signals.
status: stable
---

# TMCP Workflow Recommendation

Status: stable as a skill package. The `tmcp_recommend_workflows` MCP tool is experimental, while individual recommended templates carry their own stability labels.

Use this skill when the user asks what workflow to use, where TMCP is strongest, which rubric/audit should apply, how to route a repo through expert workflows, or how to turn harvested skill signals into recommended workflows.

Do not use it when the user has already chosen a workflow and wants immediate execution.

## Workflow

1. Harvest the repo or instruction source set first unless a recent harvest is already available.
2. Invoke TMCP through MCP tools when exposed:
   - `tmcp_recommend_workflows` for priority signals and recommendations.
   - `tmcp_harvest_skills` when the recommendation tool needs source material.
   - `tmcp_promote_harvest` only after the user approves durable routing artifacts.
3. If MCP tools are not exposed, use the CLI from the TMCP plugin root:

```bash
tmcp recommend "<source-path>" --objective "Recommend custom TMCP workflows from harvested skill signals" --write-artifacts
```

4. Recommend only workflows supported by harvested evidence.
5. Name workflows that are not recommended when the distinction matters.
6. Do not imply harvest reorganizes durable routing state by itself. Use promotion to persist reviewed source-to-atom and atom-to-workflow edges.

## Output Contract

Produce or cite:

- Harvest source paths and warnings.
- Redaction summary.
- Primary and secondary priority signals.
- Recommended workflows with evidence.
- Not-recommended workflows when relevant.
- Selected next workflow and whether implementation is approved.
