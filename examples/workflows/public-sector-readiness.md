# Public Sector Readiness Review

Use this when a government-facing product needs readiness evidence across policy, compliance, UAT, accessibility, auditability, and launch gates. A public deadline calculator is a representative case because incorrect legal calculations, missing audit trails, or inaccessible public workflows can become release blockers.

## Objective

Review public-sector readiness for a public deadline calculator.

## Tool Sequence

1. `tmcp_recommend_workflows`
2. `expert_rubric_review_plan`

## Recommendation Request

```json
{
  "source_path": ".",
  "objective": "Recommend workflows for a government compliance, UAT, and accessibility launch gate",
  "candidate_workflows": ["public_sector_readiness"],
  "limit": 40
}
```

## Review Request

```json
{
  "objective": "Use TMCP to review public-sector readiness for a public deadline calculator",
  "project_path": ".",
  "evidence_json": "[{\"dimension_id\":\"legal_calculation_safety\",\"severity\":\"warning\",\"summary\":\"Deadline rules need source-backed fixtures before launch.\",\"evidence\":[\"docs/calculation-rules.md\",\"tests/fixtures/deadline-cases.json\"],\"recommended_fix\":\"Tie each high-risk court-clock rule to a cited authority, fixture, and UAT acceptance case.\"}]",
  "write_artifacts": true
}
```

## Expected Output

- Public-sector readiness rubric using the `public_sector_readiness` profile.
- Findings grounded in policy, compliance, UAT, accessibility, auditability, and release-blocker evidence.
- Legal calculation safety gaps for ambiguous rules, missing fixtures, or uncited assumptions.
- Ordered remediation slices that keep implementation approval-gated.
