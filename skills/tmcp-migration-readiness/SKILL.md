---
name: tmcp-migration-readiness
description: Use TMCP for migration plans, upgrade readiness, deprecation cleanup, compatibility audits, rollback plans, and sequenced refactor readiness.
status: experimental
---

# TMCP Migration Readiness

Status: experimental. This workflow remains shipped and callable, but its public contract may change.

Use this skill when the user asks for a migration plan, upgrade readiness review, deprecation cleanup plan, compatibility audit, large refactor sequencing, or rollback/cutover readiness.

Do not use it for small isolated edits that do not need sequencing or rollback thinking.

## Workflow

1. Gather evidence: current and target states, compatibility constraints, affected modules, data/backfill needs, rollout order, rollback path, and validation commands.
2. Invoke `tmcp_explain` for the migration packet.
3. Invoke `expert_rubric_review_plan` for readiness and remediation sequencing.
4. If MCP tools are unavailable, run from the TMCP plugin root:

```bash
tmcp review-plan "Review migration readiness for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Affected-surface map.
- Compatibility and rollback gaps.
- Ordered migration slices.
- Verification and acceptance gates.
