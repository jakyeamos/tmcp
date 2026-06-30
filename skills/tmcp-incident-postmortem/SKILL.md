---
name: tmcp-incident-postmortem
description: Use TMCP for incident reviews, postmortems, outage/regression analysis, causal timelines, contributing factors, and follow-up remediation plans.
---

# TMCP Incident Postmortem

Use this skill when the user asks for an incident review, postmortem, outage analysis, regression analysis, root-cause writeup, failure timeline, or follow-up remediation plan.

Use systematic debugging first when the failure has not been reproduced or isolated. Use TMCP after there is enough evidence to turn the event into a durable packet.

## Workflow

1. Gather evidence: observed impact, timeline, logs, commits, CI output, rollback notes, reproduction notes, affected users/systems, and follow-up constraints.
2. Invoke `tmcp_explain` for the postmortem packet when available.
3. Invoke `expert_rubric_review_plan` for the causal audit and remediation plan.
4. If MCP tools are unavailable, run from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs review-plan "Create an incident postmortem packet for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Incident timeline and evidence gaps.
- Root cause and contributing factors.
- Blast radius and verification gaps.
- Ordered follow-up remediation plan.
