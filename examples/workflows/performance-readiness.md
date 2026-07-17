# Performance Readiness

Use this when optimization work needs measurement-first planning.

## Flow

1. Gather hot paths, profiling data, query/bundle/build artifacts, runtime metrics, cache boundaries, and load-test expectations.
2. `tmcp_explain`
3. `expert_rubric_review_plan`

## CLI

```bash
tmcp review-plan "Review performance risks and verification signals" \
  --project-path . \
  --write-artifacts \
  --output-dir .tmcp/performance-readiness
```

## Expected Output

- Performance evidence map.
- Measurement gaps.
- Hot-path and scaling risks.
- Measurement-first remediation plan.
