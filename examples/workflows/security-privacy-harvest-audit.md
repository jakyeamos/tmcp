# Security And Privacy Harvest Audit

Use this when skill harvest may touch local rules, secrets, logs, or project docs with sensitive values.

## Objective

Audit security and privacy risks in the harvest output.

## Tool Sequence

1. `tmcp_harvest_skills`
2. `expert_rubric_review_plan`

## Harvest Request

```json
{
  "source_path": ".",
  "objective": "Harvest workflow docs while preserving privacy boundaries",
  "redact_sensitive": true,
  "limit": 40,
  "max_excerpt_chars": 800
}
```

## Review Request

```json
{
  "objective": "Audit security and privacy risks in the harvest output",
  "project_path": ".",
  "evidence_json": "[{\"dimension_id\":\"secret_exposure\",\"severity\":\"warning\",\"summary\":\"Review redaction summary and artifact paths before sharing packet output.\",\"evidence\":[\"tmcp_harvest_skills.redaction_summary\"],\"recommended_fix\":\"Keep redaction enabled and inspect generated artifacts before publication.\"}]",
  "write_artifacts": true
}
```

## Expected Output

- Security/privacy rubric.
- Findings grounded in harvest warnings and redaction counts.
- Clear shareability guidance for packet artifacts.
- Remediation slices for unsafe excerpts, over-broad roots, or missing retention rules.

