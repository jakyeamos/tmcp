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

If evidence is not already mapped to rubric dimensions, run the command once
without `--evidence-json`, then use the returned
`evidence_contract.starter_template`. Rerun with records shaped like:

```json
[
  {
    "dimension_id": "source_grounding",
    "severity": "observation",
    "summary": "The recommendation is grounded in the current architecture.",
    "evidence": ["src/example/adapter.py", "docs/architecture.md"],
    "recommended_fix": "Preserve the seam while migrating consumers."
  }
]
```

Generic `{ "kind": "checks", "pytest": "..." }` records are diagnostics,
not scored evidence. Do not treat fallback scores as findings; rerun after the
`evidence_json_actionable` validation passes and
`evidence_diagnostics.missing_dimensions` is empty.

## Expected Output

- Decision context.
- Alternatives and tradeoffs.
- Evidence gaps.
- Recommended ADR outcome.
