---
name: tmcp-custom-rubric-generator
description: Use TMCP to generate source-backed custom rubrics from harvested skills, rules, docs, workflow prompts, and recurring evidence signals.
status: experimental
---

# TMCP Custom Rubric Generator

Status: experimental. This workflow remains shipped and callable, but its public contract may change.

Use this skill when the user asks to create a rubric from their own docs, turn harvested process into scoring criteria, customize an audit rubric, or convert team standards into review dimensions.

Do not invent rubric substance when the harvest is thin; report the gap and derive only from available evidence.

## Workflow

1. Run `tmcp_harvest_skills` for source-backed behavior.
2. Run `tmcp_recommend_workflows` to identify the nearest default workflow family.
3. Synthesize custom rubric dimensions from recurring behavior atoms, quality gates, output contracts, and source terms.
4. Use `expert_rubric_review_plan` only when applying the selected rubric to a target project.
5. If MCP tools are unavailable, use `tmcp harvest` and `recommend` from the TMCP plugin root.

## Output Contract

Produce or cite:

- Source-backed rubric dimensions.
- Evidence for each dimension.
- Scoring scale and expected artifacts.
- Thin-signal warnings.
- Suggested starter prompt.
