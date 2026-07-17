# Incident Postmortem Packet

Use this after a failure has enough evidence to turn debugging results into durable learning.

## Flow

1. Gather impact, timeline, logs, commits, CI output, rollback notes, and reproduction evidence.
2. `tmcp_explain`
3. `expert_rubric_review_plan`

## CLI

```bash
tmcp review-plan "Create an incident postmortem packet" \
  --project-path . \
  --write-artifacts \
  --output-dir .tmcp/incident-postmortem
```

## Expected Output

- Timeline.
- Root cause and contributing factors.
- Blast radius.
- Follow-up remediation plan.
