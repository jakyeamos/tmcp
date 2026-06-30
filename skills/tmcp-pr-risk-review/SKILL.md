---
name: tmcp-pr-risk-review
description: Use TMCP for PR risk reviews, changed-surface maps, merge readiness, regression risk, missing tests, and review handoff packets.
---

# TMCP PR Risk Review

Use this skill when the user asks to review a PR, branch, diff, changed contract, merge risk, regression risk, or release risk before merging.

Do not use it as a replacement for normal code review findings; use it to structure evidence, risk, and remediation.

## Workflow

1. Gather evidence: PR metadata, diff summary, touched contracts, test changes, CI status, migration/docs changes, and known release constraints.
2. Invoke `tmcp_explain` for the PR-risk packet.
3. Invoke `expert_rubric_review_plan` for a scored risk and merge-readiness plan.
4. If MCP tools are unavailable, run from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs review-plan "Review PR risk and merge readiness for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

## Output Contract

Produce or cite:

- Changed-surface map.
- Contract and regression risks.
- CI/test/doc evidence gaps.
- Merge blockers and warnings.
- Ordered remediation plan.
