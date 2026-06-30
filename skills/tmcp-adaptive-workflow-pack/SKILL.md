---
name: tmcp-adaptive-workflow-pack
description: Use TMCP to harvest a user/team/repo skill corpus, infer operating priorities, recommend default workflows, and propose custom workflow-pack outputs.
---

# TMCP Adaptive Workflow Pack

Use this skill when the user asks to make TMCP fit a repo/team/user, build a workflow pack, harvest operating style, infer custom workflows, or adapt agent behavior from local skills and process docs.

This is TMCP's broad adaptive workflow. It treats fixed workflows as templates, not limits.

## Workflow

1. Run `tmcp_harvest_skills` over the smallest useful source set.
2. Run `tmcp_recommend_workflows` to infer priority signals and recommended default workflows.
3. Derive custom workflow ideas from harvested behavior atoms, recurring terms, source tiers, and evidence gaps.
4. Run `expert_rubric_review_plan` only after the user selects a specific workflow to audit or execute.
5. If MCP tools are unavailable, run from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs recommend "<source-path>" --objective "Build an adaptive TMCP workflow pack from harvested skill signals" --write-artifacts
```

## Output Contract

Produce or cite:

- Harvested source map.
- User/team/repo operating profile.
- Strongest behavior signals.
- Recommended default workflows.
- Custom workflow ideas.
- Suggested Codex/Claude/AGENTS routing triggers.
- Documented process gaps.
- Approval-gated next workflow selection.
