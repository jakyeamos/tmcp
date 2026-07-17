# Adaptive Workflow Pack

Use this when you want TMCP to fit a user's, team's, or repo's actual operating style instead of assuming one fixed workflow.

## Flow

1. `tmcp_harvest_skills`
2. `tmcp_recommend_workflows`
3. Select a recommended default workflow or custom workflow idea.
4. Run the selected workflow through `expert_rubric_review_plan` only after approval.

## CLI

```bash
tmcp recommend . \
  --objective "Build an adaptive TMCP workflow pack from this repo's skill signals" \
  --write-artifacts \
  --output-dir .tmcp/adaptive-workflow-pack
```

## Expected Output

- `adaptive_workflow_pack.schema`: `tmcp-adaptive-workflow-pack-v0.1`
- `harvested_source_map`: source paths, source types, scopes, atoms, and keywords.
- `operating_profile`: user/team/repo signal profile and source mix.
- `strongest_behavior_signals`: behavior atoms driving workflow adaptation.
- `recommended_default_templates`: fixed TMCP templates that fit the harvest.
- `generated_custom_workflow_ideas`: source-backed workflow ideas beyond fixed templates.
- `suggested_routing_triggers`: Codex/Claude/AGENTS routing language.
- `documented_process_gaps`: weak or missing process evidence.
- `next_workflow_selection`: approval-gated template or custom workflow selection.

Each item in `recommended_workflows` also separates:

- `template`: the reusable default workflow family.
- `workflow_instance`: the candidate workflow adapted to this harvest, including generated rubric seed, required evidence, routing trigger, and approval gate.
