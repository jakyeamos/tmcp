# TMCP Skill Writing Guidebook

Experimental v0.1 seed for skill evaluation outputs. The pattern catalog and
this guidebook are audited together; neither is behavioral evidence by itself.
Generated reports may propose entries, but they may not silently promote or
rewrite durable guidance.

## 1. Skill activation patterns

Prefer narrow trigger descriptions tied to task evidence. Avoid frontmatter that
matches any task class.

Catalog entry: `trigger.overbroad-description` — Narrow skill activation

Evidence level: `hypothesis` · Status: `held` · Promotion: `hold`

## 2. Verification gate patterns

Prefer concrete commands with pass/fail reporting. Avoid vague quality language
such as "make sure everything works."

Catalog entries: `verification.concrete-command` — Concrete verification command;
`verification.vague-quality-language` — Vague verification language

Evidence level: `hypothesis` · Status: `held` · Promotion: `hold`

## 3. Evidence levels and confidence

Label every pattern claim with an evidence level:

- `hypothesis` — plausible, not tested
- `static_review` — rubric or lint review only
- `dogfooded` — seen in TMCP usage
- `controlled_single_agent_eval` — A/B tested on one agent/host
- `controlled_multi_agent_eval` — tested across agents or hosts
- `production_reinforced` — repeated real-world traces
- `deprecated` — previously recommended but contradicted

## 4. Harvest feedback boundary

Evaluation may propose harvest warnings. It must not auto-promote or silently
rewrite durable routing state.

## 5. Instruction precedence

Treat system, developer, and user instructions as higher-priority constraints.
Do not write skill language that asks an agent to ignore or override them.

Catalog entry: `precedence.override-hazard` — Instruction precedence is preserved

Evidence level: `hypothesis` · Status: `held` · Promotion: `hold`

## 6. Promotion boundary

Every currently shipped entry is on `hold`. The four catalog entries above are
starting hypotheses, not proven composition rules. A controlled claim must name
an experiment and resolve to source-only evidence before it can become eligible
for manual review. A benchmark plan, fixture, dry run, or synthetic trace can
prepare that experiment but cannot promote a guidebook entry.

For a completed campaign, emit a non-mutating manual-review candidate only
after the primary score and a distinct blind rejudge agree across all 540 cells:

```bash
python3 scripts/promote_guidebook_from_campaign.py \
  --campaign path/to/composition-lift-campaign.json \
  --host-results path/to/host-results.json \
  --primary-evaluator path/to/evaluator-artifacts.json \
  --summary path/to/composition-lift-summary.json \
  --rejudge path/to/independent-rejudge-envelope.json \
  --pattern-id verification.concrete-command
```

The command preserves raw evaluator and rejudge artifacts by digest reference,
requires distinct evaluator identities and execution IDs, and emits
`eligible_for_manual_review` with `auto_apply: false`. It never edits this
guidebook or the catalog; a human must review the candidate and any later
replication before a durable evidence-level change.
