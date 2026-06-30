---
name: tmcp-ui-rubric
description: Use TMCP for UI quality audits, expert UI rubrics, visual polish reviews, screenshot-backed interface findings, and ordered UI remediation plans.
---

# TMCP UI Rubric

Use this skill when the user asks for a UI audit, expert UI rubric, visual quality review, product polish review, responsive UI assessment, design-system fit review, or a remediation plan for interface quality.

Prefer this over a generic browser-only review when the user asks to score, judge, audit, prioritize, or plan UI remediation. Do not use it for tiny copy/style edits or immediate implementation unless the user explicitly asks for edits.

## Workflow

1. Gather concrete UI evidence when available: screenshots, browser inspection, relevant components, design rules, accessibility constraints, product context, and known target users.
2. Invoke TMCP through MCP tools when exposed:
   - `tmcp_explain` for the task-specific packet.
   - `expert_rubric_review_plan` for the scored rubric, audit, and remediation plan.
3. If MCP tools are not exposed, use the CLI from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs expert-ui-rubric --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

4. If rendered UI evidence is unavailable, say that explicitly and base findings on source evidence only.
5. Stop at the audit/remediation plan unless the user explicitly approves implementation.

## Output Contract

Produce or cite:

- TMCP expertise packet or `tmcp_explain` output.
- Packet `substance_check`.
- Scored UI rubric.
- Evidence-backed findings or explicit evidence gaps.
- Ordered remediation plan with verification expectations.
