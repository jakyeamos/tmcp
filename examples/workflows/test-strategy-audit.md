# Test Strategy Audit

Use this when a repo needs behavior-focused test strategy instead of low-value coverage chasing.

## Flow

1. Gather public contracts, domain rules, recent bugs, test files, CI checks, and coverage evidence.
2. `tmcp_explain`
3. `expert_rubric_review_plan`

## CLI

```bash
node scripts/tmcp_launcher.mjs review-plan "Review test strategy and regression risk" \
  --project-path . \
  --write-artifacts \
  --output-dir .tmcp/test-strategy
```

## Expected Output

- Behavior and contract coverage map.
- Regression gaps.
- Low-value or redundant test findings.
- Verification-focused remediation plan.
