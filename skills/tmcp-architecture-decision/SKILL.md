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
tmcp review-plan "Review this architecture decision for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Decision context and constraints.
- Alternatives considered.
- Tradeoff and migration-cost audit.
- Recommended ADR outcome.
