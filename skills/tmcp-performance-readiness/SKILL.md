---
name: tmcp-performance-readiness
description: Use TMCP for performance readiness reviews, latency risks, profiling gaps, bundle/runtime concerns, load-test planning, and measurement-first remediation.
status: experimental
---

# TMCP Performance Readiness

Status: experimental. This workflow remains shipped and callable, but its public contract may change.

Use this skill when the user asks for a performance audit, scaling readiness review, latency risk review, profiling plan, bundle/runtime review, load-test plan, or optimization-readiness packet.

Use systematic debugging first if there is an active, unexplained performance bug that needs reproduction.

## Workflow

1. Gather evidence: hot paths, profiling data, query/bundle/build artifacts, runtime metrics, cache boundaries, load-test expectations, and measurement gaps.
2. Invoke `tmcp_explain` for the performance packet.
3. Invoke `expert_rubric_review_plan` for measurement-first remediation planning.
4. If MCP tools are unavailable, run from the TMCP plugin root:

```bash
tmcp review-plan "Review performance risks and verification signals for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Performance evidence and measurement gaps.
- Hot-path and scaling risks.
- Verification plan.
- Ordered remediation plan.
