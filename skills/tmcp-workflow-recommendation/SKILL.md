---
name: tmcp-workflow-recommendation
description: Use TMCP to recommend the best expert workflow from harvested repo, skill, rule, process, quality, security, DX, testing, release, UI, or data-integrity signals.
---

# TMCP Workflow Recommendation

Use this skill when the user asks what workflow to use, where TMCP is strongest, which rubric/audit should apply, how to route a repo through expert workflows, or how to turn harvested skill signals into recommended workflows.

Do not use it when the user has already chosen a workflow and wants immediate execution.

## Workflow

1. Harvest the repo or instruction source set first unless a recent harvest is already available.
2. Invoke TMCP through MCP tools when exposed:
   - `tmcp_recommend_workflows` for priority signals and recommendations.
   - `tmcp_harvest_skills` when the recommendation tool needs source material.
3. If MCP tools are not exposed, use the CLI from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs recommend "<source-path>" --objective "Recommend custom TMCP workflows from harvested skill signals" --write-artifacts
```

4. Recommend only workflows supported by harvested evidence.
5. Name workflows that are not recommended when the distinction matters.

## Output Contract

Produce or cite:

- Harvest source paths and warnings.
- Redaction summary.
- Primary and secondary priority signals.
- Recommended workflows with evidence.
- Not-recommended workflows when relevant.
- Selected next workflow and whether implementation is approved.
