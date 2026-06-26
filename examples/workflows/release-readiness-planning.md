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
  "evidence_json": "[]",
  "write_artifacts": true
}
```

## Expected Output

- Planning packet with context-gathering and evidence-first behavior atoms.
- Explicit release evidence gaps.
- Ordered remediation slices for packaging, docs, compatibility, and verification.
- A handoff that remains approval-gated before implementation.

