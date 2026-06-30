---
name: tmcp-data-integrity-audit
description: Use TMCP for data correctness audits, schema/migration reviews, invariants, pipelines, reconciliation, idempotency, and backfill risk.
---

# TMCP Data Integrity Audit

Use this skill when the user asks about data correctness, schema review, migration safety, invariants, pipelines, ETL, backfills, reconciliation, idempotency, or data-loss risk.

Do not use it for generic performance or UI data-display questions unless correctness is the central risk.

## Workflow

1. Gather evidence: schemas, migrations, data-flow docs, validation rules, import/export jobs, backfills, reconciliation checks, and known edge cases.
2. Invoke `tmcp_explain` for the data-integrity packet.
3. Invoke `expert_rubric_review_plan` for a scored audit and remediation plan.
4. If MCP tools are unavailable, run from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs review-plan "Review data integrity, migrations, and pipeline correctness for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Invariant and schema-risk map.
- Migration/backfill/reconciliation gaps.
- Data-loss and duplication risks.
- Verification-first remediation plan.
