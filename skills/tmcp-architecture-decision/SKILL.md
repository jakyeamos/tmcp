---
name: tmcp-architecture-decision
description: Use TMCP for architecture reviews, ADRs, design decisions, tradeoff analysis, alternatives, constraints, and recommendation packets.
status: experimental
---

# TMCP Architecture Decision

Status: experimental. This workflow remains shipped and callable, but its public contract may change.

Use this skill when the user asks whether to use an architecture, library, platform, design pattern, boundary, or migration approach, or when they ask for an ADR/design-decision review.

Do not use it for immediate implementation unless the user has already approved the decision.

## Workflow

1. Gather evidence: current architecture, constraints, repo patterns, alternatives, migration cost, compatibility concerns, and verification expectations.
2. Invoke `tmcp_explain` for the decision-specific packet.
3. Invoke `expert_rubric_review_plan` to score source grounding, risk priority, verification readiness, and scope control.
4. If MCP tools are unavailable, run from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs review-plan "Review this architecture decision for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

### Evidence preflight

The `--evidence-json` value must be a JSON object or array whose actionable
items are mapped to the rubric. Every item requires:

- `dimension_id`: exact rubric dimension ID
- `severity`: `blocker`, `warning`, or `observation`
- `summary`: concise finding or evidence-gap statement
- `evidence`: non-empty concrete citations
- `recommended_fix`: optional remediation

Do not pass generic records such as `{ "kind": "checks", "pytest": "..." }`
as if they were findings. If the evidence is not mapped, run the command once
without `--evidence-json`, fill `evidence_contract.starter_template`, then
rerun with records like:

```json
[
  {
    "dimension_id": "source_grounding",
    "severity": "observation",
    "summary": "The recommendation is grounded in the current architecture.",
    "evidence": [
      "src/example/adapter.py: current adapter seam",
      "docs/architecture.md: stated compatibility constraint"
    ],
    "recommended_fix": "Preserve the seam while migrating consumers."
  }
]
```

For the standard architecture review, provide at least one item for each of
`source_grounding`, `risk_priority`, `verification_readiness`, and
`scope_control`. Check `evidence_diagnostics.missing_dimensions`; an
`actionable: true` result only validates item shape, not complete coverage.

Do not interpret fallback scores as findings. Continue only when the result
reports actionable evidence; `invalid_evidence_json`, `missing_evidence`, or a
false `evidence_json_actionable` validation means the review must be rerun.

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Decision context and constraints.
- Alternatives considered.
- Tradeoff and migration-cost audit.
- Recommended ADR outcome.
