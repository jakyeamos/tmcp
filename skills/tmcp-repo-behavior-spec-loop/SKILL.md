---
name: tmcp-repo-behavior-spec-loop
description: Use TMCP for repo-wide behavior specification loops: code-derived feature inventory, canonical spreadsheet tracking, running-app verification, defect remediation, regression coverage, and final evidence audits.
status: experimental
---

# TMCP Repo Behavior Spec Loop

Status: experimental. This workflow remains shipped and callable, but its public contract may change.

Use this skill when the user asks to inventory every feature from code, create or maintain a canonical behavior spreadsheet, test user stories against the running app, fix defects, re-test, add regression coverage, and drive a repo to an evidence-backed known-good state.

Do not use it for a narrow bug fix, a generic test-strategy review, or a release-readiness audit unless the user specifically wants the full behavior spreadsheet and verification loop.

## Workflow

1. Gather evidence: repo instructions, routes/pages/layouts, components, APIs, server actions, auth and permissions, forms, modals, search/filter/sort/pagination, data models, jobs, tests, scripts, and dev workflow.
2. Invoke `tmcp_harvest_skills` or `tmcp_recommend_workflows` with `candidate_workflows: ["repo_behavior_spec_loop"]`.
3. Build or update exactly one canonical spreadsheet with stable `AREA-###` Feature IDs, source file/function citations, expected behavior from code, user-acceptable behavior, test method, observed behavior, status, defect metadata, evidence, iteration, and last tested commit.
4. Use `expert_rubric_review_plan` for the scored workflow packet and evidence audit before implementation-heavy remediation.
5. Test each row with the strongest available method, fix defects with the smallest safe change, re-test, and add regression coverage or an explicit manual-only reason.
6. Stop only for destructive actions, real product decisions, unavailable required input, or the safety cap after repeated failed fix/re-test attempts.

If MCP tools are unavailable, run from the TMCP plugin root:

```bash
tmcp recommend "<project-path>" --candidate-workflows repo_behavior_spec_loop --min-confidence 0.1 --write-artifacts
```

## Output Contract

Produce or cite:

- TMCP packet and `substance_check`.
- Canonical behavior spreadsheet path and current commit.
- Coverage audit for discovered feature rows and source citations.
- Status counts across `Discovered`, `Spec'd`, `Test-Blocked`, `Tested-Pass`, `Tested-Fail`, `Fixing`, `Fixed`, `Verified`, and `Regression-Covered`.
- Defects by type, root cause, fix summary, and evidence.
- Verification commands or browser actions, observed results, iteration, and last tested commit.
- Regression coverage added or explicit manual-only reason.
- Complexity-gate review and unresolved product/environment questions.
