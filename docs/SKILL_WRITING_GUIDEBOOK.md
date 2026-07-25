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
tested explicit controls. Untyped variants remain outside the gate until their
evidence scope is explicit; keep those exclusions visible rather than weakening
the bar or treating structural agreement as causal proof.

## 6. Neutral evidence and discovered-corpus coverage

Neutral artifacts are now admitted through
`tests/fixtures/skill-fixtures/neutral-corpus-v0.1.json`. The validator can
scope exact values and disclosure patterns to the complete artifact while still
requiring a final-response readiness statement. This matches the judge's bar
for evidence distributed across `observations`, `actions`, and a structured
`final_response`: the original control is 0/3, the first candidate is 2/3, and
the corrected candidate variant is 3/3, with 9/9 structural–judge agreement.

Coverage of the discovered corpus is a separate gate. Audit a scaffolded
manifest with:

```bash
python3 scripts/audit_skill_fixture_coverage.py \
  /path/to/fixture-set/manifest.json
```

The recorded [coverage baseline](/private/tmp/tmcp-skill-fixtures-20260722/tests/fixtures/skill-fixtures/corpus-coverage-baseline-v0.1.json)
finds 158 discovered skills but only 1 ready skill and 1 golden case in the
full discovery manifest; 157 still need a case and bar. The later calibrated
subset contains 7 skills and 8 cases. That gap is an explicit promotion stop,
not missing evidence to be inferred from static rewrites.
