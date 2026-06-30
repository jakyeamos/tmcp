---
name: tmcp-routing-policy-generator
description: Use TMCP to generate Codex, Claude, AGENTS, or team routing policies from harvested workflow signals and recommended TMCP workflows.
---

# TMCP Routing Policy Generator

Use this skill when the user asks for routing triggers, agent policy, AGENTS/CLAUDE rules, when-to-use guidance, or workflow selection rules derived from harvested skills.

Do not edit policy files unless the user explicitly asks for implementation.

## Workflow

1. Run `tmcp_harvest_skills` over agent instructions, skills, repo docs, and workflow rules.
2. Run `tmcp_recommend_workflows` to identify supported routing families.
3. Generate routing triggers, negative triggers, fallback CLI instructions, and approval gates.
4. Run `expert_rubric_review_plan` only after the user selects a workflow to turn into an audited policy change.
5. Keep implementation approval-gated.

## Output Contract

Produce or cite:

- Recommended routing triggers.
- Negative routing rules.
- Default workflow templates.
- Custom workflow triggers.
- Tool/CLI fallbacks.
- Policy gaps that need user decisions.
