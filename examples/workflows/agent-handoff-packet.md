# Agent Handoff Packet

Use this when work needs to pause or move to another agent or thread.

## Flow

1. Gather goal, git state, changed files, decisions, commands, test results, blockers, and open questions.
2. `tmcp_explain`
3. `expert_rubric_review_plan` only if handoff completeness needs a scored audit.

## CLI

```bash
node scripts/tmcp_launcher.mjs review-plan "Create an agent handoff and continuity packet" \
  --project-path . \
  --evidence-json '[]' \
  --write-artifacts \
  --output-dir .tmcp/agent-handoff
```

## Expected Output

- Current-state packet.
- Decisions and constraints.
- Verification already run.
- Blockers, open questions, and next commands.
