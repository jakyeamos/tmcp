---
name: tmcp-release-readiness
description: Use TMCP for release readiness audits, ship/no-ship planning, quality ladder gaps, launch blockers, and ordered release remediation slices.
status: stable
---

# TMCP Release Readiness

Use this skill when the user asks whether a repo, branch, feature, sprint, milestone, or product is ready to ship, merge, release, or hand off. Also use it for quality ladder gap analysis, launch-blocker triage, release-readiness planning, and ordered remediation before implementation.

Do not use it for normal test failures or active debugging unless the user asks for a release rubric or remediation plan.

## Workflow

1. Gather evidence from project instructions, README, CI config, tests, build scripts, release docs, current git status, and recent quality-tool output.
2. Invoke TMCP through MCP tools when exposed:
   - `tmcp_explain` for the release-readiness packet.
   - `expert_rubric_review_plan` for the scored rubric and remediation plan.
3. If MCP tools are not exposed, use the CLI from the TMCP plugin root:

```bash
tmcp review-plan "Review release readiness for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

4. Treat missing evidence as a finding, not as permission to assume readiness.
5. Stop at the plan unless the user explicitly asks for implementation.

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Scored release-readiness rubric.
- Evidence-backed ship blockers, risks, and gaps.
- Ordered remediation slices with verification expectations.
