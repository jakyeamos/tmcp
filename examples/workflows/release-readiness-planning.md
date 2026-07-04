# Release Readiness Planning

Use this when a plugin, MCP server, or agent workflow needs a release gate instead of an ad hoc checklist.

## Objective

Plan a release readiness roadmap for the plugin.

## Tool Sequence

1. `tmcp_explain`
2. `tmcp_harvest_skills`
3. `expert_rubric_review_plan`

## Packet Request

```json
{
  "objective": "Plan a release readiness roadmap for the plugin",
  "project_path": ".",
  "domain": "release-operations",
  "adapter": "standalone"
}
```

## Review Request

```json
{
  "objective": "Plan a release readiness roadmap for the plugin",
  "project_path": ".",
  "evidence_json": "[{\"dimension_id\":\"risk_priority\",\"severity\":\"warning\",\"summary\":\"A release gate is failing after tests pass.\",\"evidence\":[\"pytest: 162 passed\",\"ruff format --check: failed\"],\"recommended_fix\":\"Fix the failed gate before release.\"},{\"dimension_id\":\"verification_readiness\",\"severity\":\"warning\",\"summary\":\"Release verification is not green.\",\"evidence\":[\"ruff format --check: failed\"],\"recommended_fix\":\"Rerun and cite the full release gate after the fix.\"},{\"dimension_id\":\"scope_control\",\"severity\":\"observation\",\"summary\":\"Review scope is limited to the current working tree and release docs.\",\"evidence\":[\"git status --short\",\"docs/RELEASE_CHECKLIST.md\"],\"recommended_fix\":\"Name any deferred release surfaces explicitly.\"},{\"dimension_id\":\"source_grounding\",\"severity\":\"observation\",\"summary\":\"Release claims cite local commands and docs.\",\"evidence\":[\"pytest output\",\"docs/RELEASE_CHECKLIST.md\"],\"recommended_fix\":\"Keep command outputs attached to the review artifacts.\"}]",
  "write_artifacts": true
}
```

## Expected Output

- Planning packet with context-gathering and evidence-first behavior atoms.
- Explicit release evidence gaps.
- Ordered remediation slices for packaging, docs, compatibility, and verification.
- A handoff that remains approval-gated before implementation.
- `evidence_contract` and `evidence_diagnostics` in the result, so coarse records
  are reported before they become uncited findings.
