---
name: tmcp-agent-handoff
description: Use TMCP to create agent handoff and continuity packets with current state, decisions, touched files, blockers, open questions, and next commands.
status: experimental
---

# TMCP Agent Handoff

Status: experimental. This workflow remains shipped and callable, but its public contract may change.

Use this skill when the user asks for a handoff, resume packet, continuity note, pause-work summary, next-agent context, or durable state packet.

Do not use it as a generic summary if no future worker needs to act on the output.

## Workflow

1. Gather evidence: current goal, git state, files changed, decisions made, commands run, test results, blockers, open questions, and next actions.
2. Invoke `tmcp_explain` for the handoff packet when available.
3. If a scored audit is needed, invoke `expert_rubric_review_plan` for handoff completeness.
4. If MCP tools are unavailable, run from the TMCP plugin root:

```bash
node scripts/tmcp_launcher.mjs review-plan "Create an agent handoff and continuity packet for <project>" --project-path "<project-path>" --evidence-json '<json>' --write-artifacts
```

## Output Contract

Produce or cite:

- Current-state packet.
- Decisions and constraints.
- Changed/touched surfaces.
- Verification already run.
- Blockers, open questions, and next commands.
