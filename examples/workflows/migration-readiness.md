# Migration Readiness

Use this before upgrades, deprecations, large refactors, compatibility work, or cutovers.

## Flow

1. Gather current/target states, affected surfaces, data/backfill needs, rollback path, and validation commands.
2. `tmcp_explain`
3. `expert_rubric_review_plan`

## CLI

```bash
tmcp review-plan "Review migration readiness" \
  --project-path . \
  --write-artifacts \
  --output-dir .tmcp/migration-readiness
```

## Expected Output

- Affected-surface map.
- Compatibility and rollback gaps.
- Ordered migration slices.
- Verification gates.
