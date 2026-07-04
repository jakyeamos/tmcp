# Repo Behavior Spec Loop

Use this when a web platform needs a code-derived behavior inventory, running-app verification, defect remediation, and regression coverage tracked in one canonical spreadsheet.

## Objective

Produce a verified behavior specification for the current repo. The spreadsheet is the source of truth: every discoverable feature moves from spec to tested, fixed when needed, verified, and regression-covered or explicitly dispositioned.

## Flow

1. Harvest the repo instructions, routes, pages, components, APIs, actions, tests, scripts, auth/permission surfaces, forms, modals, search/filter/sort/pagination, jobs, and data models.
2. Create or update exactly one canonical spreadsheet with stable `AREA-###` Feature IDs and source file/function citations.
3. Audit spreadsheet coverage before testing starts.
4. Test each user story with the strongest available method, preferably a running app, browser automation, or e2e path.
5. Log observed behavior, status, defect metadata, evidence, iteration, and last tested commit.
6. Fix each defect with the smallest safe change, re-test it, and add regression coverage or a manual-only reason.
7. Run a final evidence audit before marking the repo known-good.

## CLI

```bash
node scripts/tmcp_launcher.mjs recommend . \
  --candidate-workflows repo_behavior_spec_loop \
  --min-confidence 0.1 \
  --write-artifacts \
  --output-dir .tmcp/repo-behavior-spec-loop
```

Then run the selected workflow through `expert_rubric_review_plan` with repo-specific evidence.

## Required Spreadsheet Columns

- `Feature ID`
- `Area`
- `Surface`
- `User story`
- `Persona / role`
- `Auth state`
- `Data precondition`
- `Viewport`
- `Expected behavior from code`
- `User-acceptable behavior`
- `Source files/functions`
- `Test method`
- `Test command/actions`
- `Observed behavior`
- `Status`
- `Defect ID`
- `Defect type`
- `Root cause`
- `Fix summary`
- `Regression test added`
- `Complexity review`
- `Evidence`
- `Iteration`
- `Last tested commit`
- `Open question / notes`

## Expected Output

- Canonical behavior spreadsheet path and current commit.
- Feature counts by status and area.
- Defect list by type with root cause and fix summary.
- Commands, browser actions, and evidence used for verification.
- Regression coverage added or manual-only justification.
- Complexity-gate findings and unresolved product/environment questions.
