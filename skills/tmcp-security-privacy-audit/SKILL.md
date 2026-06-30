---
name: tmcp-security-privacy-audit
description: Use TMCP for security/privacy process audits, redacted instruction harvests, secret-handling reviews, risk evidence gaps, and remediation planning.
---

# TMCP Security Privacy Audit

Use this skill when the user asks for a security audit, privacy audit, secret-handling review, redacted skill harvest, process-risk audit, safety review, or remediation plan for security/privacy practices.

Do not use it as a substitute for exploit development or invasive testing. Keep evidence redacted by default.

## Workflow

1. Gather evidence from security docs, privacy docs, environment docs, CI config, dependency policy, auth/payment/data-flow docs, agent instructions, and relevant code boundaries.
2. Invoke TMCP through MCP tools when exposed:
   - `tmcp_harvest_skills` for redacted source harvesting.
   - `tmcp_explain` for a security/privacy packet.
   - `expert_rubric_review_plan` for a scored audit and remediation plan.
3. If MCP tools are not exposed, use the CLI from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs review-plan "Review security and privacy readiness for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

4. Preserve redaction summaries and report evidence gaps explicitly.
5. Stop at the plan unless the user explicitly asks for implementation.

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Redaction summary when harvesting.
- Scored security/privacy rubric.
- Evidence-backed findings and gaps.
- Ordered remediation plan with verification expectations.
