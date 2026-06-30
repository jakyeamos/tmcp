# Adaptive Workflow Pack

Use this when you want TMCP to fit a user's, team's, or repo's actual operating style instead of assuming one fixed workflow.

## Flow

1. `tmcp_harvest_skills`
2. `tmcp_recommend_workflows`
3. Select a recommended default workflow or custom workflow idea.
4. Run the selected workflow through `expert_rubric_review_plan` only after approval.

## CLI

```bash
node scripts/tmcp_launcher.mjs recommend . \
  --objective "Build an adaptive TMCP workflow pack from this repo's skill signals" \
  --write-artifacts \
  --output-dir .tmcp/adaptive-workflow-pack
```

## Expected Output

- Harvested source map.
- User/team/repo operating profile.
- Strongest behavior signals.
- Recommended default workflows.
- Custom workflow ideas.
- Suggested Codex/Claude/AGENTS routing triggers.
- Documented process gaps.
- Approval-gated next workflow selection.
