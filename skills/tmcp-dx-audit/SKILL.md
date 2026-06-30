---
name: tmcp-dx-audit
description: Use TMCP for developer-experience audits of onboarding docs, setup commands, contribution flow, CI clarity, repo navigation, and maintainer handoff readiness.
---

# TMCP Developer Experience Audit

Use this skill when the user asks to review developer onboarding, README quality, setup docs, contribution flow, command discoverability, CI/development ergonomics, repo navigation, or maintainer handoff readiness.

Do not use it for active bug debugging unless the user asks for an audit or remediation plan.

## Workflow

1. Gather evidence from README, install docs, contributing docs, scripts, CI files, project instructions, package metadata, and recent quality-tool output.
2. Invoke TMCP through MCP tools when exposed:
   - `tmcp_explain` for a developer-experience packet.
   - `expert_rubric_review_plan` for a scored audit and remediation plan.
3. If MCP tools are not exposed, use the CLI from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs review-plan "Review developer experience and onboarding for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

4. Treat missing setup or verification evidence as an audit finding.
5. Stop at the plan unless the user explicitly asks for implementation.

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Scored DX/onboarding rubric.
- Evidence-backed findings.
- Ordered remediation plan with verification expectations.
