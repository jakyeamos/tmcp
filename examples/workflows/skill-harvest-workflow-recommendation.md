# Skill Harvest Workflow Recommendation

Use this when you want TMCP to infer which expert workflows fit a user's or repo's harvested skills and instructions.

## Objective

Recommend custom TMCP workflows from harvested skill signals.

## Tool Sequence

1. `tmcp_doctor`
2. `tmcp_recommend_workflows`
3. Run the selected workflow, usually through `expert_rubric_review_plan`

## Recommendation Request

```json
{
  "source_path": ".",
  "objective": "Recommend custom TMCP workflows from this skill corpus",
  "limit": 40,
  "redact_sensitive": true
}
```

## Candidate-Restricted Request

```json
{
  "source_path": ".",
  "candidate_workflows": [
    "security_privacy_review_workflow",
    "developer_experience_workflow"
  ],
  "limit": 40
}
```

## Expected Output

- Harvest summary with redaction and warnings.
- Priority profile with primary, secondary, and weak signals.
- Recommended workflows with confidence, evidence, and starter prompts.
- Not-recommended workflows with reasons.
- Rubric seeds for the selected workflow family.

## Follow-Up

After selecting a workflow, run the starter prompt or call `expert_rubric_review_plan` with the selected objective. Implementation remains approval-gated.
