# PR Risk Review

Use this when a PR or branch needs risk-oriented merge readiness beyond normal code review.

## Flow

1. Gather PR metadata, diff summary, touched contracts, test changes, CI status, migrations, and docs changes.
2. `tmcp_explain`
3. `expert_rubric_review_plan`

## CLI

```bash
node scripts/tmcp_launcher.mjs review-plan "Review PR risk and merge readiness" \
  --project-path . \
  --evidence-json '[]' \
  --write-artifacts \
  --output-dir .tmcp/pr-risk-review
```

## Expected Output

- Changed-surface map.
- Contract and regression risks.
- CI/test/doc evidence gaps.
- Merge blockers and warnings.
