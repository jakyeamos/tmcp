# Data Integrity Audit

Use this when correctness depends on schemas, migrations, pipelines, invariants, reconciliation, or backfills.

## Flow

1. Gather schemas, migrations, data-flow docs, validation rules, jobs, backfills, and reconciliation checks.
2. `tmcp_explain`
3. `expert_rubric_review_plan`

## CLI

```bash
node scripts/tmcp_launcher.mjs review-plan "Review data integrity, migrations, and pipeline correctness" \
  --project-path . \
  --evidence-json '[]' \
  --write-artifacts \
  --output-dir .tmcp/data-integrity
```

## Expected Output

- Invariant and schema-risk map.
- Migration/backfill/reconciliation gaps.
- Data-loss and duplication risks.
- Verification-first remediation plan.
