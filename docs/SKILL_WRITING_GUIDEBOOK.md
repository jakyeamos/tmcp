# TMCP Skill Writing Guidebook

Experimental v0.1 seed for skill evaluation outputs. Generated reports may update
`docs/SKILL_PATTERN_CATALOG.json` and this guidebook with evidence levels.

## 1. Skill activation patterns

Prefer narrow trigger descriptions tied to task evidence. Avoid frontmatter that
matches any task class.

## 2. Verification gate patterns

Prefer concrete commands with pass/fail reporting. Avoid vague quality language
such as "make sure everything works."

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
