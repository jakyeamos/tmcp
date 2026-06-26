# Developer Onboarding Audit

Use this when a repo may have scattered or stale setup commands.

## Objective

Review developer onboarding commands and CLI docs.

## Tool Sequence

1. `tmcp_doctor`
2. `tmcp_harvest_skills`
3. `expert_rubric_review_plan`

## Harvest Request

```json
{
  "source_path": ".",
  "objective": "Harvest developer onboarding and validation workflow docs",
  "include_globs": [
    "README.md",
    "CONTRIBUTING.md",
    "docs/**/*.md",
    ".github/**/*.md",
    "AGENTS.md",
    "CLAUDE.md"
  ],
  "limit": 30
}
```

## Review Request

```json
{
  "objective": "Review developer onboarding commands and CLI docs",
  "project_path": ".",
  "evidence_json": "[]",
  "write_artifacts": true
}
```

## Expected Output

- Developer-experience rubric.
- Evidence gaps if command docs are missing.
- Remediation slices for setup, validation, and troubleshooting.
- Verification expectations for every command the docs claim.

