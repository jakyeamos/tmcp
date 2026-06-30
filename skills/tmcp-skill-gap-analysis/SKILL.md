---
name: tmcp-skill-gap-analysis
description: Use TMCP to identify missing process docs, weak skill signals, undocumented quality gates, and workflow gaps from a skill harvest.
---

# TMCP Skill Gap Analysis

Use this skill when the user asks what their skill corpus is missing, where process docs are weak, which workflows lack evidence, or how to improve agent/team operating instructions.

This is a harvest-first diagnostic, not an implementation workflow.

## Workflow

1. Run `tmcp_harvest_skills` over the source set.
2. Run `tmcp_recommend_workflows` and inspect weak/not-recommended signals.
3. Compare strong/weak signals against intended workflows.
4. Recommend missing docs, skills, routing rules, or validation artifacts.
5. Run `expert_rubric_review_plan` only after the user selects a specific gap or workflow for scored remediation.

## Output Contract

Produce or cite:

- Harvested source map.
- Strong, secondary, weak, and absent workflow signals.
- Missing process documentation.
- Recommended skill/router additions.
- Verification or quality-gate gaps.
- Prioritized next documentation improvements.
