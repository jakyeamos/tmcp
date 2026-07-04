---
name: tmcp-test-strategy
description: Use TMCP for test strategy audits, regression coverage plans, test value reviews, behavior coverage, and quality-gate remediation.
status: experimental
---

# TMCP Test Strategy

Status: experimental. This workflow remains shipped and callable, but its public contract may change.

Use this skill when the user asks what to test, whether tests are valuable, how to cover regression risk, whether coverage protects behavior, or how to improve a test/quality gate plan.

Do not use it to debug a failing test unless the user asks for a test strategy or regression-risk packet.

## Workflow

1. Gather evidence: public contracts, domain rules, recent bugs, test files, CI checks, coverage reports, and quality-gate requirements.
2. Invoke `tmcp_explain` for the testing packet.
3. Invoke `expert_rubric_review_plan` for a scored test strategy and remediation plan.
4. If MCP tools are unavailable, run from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs review-plan "Review test strategy and regression risk for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Behavior and contract coverage map.
- Regression-risk gaps.
- Low-value or redundant test findings.
- Verification-focused remediation plan.
