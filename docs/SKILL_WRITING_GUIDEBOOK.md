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

## 5. Full-corpus dogfood gate

The available fixture corpus is now exercised as one provenance-aware gate, not
only as isolated composition examples. Run it from the repository root:

```bash
python3 scripts/validate_skill_fixture_corpus.py \
  --manifest tests/fixtures/skill-fixtures/full-corpus-v0.1.json \
  --project-root . \
  --artifact-root /private/tmp
```

The checked-in baseline is
`tests/fixtures/skill-fixtures/full-corpus-baseline-v0.1.json`. It covers eight
single-skill families and 42 available runner artifacts at `gpt-5.5` with low
reasoning. The structural validator passes 31/42, the independent judge passes
31/42, and the two agree on 42/42 runs. Every run can point to a specific judge
record; the gate records that judge file's SHA-256 and record index so a copied
boolean cannot silently drift from its source.

This is a readiness gate for the fixture/evaluator apparatus, not a claim that
all skills are good. The 11 failures are behavior signals: the ambiguous
approval prompt remains a no-target failure, required-read and precedence
controls expose original-version gaps, and the candidate versions pass the
tested explicit controls. Neutral-format output-contract variants remain
judge-only because their artifact schema does not expose enough typed evidence
to prove the response-field bar. Keep those exclusions visible rather than
weakening the bar or treating structural agreement as causal proof.
