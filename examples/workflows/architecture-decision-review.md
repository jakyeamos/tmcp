# Architecture Decision Review

Use this when a project needs an ADR-style decision packet before implementation.

## Flow

1. Gather current architecture, constraints, alternatives, compatibility concerns, and migration cost.
2. `tmcp_explain`
3. `expert_rubric_review_plan`

## CLI

```bash
node scripts/tmcp_launcher.mjs review-plan "Review this architecture decision" \
  --project-path . \
  --write-artifacts \
  --output-dir .tmcp/architecture-decision
```

## Expected Output

- Decision context.
- Alternatives and tradeoffs.
- Evidence gaps.
- Recommended ADR outcome.
