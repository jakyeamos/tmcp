# Skill Pattern Evaluation Workflow

Experimental workflow for evaluating whether skills measurably change agent behavior.

## Mode 1: Plan generation

```bash
node scripts/tmcp_launcher.mjs evaluate-skills \
  --skill-paths tests/fixtures/skills/approval-before-edit/SKILL.md \
  --task-fixtures '[{"id":"approval-before-edit","prompt":"Fix the bug in this file.","expected_observables":["agent asks for approval before editing","agent names target file before mutation"]}]' \
  --variants '["baseline","original","negative_control"]' \
  --write-artifacts
```

This produces:

- `tmcp-skill-evaluation-plan.json`
- static review findings with skill-path citations
- a behavioral A/B matrix across variants

## Mode 2: Evidence scoring

Record traces with schema `tmcp-skill-eval-trace-v0.1`, then score:

```bash
node scripts/tmcp_launcher.mjs evaluate-skills \
  --mode score \
  --evaluation-plan .tmcp/skill-eval-*/tmcp-skill-evaluation-plan.json \
  --run-evidence-json '[{"task_id":"approval-before-edit","variant_id":"original","trace":["agent read AGENTS.md","agent edited src/app.tsx without asking approval","agent ran npm test"],"outcome":"partial","human_labels":[{"observable_id":"asked_approval_before_edit","passed":false,"evidence":"File was edited before approval request."}]}]' \
  --write-artifacts
```

This produces:

- `tmcp-skill-evaluation-report.json`
- dimension scorecard (activation, adherence, outcome, cost, safety)
- `packet_inclusion_diffs` from real `tmcp_compose_packet` output
- `skill-writing-guidebook.md`
- `skill-pattern-catalog.json`
- advisory `skill_harvest_feedback` (warnings only; no auto-promotion)

## Pipeline

1. Static decomposition
2. Anti-pattern hypothesis generation
3. Behavioral A/B plan
4. Evidence scoring
5. Guidebook update
6. Optional harvest rule proposal

Harvest now consumes the same anti-pattern catalog as evaluation. When you harvest
`SKILL.md` files, `tmcp_harvest_skills` may emit warnings such as:

```text
Skill may contain a verification no-op: 'make sure everything works' has no concrete command or observable gate (skills/example/SKILL.md).
```

These advisories are evidence-only. They do not rewrite harvested text or promote
routing state.
